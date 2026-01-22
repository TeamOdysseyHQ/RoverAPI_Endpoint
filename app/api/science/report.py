from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
import os
from report_handler import ReportHandler, DuplicationError, ReportGenerationFailure 

router = APIRouter()
    
@router.post("/reports")
async def sci_reports(request: Request):
    
    data = await request.json()
    
    if not (data and data.get("inference")):
        return {
            "success": False,
            "status": "Error",
            "message": "Invalid request. 'inference' field is required."
        }
    
    try:
        rh_handler = ReportHandler()
        rid, report_path = rh_handler.create_report(data["inference"])
    
        if not report_path:
            return {
                "success": False,
                "status": "Error",
                "message": f"Report generated but not found at expected path: {report_path}."
            }
        
        return {
            "success": True,
            "status": "Success",
            "message": "Report generated successfully.",
            "report_id": rid, # faster query
            "report_path": report_path,
        }
    
    except ImportError as ie:
        return {
            "success": False,
            "status": "Error",
            "message": f"ReportHandler module not found: {ie}"
        }
    except ReportGenerationFailure as rgf:
        return {
            "success": False,
            "status": "Error",
            "message": f"Report generation failed: {rgf}"
        }
    except DuplicationError as de:
        return {
            "success": False,
            "status": "Error",
            "message": f"Report generation requests too frequent: {de}"
        }
    except Exception as e:
        return {
            "success": False,
            "status": "Error",
            "message": f"Unhandled exception with report handler: {e}"
        }
    
def verify_report_access(rid: str, rpath: str) -> int:
    
    if rid and os.path.exists(f"/home/administratror/sci_reports_0x1000/{rid}.pdf"):
        return 1
    elif rpath and os.path.exists(rpath):
        return 2
    
    return 0 #* unknown report!
    
@router.post("/get_report")
async def get_report(request: Request):
    
    data = await request.json()
    
    if not (data and (data.get("report_id") or data.get("report_path"))):
        return {
            "success": False,
            "status": "Error",
            "message": "Invalid request. 'report_id' or 'report_path' preferably both field(s) are required."
        }
    
    rid = data.get("report_id")
    rpath = data.get("report_path")
    
    info_code = verify_report_access(rid, rpath)
    
    if info_code == 0:
        # worst case
        return {
            "success": False,
            "status": "Error",
            "message": "Report not found with given ID or path."
        }
    
    elif info_code == 1:
        # best case
        return FileResponse(path=f"/home/administratror/sci_reports_0x1000/{rid}.pdf", 
                            media_type='application/pdf', filename=f"{rid}.pdf")
    
    elif info_code == 2:
        # acceptable case - but need to inform that it was fetched via path not id which is weird and sus
        return FileResponse(path=rpath, media_type='application/pdf', filename=os.path.basename(rpath))
    
    else:
    
        return {
            "success": False,
            "status": "Error",
            "message": "Unhandled error in report retrieval."
        }