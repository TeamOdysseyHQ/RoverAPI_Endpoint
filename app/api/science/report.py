from fastapi import APIRouter, Request, Query
from fastapi.responses import FileResponse
from datetime import datetime
import os
import uuid
import time
from .report_handler import ReportHandler, DuplicationError, ReportGenerationFailure

router = APIRouter()

# Report directory configuration (can be overridden with environment variables)
# Default to project-relative paths that work for any user
_BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
REPORT_OUTPUT_DIR = os.getenv(
    "SCIENCE_REPORT_OUTPUT_DIR", os.path.join(_BASE_DIR, "storage", "sci_reports")
)
REPORT_SOURCE_DIR = os.getenv(
    "SCIENCE_REPORT_SOURCE_DIR", os.path.join(_BASE_DIR, "storage", "report_sci_gen")
)

# Ensure directories exist
os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)
os.makedirs(REPORT_SOURCE_DIR, exist_ok=True)

@router.post("/assign_expedition")
async def assign_expedition():

    eid = str(uuid.uuid4()).replace("-", "")
    counter = 0

    while os.path.exists("/home/administratror/expeditions/unprocessed/" + eid):
        
        if counter > 5:
            eid = str(time.time()).replace(".", "")  # fallback to timestamp
            break
        
        eid = str(uuid.uuid4()).replace("-", "")
        counter += 1

    os.mkdir("/home/administratror/expeditions/unprocessed/" + eid)
    return {
        "success": True,
        "status": "Success",
        "expedition_id": eid,
        "message": "Expedition ID assigned successfully."
    }

@router.get("/expedition_check/{expedition_id}")
async def expedition_check(expedition_id: str):
    unprocessed_path = f"/home/administratror/expeditions/unprocessed/{expedition_id}"
    processed_path = f"/home/administratror/expeditions/processed/{expedition_id}"

    if os.path.exists(processed_path):
        status = "processed"
    elif os.path.exists(unprocessed_path):
        status = "unprocessed"
    else:
        status = "not_found"

    return {
        "success": True,
        "status": "Success",
        "expedition_id": expedition_id,
        "expedition_status": status,
        "message": "Expedition status checked successfully."
    }

@router.post("/expeditions_list")
async def expeditions_list():
    
    try:
    
        unprocessed = os.listdir("/home/administratror/expeditions/unprocessed/")
        processed = os.listdir("/home/administratror/expeditions/processed/")

        for expedition in processed:
            if expedition in unprocessed:
                unprocessed.remove(expedition)

            if os.path.exists(f"/home/administratror/expeditions/processed/{expedition}/metadata.dat"):
                try:
                    with open(f"/home/administratror/expeditions/processed/{expedition}/metadata.dat", "r") as meta_f:
                        report_id = meta_f.readline().strip()
                        processed[processed.index(expedition)] = {
                            "expedition_id": expedition,
                            "report_id": report_id,
                            "failure": False
                        }
                except Exception as e:

                    report_id = f"unknown/failed to fetch because of {e}"
                    processed[processed.index(expedition)] = {
                        "expedition_id": expedition,
                        "report_id": report_id,
                        "failure": True
                    }

                    pass  # ignore metadata read errors

        return {
            "success": True,
            "status": "Success",
            "unprocessed_expeditions": unprocessed,
            "processed_expeditions": processed,
            "message": "Expedition list fetched successfully."
        }
    
    except Exception as e:
        return {
            "success": False,
            "status": "Error",
            "message": f"Failed to list expeditions: {e}"
        }

