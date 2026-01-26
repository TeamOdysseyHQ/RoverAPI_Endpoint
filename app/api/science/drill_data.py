"""Science drill telemetry and warning endpoints"""

from fastapi import APIRouter, HTTPException
from app.ros.manager import ros_manager
from app.ros.topics import SCIENCE_DRILL_DATA_TOPIC, SCIENCE_INFO_WARNING_TOPIC
import time

router = APIRouter()

# Warning code meanings
WARNING_CODES = {
    1: "Start drilling",
    2: "Stop drilling (depth limit reached)",
    3: "Shake detected",
    4: "Current threshold 1 exceeded",
    5: "Current threshold 2 exceeded (drill auto-stopped)",
}


@router.post("/drill/subscribe")
async def subscribe_to_drill_data():
    """
    Subscribe to drill telemetry topic.
    Must be called before getting drill data.
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to ROS. Cannot subscribe to drill data.",
        )

    success = ros_manager.subscribe_drill_data()

    if not success:
        return {
            "success": False,
            "message": f"Failed to subscribe to {SCIENCE_DRILL_DATA_TOPIC}",
        }

    return {
        "success": True,
        "message": f"Successfully subscribed to {SCIENCE_DRILL_DATA_TOPIC}",
    }


@router.get("/drill/data")
async def get_drill_data():
    """
    Get latest drill telemetry data.

    Returns:
    - drill_halted: Whether drill is currently stopped
    - distance_mm: Distance measurement from VL53L0X sensor
    - accelerometer: x, y, z acceleration values
    - gyroscope: x, y, z gyro values
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503, detail="Not connected to ROS. Cannot get drill data."
        )

    # Auto-subscribe if not already subscribed
    if SCIENCE_DRILL_DATA_TOPIC not in ros_manager._subscribers:
        success = ros_manager.subscribe_drill_data()
        if not success:
            raise HTTPException(
                status_code=500, detail="Failed to subscribe to drill data topic"
            )
        # Wait a moment for first message
        time.sleep(0.5)

    data = ros_manager.get_latest_drill_data()

    if data is None:
        # Wait a bit longer for data
        time.sleep(1.0)
        data = ros_manager.get_latest_drill_data()

        if data is None:
            return {
                "success": False,
                "message": "No drill data received yet. Ensure science module is publishing.",
                "data": None,
            }

    return {
        "success": True,
        "message": "Drill data retrieved",
        "data": data,
    }


@router.post("/warnings/subscribe")
async def subscribe_to_warnings():
    """
    Subscribe to science info/warning codes topic.

    Warning codes:
    1 = Start drilling
    2 = Stop drilling (depth limit)
    3 = Shake detected
    4 = Current threshold 1 exceeded
    5 = Current threshold 2 exceeded (drill auto-stopped)
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to ROS. Cannot subscribe to warnings.",
        )

    success = ros_manager.subscribe_science_warnings()

    if not success:
        return {
            "success": False,
            "message": f"Failed to subscribe to {SCIENCE_INFO_WARNING_TOPIC}",
        }

    return {
        "success": True,
        "message": f"Successfully subscribed to {SCIENCE_INFO_WARNING_TOPIC}",
    }


@router.get("/warnings")
async def get_latest_warning():
    """
    Get the latest warning code from science module.
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503, detail="Not connected to ROS. Cannot get warnings."
        )

    # Auto-subscribe if not already subscribed
    if SCIENCE_INFO_WARNING_TOPIC not in ros_manager._subscribers:
        success = ros_manager.subscribe_science_warnings()
        if not success:
            raise HTTPException(
                status_code=500, detail="Failed to subscribe to warnings topic"
            )
        time.sleep(0.5)

    warning_code = ros_manager.get_latest_science_warning()

    if warning_code is None:
        return {
            "success": True,
            "message": "No warnings received",
            "data": {"warning_code": None, "warning_message": "No active warnings"},
        }

    warning_message = WARNING_CODES.get(
        warning_code, f"Unknown warning code: {warning_code}"
    )

    return {
        "success": True,
        "message": "Warning retrieved",
        "data": {
            "warning_code": warning_code,
            "warning_message": warning_message,
        },
    }


@router.get("/warnings/codes")
async def get_warning_codes():
    """
    Get all possible warning codes and their meanings.
    """
    return {
        "success": True,
        "message": "Warning codes retrieved",
        "data": WARNING_CODES,
    }
