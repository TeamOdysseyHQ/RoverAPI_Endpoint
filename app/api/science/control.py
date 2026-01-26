"""Science module control endpoints"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.ros.manager import ros_manager

router = APIRouter()


class ScienceControlCommand(BaseModel):
    """Full science control command structure"""

    linear_actuator_cmd: int = -6  # -1=down, 1=up, 0/4/8/16=microstep, -6=no command
    drill_cmd: int = (
        -6
    )  # -2=CW, -1=dec speed, 0=stop, 1=inc speed, 2=CCW, -6=no command
    barrel_cmd: int = -6  # 1=rotate 60°, 0/4/8/16=microstep, -6=no command
    servo_toggle: bool = False
    science_module_toggle: bool = False


class LinearActuatorCommand(BaseModel):
    """Linear actuator control command"""

    command: int  # -1=down, 1=up, 0/4/8/16=microstep modes


class DrillCommand(BaseModel):
    """Drill motor control command"""

    command: int  # -2=CW, -1=decrease speed, 0=stop, 1=increase speed, 2=CCW


class BarrelCommand(BaseModel):
    """Barrel motor control command"""

    command: int  # 1=rotate 60°, 0/4/8/16=microstep modes


class ServoCommand(BaseModel):
    """PH servo toggle command"""

    toggle: bool


class ScienceModeCommand(BaseModel):
    """Science exploration mode toggle"""

    enable: bool


@router.post("/control/enable")
async def toggle_science_mode(cmd: ScienceModeCommand):
    """
    Toggle science exploration mode on/off.
    When disabled, all science operations are stopped.
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503, detail="Not connected to ROS. Cannot send command."
        )

    success = ros_manager.publish_science_control(science_module_toggle=cmd.enable)

    if not success:
        return {
            "success": False,
            "message": f"Failed to {'enable' if cmd.enable else 'disable'} science mode",
        }

    return {
        "success": True,
        "message": f"Science mode {'enabled' if cmd.enable else 'disabled'}",
        "data": {"enabled": cmd.enable},
    }


@router.post("/control/linear_actuator")
async def control_linear_actuator(cmd: LinearActuatorCommand):
    """
    Send linear actuator command.

    Command values:
    - -1: Move down
    - 1: Move up
    - 0: Full step mode
    - 4: 1/4 microstep mode
    - 8: 1/8 microstep mode
    - 16: 1/16 microstep mode
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503, detail="Not connected to ROS. Cannot send command."
        )

    success = ros_manager.publish_science_control(linear_actuator_cmd=cmd.command)

    if not success:
        return {
            "success": False,
            "message": "Failed to send linear actuator command",
        }

    return {
        "success": True,
        "message": f"Linear actuator command sent: {cmd.command}",
        "data": {"command": cmd.command},
    }


@router.post("/control/drill")
async def control_drill(cmd: DrillCommand):
    """
    Send drill motor command.

    Command values:
    - -2: Clockwise rotation
    - -1: Decrease speed
    - 0: Stop motor
    - 1: Increase speed
    - 2: Counter-clockwise rotation
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503, detail="Not connected to ROS. Cannot send command."
        )

    success = ros_manager.publish_science_control(drill_cmd=cmd.command)

    if not success:
        return {
            "success": False,
            "message": "Failed to send drill command",
        }

    return {
        "success": True,
        "message": f"Drill command sent: {cmd.command}",
        "data": {"command": cmd.command},
    }


@router.post("/control/barrel")
async def control_barrel(cmd: BarrelCommand):
    """
    Send barrel motor command.

    Command values:
    - 1: Rotate 60 degrees
    - 0: Full step mode
    - 4: 1/4 microstep mode
    - 8: 1/8 microstep mode
    - 16: 1/16 microstep mode
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503, detail="Not connected to ROS. Cannot send command."
        )

    success = ros_manager.publish_science_control(barrel_cmd=cmd.command)

    if not success:
        return {
            "success": False,
            "message": "Failed to send barrel command",
        }

    return {
        "success": True,
        "message": f"Barrel command sent: {cmd.command}",
        "data": {"command": cmd.command},
    }


@router.post("/control/servo")
async def control_servo(cmd: ServoCommand):
    """
    Toggle PH servo position.
    Only works after barrel has rotated at least once.
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503, detail="Not connected to ROS. Cannot send command."
        )

    success = ros_manager.publish_science_control(servo_toggle=cmd.toggle)

    if not success:
        return {
            "success": False,
            "message": "Failed to send servo toggle command",
        }

    return {
        "success": True,
        "message": f"Servo toggle sent: {cmd.toggle}",
        "data": {"toggle": cmd.toggle},
    }


@router.post("/control/command")
async def send_full_command(cmd: ScienceControlCommand):
    """
    Send a complete science control command with all parameters.
    Use -6 for any field to indicate "no command" for that actuator.
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503, detail="Not connected to ROS. Cannot send command."
        )

    success = ros_manager.publish_science_control(
        linear_actuator_cmd=cmd.linear_actuator_cmd,
        drill_cmd=cmd.drill_cmd,
        barrel_cmd=cmd.barrel_cmd,
        servo_toggle=cmd.servo_toggle,
        science_module_toggle=cmd.science_module_toggle,
    )

    if not success:
        return {
            "success": False,
            "message": "Failed to send full control command",
        }

    return {
        "success": True,
        "message": "Full control command sent",
        "data": {
            "linear_actuator_cmd": cmd.linear_actuator_cmd,
            "drill_cmd": cmd.drill_cmd,
            "barrel_cmd": cmd.barrel_cmd,
            "servo_toggle": cmd.servo_toggle,
            "science_module_toggle": cmd.science_module_toggle,
        },
    }


@router.get("/control/status")
async def get_control_status():
    """
    Get ROS connection status for science control.
    """
    status = ros_manager.get_status()

    return {
        "success": True,
        "message": "Control status retrieved",
        "data": {
            "ros_connected": status["connected"],
            "ros_url": status["url"],
            "can_send_commands": status["connected"],
        },
    }