@router.post("/reports")
async def sci_reports(request: Request):
    data = (
        await request.json()
        if request.headers.get("content-type") == "application/json"
        else None
    )

    if not (data and data.get("inference")):
        return {
            "success": False,
            "status": "Error",
            "message": "Invalid request. 'inference' field is required.",
        }
    
    img_captions: dict[str, str] = data.get("image_captions", {})
    expedition_id: int | None = data.get("expedition_id", None)

    try:
        rh_handler = ReportHandler(expedition_id=expedition_id, img_captions=img_captions)
        rid, report_path = rh_handler.create_report(data["inference"])

        if not report_path:
            return {
                "success": False,
                "status": "Error",
                "message": f"Report generated but not found at expected path: {report_path}.",
            }

        return {
            "success": True,
            "status": "Success",
            "message": "Report generated successfully.",
            "report_id": rid,  # faster query
            "report_path": report_path,
        }

    except ImportError as ie:
        return {
            "success": False,
            "status": "Error",
            "message": f"ReportHandler module not found: {ie}",
        }
    except ReportGenerationFailure as rgf:
        return {"success": False, "status": "Error", "message": f"{rgf}"}
    except DuplicationError as de:
        return {
            "success": False,
            "status": "Error",
            "message": f"Report generation requests too frequent: {de}",
        }
    except Exception as e:
        return {
            "success": False,
            "status": "Error",
            "message": f"Unhandled exception with report handler: {e}",
        }


def verify_report_access(rid: str | None, rpath: str | None) -> int:
    if rid and os.path.exists(os.path.join(REPORT_OUTPUT_DIR, f"{rid}.pdf")):
        return 1
    elif rpath and os.path.exists(rpath):
        return 2

    return 0  # * unknown report!


@router.get("/report/{id}")
async def get_report_by_id(id: str):
    info_code = verify_report_access(id, None)

    if info_code == 0:
        return {
            "success": False,
            "status": "Error",
            "message": "Report not found with given ID.",
        }

    elif info_code == 1:
        return FileResponse(
            path=os.path.join(REPORT_OUTPUT_DIR, f"{id}.pdf"),
            media_type="application/pdf",
            filename=f"{id}.pdf",
        )

    else:
        return {
            "success": False,
            "status": "Error",
            "message": "Unhandled error in report retrieval by ID.",
        }


@router.get("/report/by_path")
async def get_report_by_path(path: str = Query(..., description="Report file path")):
    info_code = verify_report_access(None, path)

    if info_code == 0:
        return {
            "success": False,
            "status": "Error",
            "message": "Report not found with given path.",
        }

    elif info_code == 2:
        return FileResponse(
            path=path, media_type="application/pdf", filename=os.path.basename(path)
        )

    else:
        return {
            "success": False,
            "status": "Error",
            "message": "Unhandled error in report retrieval by path.",
        }


@router.get("/report/{id}/path/{path}")
async def get_report_by_id_and_path(id: str, path: str):
    info_code = verify_report_access(id, path)
    if info_code == 0:
        return {
            "success": False,
            "status": "Error",
            "message": "Report not found with given ID or path.",
        }

    elif info_code == 1:
        return FileResponse(
            path=os.path.join(REPORT_OUTPUT_DIR, f"{id}.pdf"),
            media_type="application/pdf",
            filename=f"{id}.pdf",
        )

    elif info_code == 2:
        return FileResponse(
            path=path, media_type="application/pdf", filename=os.path.basename(path)
        )

    else:
        return {
            "success": False,
            "status": "Error",
            "message": "Unhandled error in report retrieval by ID and path.",
        }


@router.get("/reports/ids")
async def list_reports():
    try:
        reports = os.listdir(REPORT_OUTPUT_DIR)
        report_ids = [f[:-4] for f in reports if f.endswith(".pdf")]

        return {
            "success": True,
            "status": "Success",
            "message": "Reports listed successfully.",
            "report_ids": report_ids,
        }

    except Exception as e:
        return {
            "success": False,
            "status": "Error",
            "message": f"Failed to list reports: {e}",
        }


@router.get("/reports/path")
async def list_reports_path():
    try:
        reports = os.listdir(REPORT_SOURCE_DIR)

        return {
            "success": True,
            "status": "Success",
            "message": "Reports listed successfully.",
            "report_ids": reports,
        }

    except Exception as e:
        return {
            "success": False,
            "status": "Error",
            "message": f"Failed to list reports: {e}",
        }


