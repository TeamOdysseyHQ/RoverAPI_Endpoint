from fastapi import APIRouter
from app.py_types import listOfStrings

router = APIRouter()


def sci_avi_l_ret() -> listOfStrings:
    # * Add all endpoints here without fail.
    return [
        "available",
        "reports",
        "get_report",
        "report/:id",
        "report/path/:path",
        "report/:id/path/:path",
        "/reports/ids",
        "/reports/path",
        "microscope/start",
        "microscope/stop",
        "microscope/status",
        "microscope/stream",
        "microscope/stream/ws",
        "microscope/capture",
    ]


@router.post("/available")
async def sci_avi():
    return {"success": True, "status": "Success", "endpoints": sci_avi_l_ret()}
