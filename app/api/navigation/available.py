from fastapi import APIRouter, HTTPException
from app.py_types import listOfStrings

router = APIRouter()


def nav_avi_l_ret() -> listOfStrings:
    # * Add all endpoints here without fail.
    return [
        "available",
        "capture",
        "capture_test_data",
        "waypoint",
        "get_waypoints",
        "get_metadata",
        "generate_report",
        "generate_comprehensive_report",
        "export_data",
        "reports",
        "route_analysis",
        "download/<filename>",
        "cameras/detect",
        "cameras/{camera_index}/start",
        "cameras/{camera_index}/stop",
        "cameras/stop_all",
        "cameras/status",
        "cameras/{camera_index}/status",
        "cameras/{camera_index}/capture",
        "cameras/{camera_index}/stream",
        "cameras/{camera_index}/webrtc/offer",
        "cameras/{camera_index}/webrtc/status",
        "cameras/webrtc/status",
        "ros/camera/webrtc/offer",
        "ros/camera/webrtc/status",
        "ros/motor_rpms/subscribe",
        "ros/motor_rpms",
    ]


@router.post("/available")
async def nav_avi():
    return {"success": True, "status": "Success", "endpoints": nav_avi_l_ret()}
