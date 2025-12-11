from fastapi import APIRouter, HTTPException
from app.py_types import listOfStrings

router = APIRouter()

def nav_avi_l_ret() -> listOfStrings:
    
    #* Add all endpoints here without fail.
    return [
        "available", "capture", "capture_test_data", "waypoint", "get_waypoints", "get_metadata", 
        "generate_report", "generate_comprehensive_report", "export_data", "reports", 
        "route_analysis", "download/<filename>"
    ]

@router.post("/available")
async def nav_avi():
    return {
        "success": True,
        "status": "Success",
        "endpoints": nav_avi_l_ret()
    }