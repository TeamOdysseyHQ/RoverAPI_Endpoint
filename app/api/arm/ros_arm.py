"""ROS integration endpoints for arm subsystem"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.ros.manager import ros_manager


router = APIRouter()


class ArmCommandRequest(BaseModel):
    """Request model for arm commands"""

    command: int  # 1 = drop payload, -1 = emergency stop


class ArmTargetRequest(BaseModel):
    """Request model for arm target angles"""

    dc_elbow: float
    dc_wrist_pitch: float
    stepper_base_pan: float
    stepper_shoulder: float
    servo_wrist_roll: float
    servo_gripper: float


@router.post("/ros/command")
async def publish_arm_command(req: ArmCommandRequest):
    """
    Publish command to arm/command topic.

    Commands:
    - 1 = Drop payload (safe drop sequence)
    - -1 = Emergency stop

    Example request:
    ```json
    {
        "command": 1
    }
    ```
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to ROS. Ensure rosbridge_server is running.",
        )

    success = ros_manager.publish_arm_command(req.command)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to publish arm command")

    command_name = (
        "drop" if req.command == 1 else "stop" if req.command == -1 else "unknown"
    )
    return {
        "success": True,
        "message": f"Arm command published: {command_name}",
        "command": req.command,
    }


@router.post("/ros/drop")
async def drop_payload():
    """
    Convenience endpoint to trigger safe drop sequence.
    Publishes command=1 to arm/command topic.
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to ROS. Ensure rosbridge_server is running.",
        )

    success = ros_manager.publish_arm_command(1)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to publish drop command")

    return {
        "success": True,
        "message": "Drop payload command sent to arm",
    }


@router.post("/ros/stop")
async def emergency_stop():
    """
    Convenience endpoint for emergency stop.
    Publishes command=-1 to arm/command topic.
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to ROS. Ensure rosbridge_server is running.",
        )

    success = ros_manager.publish_arm_command(-1)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to publish stop command")

    return {
        "success": True,
        "message": "Emergency stop command sent to arm",
    }


@router.post("/ros/target")
async def publish_arm_target(req: ArmTargetRequest):
    """
    Publish target angles to arm/target topic.

    The arm will move to these target angles using closed-loop control.

    Example request:
    ```json
    {
        "dc_elbow": 45.0,
        "dc_wrist_pitch": 30.0,
        "stepper_base_pan": 90.0,
        "stepper_shoulder": 60.0,
        "servo_wrist_roll": 90.0,
        "servo_gripper": 45.0
    }
    ```
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to ROS. Ensure rosbridge_server is running.",
        )

    success = ros_manager.publish_arm_target(
        dc_elbow=req.dc_elbow,
        dc_wrist_pitch=req.dc_wrist_pitch,
        stepper_base_pan=req.stepper_base_pan,
        stepper_shoulder=req.stepper_shoulder,
        servo_wrist_roll=req.servo_wrist_roll,
        servo_gripper=req.servo_gripper,
    )

    if not success:
        raise HTTPException(
            status_code=500, detail="Failed to publish arm target angles"
        )

    return {
        "success": True,
        "message": "Arm target angles published",
        "target": {
            "dc": {
                "elbow": req.dc_elbow,
                "wrist_pitch": req.dc_wrist_pitch,
            },
            "stepper": {
                "base_pan": req.stepper_base_pan,
                "shoulder": req.stepper_shoulder,
            },
            "servo": {
                "wrist_roll": req.servo_wrist_roll,
                "gripper": req.servo_gripper,
            },
        },
    }


@router.post("/ros/telemetry/subscribe")
async def subscribe_to_arm_telemetry():
    """
    Subscribe to arm/telemetry topic.

    After subscribing, use GET /api/arm/ros/telemetry to retrieve latest data.
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to ROS. Ensure rosbridge_server is running.",
        )

    success = ros_manager.subscribe_arm_telemetry()

    if not success:
        raise HTTPException(
            status_code=500, detail="Failed to subscribe to arm/telemetry"
        )

    return {
        "success": True,
        "message": "Subscribed to arm/telemetry topic",
        "info": "Use GET /api/arm/ros/telemetry to retrieve latest telemetry data",
    }


@router.get("/ros/telemetry")
async def get_arm_telemetry():
    """
    Get the latest arm telemetry data.

    Must subscribe first using POST /api/arm/ros/telemetry/subscribe.

    Returns telemetry with joint angles and RC channel values:
    ```json
    {
        "success": true,
        "message": "Latest arm telemetry",
        "data": {
            "stepper": {
                "base_pan": 45.0,
                "shoulder": 30.0
            },
            "dc": {
                "elbow": 60.0,
                "wrist_pitch": 25.0
            },
            "servo": {
                "wrist_roll": 90.0,
                "gripper": 45.0
            },
            "rc_channels": {
                "ch1": 1500,
                "ch2": 1500,
                "ch3": 1000,
                "ch4": 1500,
                "ch5": 1000,
                "ch6": 1000
            },
            "raw": "45.0,30.0,60.0,25.0,90.0,45.0,1500,1500,1000,1500,1000,1000"
        }
    }
    ```
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to ROS. Ensure rosbridge_server is running.",
        )

    telemetry = ros_manager.get_latest_arm_telemetry()

    if telemetry is None:
        return {
            "success": False,
            "message": "No telemetry data received yet. Ensure you've subscribed and messages are being published.",
            "data": None,
        }

    return {
        "success": True,
        "message": "Latest arm telemetry",
        "data": telemetry,
    }
