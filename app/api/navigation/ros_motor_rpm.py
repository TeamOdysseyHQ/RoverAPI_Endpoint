"""ROS integration endpoints for motor RPM telemetry"""

from fastapi import APIRouter, HTTPException
from app.ros.manager import ros_manager


router = APIRouter()


@router.post("/ros/motor_rpms/subscribe")
async def subscribe_to_motor_rpms():
    """
    Subscribe to the /motor_rpms topic (std_msgs/Float32MultiArray).

    This starts listening for 6-wheel RPM data published by the rover's
    motor controllers. After subscribing, use GET /api/nav/ros/motor_rpms
    to retrieve the latest data.

    The Float32MultiArray contains 6 floats in order:
    [front_left, front_right, mid_left, mid_right, rear_left, rear_right]
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to ROS. Ensure rosbridge_server is running.",
        )

    success = ros_manager.subscribe_motor_rpms()

    if not success:
        raise HTTPException(
            status_code=500, detail="Failed to subscribe to /motor_rpms"
        )

    return {
        "success": True,
        "message": "Subscribed to /motor_rpms topic",
        "info": "Use GET /api/nav/ros/motor_rpms to retrieve latest motor RPM data",
    }


@router.get("/ros/motor_rpms")
async def get_motor_rpms():
    """
    Get the latest motor RPM data from /motor_rpms topic.

    Must subscribe first using POST /api/nav/ros/motor_rpms/subscribe.

    Returns per-wheel RPM values for all 6 wheels:
    ```json
    {
        "success": true,
        "message": "Latest motor RPM data",
        "data": {
            "front_left": 120.0,
            "front_right": 118.5,
            "mid_left": 121.0,
            "mid_right": 119.0,
            "rear_left": 117.5,
            "rear_right": 122.0,
            "raw": [120.0, 118.5, 121.0, 119.0, 117.5, 122.0]
        }
    }
    ```
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to ROS. Ensure rosbridge_server is running.",
        )

    rpms = ros_manager.get_latest_motor_rpms()

    if rpms is None:
        return {
            "success": False,
            "message": "No motor RPM data received yet. Ensure you've subscribed and messages are being published.",
            "data": None,
        }

    return {"success": True, "message": "Latest motor RPM data", "data": rpms}
