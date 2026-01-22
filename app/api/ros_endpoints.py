"""General ROS bridge status and health endpoints"""

from fastapi import APIRouter, HTTPException
from app.ros.manager import ros_manager


router = APIRouter()


@router.get("/status")
async def get_api_status():
    """
    Get API server status - used for connection testing from the UI.
    Returns server health and ROS bridge connection state.
    """
    ros_status = "connected" if ros_manager.is_connected else "disconnected"
    return {
        "success": True,
        "status": "ok",
        "message": "Rover API Server is running",
        "version": "2.0.0",
        "ros_bridge": ros_status,
    }


@router.get("/ros/status")
async def get_ros_status():
    """
    Get rosbridge connection status and information.
    Shows which topics are subscribed/published, connection state, etc.
    """
    status = ros_manager.get_status()

    return {
        "success": True,
        "status": status,
        "message": "Connected to ROS"
        if status["connected"]
        else "Not connected to ROS",
    }


@router.post("/ros/connect")
async def connect_to_ros():
    """
    Manually trigger connection to rosbridge_server.
    Usually not needed as connection happens automatically on startup.
    """
    if ros_manager.is_connected:
        return {
            "success": True,
            "message": "Already connected to ROS",
            "url": ros_manager.config.url,
        }

    success = ros_manager.connect()

    if not success:
        raise HTTPException(
            status_code=503,
            detail="Failed to connect to rosbridge_server. Ensure it's running at "
            + ros_manager.config.url,
        )

    return {
        "success": True,
        "message": "Connected to ROS",
        "url": ros_manager.config.url,
    }


@router.post("/ros/disconnect")
async def disconnect_from_ros():
    """
    Disconnect from rosbridge_server.
    Useful for testing or maintenance.
    """
    if not ros_manager.is_connected:
        return {"success": True, "message": "Already disconnected from ROS"}

    ros_manager.disconnect()

    return {"success": True, "message": "Disconnected from ROS"}
