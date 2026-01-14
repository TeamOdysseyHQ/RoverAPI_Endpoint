"""ROS integration endpoints for navigation subsystem"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.ros.manager import ros_manager


router = APIRouter()


class CmdVelRequest(BaseModel):
    """Request model for velocity commands"""

    linear_x: float = 0.0
    linear_y: float = 0.0
    linear_z: float = 0.0
    angular_x: float = 0.0
    angular_y: float = 0.0
    angular_z: float = 0.0


class TwistMessage(BaseModel):
    """Full Twist message model"""

    linear: dict
    angular: dict


@router.post("/ros/cmd_vel")
async def publish_cmd_vel(cmd: CmdVelRequest):
    """
    Publish velocity command to /cmd_vel topic.

    Example request:
    ```json
    {
        "linear_x": 1.0,
        "linear_y": 0.0,
        "linear_z": 0.0,
        "angular_x": 0.0,
        "angular_y": 0.0,
        "angular_z": 0.5
    }
    ```
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to ROS. Ensure rosbridge_server is running.",
        )

    success = ros_manager.publish_cmd_vel(
        linear_x=cmd.linear_x,
        linear_y=cmd.linear_y,
        linear_z=cmd.linear_z,
        angular_x=cmd.angular_x,
        angular_y=cmd.angular_y,
        angular_z=cmd.angular_z,
    )

    if not success:
        raise HTTPException(
            status_code=500, detail="Failed to publish velocity command"
        )

    return {
        "success": True,
        "message": "Velocity command published to /cmd_vel",
        "command": {
            "linear": {"x": cmd.linear_x, "y": cmd.linear_y, "z": cmd.linear_z},
            "angular": {"x": cmd.angular_x, "y": cmd.angular_y, "z": cmd.angular_z},
        },
    }


@router.post("/ros/cmd_vel/stop")
async def stop_robot():
    """
    Send stop command (all zeros) to /cmd_vel.
    Convenience endpoint to immediately stop the rover.
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to ROS. Ensure rosbridge_server is running.",
        )

    success = ros_manager.publish_cmd_vel(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to publish stop command")

    return {"success": True, "message": "Stop command published to /cmd_vel"}


@router.post("/ros/odom/subscribe")
async def subscribe_to_odom():
    """
    Subscribe to odometry topic (/odom).
    After subscribing, use GET /api/nav/ros/odom to retrieve latest data.
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to ROS. Ensure rosbridge_server is running.",
        )

    success = ros_manager.subscribe_odom()

    if not success:
        raise HTTPException(status_code=500, detail="Failed to subscribe to /odom")

    return {
        "success": True,
        "message": "Subscribed to /odom topic",
        "info": "Use GET /api/nav/ros/odom to retrieve latest odometry data",
    }


@router.get("/ros/odom")
async def get_odometry():
    """
    Get the latest odometry data from /odom topic.
    Must subscribe first using POST /api/nav/ros/odom/subscribe.

    Returns odometry message with pose and twist information.
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to ROS. Ensure rosbridge_server is running.",
        )

    odom = ros_manager.get_latest_odom()

    if odom is None:
        return {
            "success": False,
            "message": "No odometry data received yet. Ensure you've subscribed and messages are being published.",
            "data": None,
        }

    return {"success": True, "message": "Latest odometry data", "data": odom}


@router.post("/ros/publish")
async def publish_custom_message(topic: str, message_type: str, message: dict):
    """
    Publish a custom message to any ROS topic.

    Example request:
    ```json
    {
        "topic": "/custom_topic",
        "message_type": "std_msgs/String",
        "message": {"data": "Hello ROS!"}
    }
    ```
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to ROS. Ensure rosbridge_server is running.",
        )

    success = ros_manager.publish(topic, message_type, message)

    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to publish to {topic}")

    return {
        "success": True,
        "message": f"Message published to {topic}",
        "topic": topic,
        "message_type": message_type,
    }