@router.post("/get_report")
async def get_report(request: Request):
    data = (
        await request.json()
        if request.headers.get("content-type") == "application/json"
        else None
    )

    if not (data and (data.get("report_id") or data.get("report_path"))):
        return {
            "success": False,
            "status": "Error",
            "message": "Invalid request. 'report_id' or 'report_path' preferably both field(s) are required.",
        }

    rid = data.get("report_id")
    rpath = data.get("report_path")

    info_code = verify_report_access(rid, rpath)

    if info_code == 0:
        # worst case
        return {
            "success": False,
            "status": "Error",
            "message": "Report not found with given ID or path.",
        }

    elif info_code == 1:
        # best case
        return FileResponse(
            path=os.path.join(REPORT_OUTPUT_DIR, f"{rid}.pdf"),
            media_type="application/pdf",
            filename=f"{rid}.pdf",
        )

    elif info_code == 2:
        # acceptable case - but need to inform that it was fetched via path not id which is weird and sus
        return FileResponse(
            path=rpath, media_type="application/pdf", filename=os.path.basename(rpath)
        )

    else:
        return {
            "success": False,
            "status": "Error",
            "message": "Unhandled error in report retrieval.",
        }


@router.get("/reports/metadata")
async def get_reports_metadata():
    """Get detailed metadata for all reports"""
    try:
        reports = []
        for filename in os.listdir(REPORT_OUTPUT_DIR):
            if filename.endswith(".pdf"):
                filepath = os.path.join(REPORT_OUTPUT_DIR, filename)
                stat = os.stat(filepath)
                reports.append(
                    {
                        "report_id": filename[:-4],
                        "filename": filename,
                        "size_bytes": stat.st_size,
                        "size_kb": round(stat.st_size / 1024, 2),
                        "size_mb": round(stat.st_size / (1024 * 1024), 2),
                        "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                        "modified_at": datetime.fromtimestamp(
                            stat.st_mtime
                        ).isoformat(),
                    }
                )

        # Sort by creation time, newest first
        reports.sort(key=lambda x: x["created_at"], reverse=True)

        return {
            "success": True,
            "status": "Success",
            "message": "Report metadata retrieved successfully.",
            "reports": reports,
            "count": len(reports),
        }

    except Exception as e:
        return {
            "success": False,
            "status": "Error",
            "message": f"Failed to retrieve report metadata: {e}",
        }


@router.delete("/report/{id}")
async def delete_report(id: str):
    """Delete a report by ID"""
    try:
        pdf_path = os.path.join(REPORT_OUTPUT_DIR, f"{id}.pdf")

        if not os.path.exists(pdf_path):
            return {
                "success": False,
                "status": "Error",
                "message": "Report not found with given ID.",
            }

        # Delete the PDF
        os.remove(pdf_path)

        # Try to find and delete source files (optional cleanup)
        try:
            typ_files = [f for f in os.listdir(REPORT_SOURCE_DIR) if f.endswith(".typ")]
            for typ_file in typ_files:
                typ_path = os.path.join(REPORT_SOURCE_DIR, typ_file)
                pdf_file = typ_file[:-4] + ".pdf"
                pdf_source_path = os.path.join(REPORT_SOURCE_DIR, pdf_file)

                # If source PDF still exists and matches our ID, clean it up
                if os.path.exists(pdf_source_path):
                    source_stat = os.stat(pdf_source_path)
                    # Clean up if file is older than 1 day (optional safety)
                    if (datetime.now().timestamp() - source_stat.st_mtime) > 86400:
                        try:
                            os.remove(typ_path)
                            os.remove(pdf_source_path)
                        except:
                            pass
        except:
            pass  # Source cleanup is optional, don't fail if it doesn't work

        return {
            "success": True,
            "status": "Success",
            "message": "Report deleted successfully.",
        }

    except Exception as e:
        return {
            "success": False,
            "status": "Error",
            "message": f"Failed to delete report: {e}",
        }
