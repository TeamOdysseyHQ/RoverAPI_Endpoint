from fastapi import APIRouter
from typing import Union
from app.ros.manager import ros_manager
from app.ros.topics import ARM_TELEMETRY_TOPIC
import time

router = APIRouter()

ArmSensorData = dict[str, dict[str, Union[str, int, float]]]


class SensorDataFetchFailure(Exception):
    def __init__(self, msg: str, *args):
        super().__init__(msg, *args)
        self.msg = msg

    def __str__(self):
        return f"Failed to obtain sensor data: {self.msg}"


def arm_data_handler():
    sensor_data: ArmSensorData = {}
    # fetch sensor data

    if not ros_manager.is_connected:
        raise SensorDataFetchFailure("Not connected to ROS. Cannot fetch arm data.")

    if ARM_TELEMETRY_TOPIC not in ros_manager._subscribers:
        success = ros_manager.subscribe_arm_telemetry()
        if not success:
            raise SensorDataFetchFailure(
                f"Failed to subscribe to {ARM_TELEMETRY_TOPIC}"
            )

    time.sleep(0.5)
    data = ros_manager.get_latest_arm_telemetry()

    if data is None:
        time.sleep(1.0)
        data = ros_manager.get_latest_arm_telemetry()

        if data is None:
            raise SensorDataFetchFailure("No data received from arm.")

    # Data is already parsed by ros_manager.get_latest_arm_telemetry()
    # Format: {"stepper": {...}, "dc": {...}, "servo": {...}, "rc_channels": {...}}

    sensor_data = {
        "servo": {
            "wrist_roll": data["servo"]["wrist_roll"],
            "gripper": data["servo"]["gripper"],
        },
        "dc": {
            "elbow": data["dc"]["elbow"],
            "wrist_pitch": data["dc"]["wrist_pitch"],
        },
        "stepper": {
            "base_pan": data["stepper"]["base_pan"],
            "shoulder": data["stepper"]["shoulder"],
        },
    }

    return sensor_data


@router.post("/data")
async def arm_data():
    try:
        data = arm_data_handler()
        return {
            "success": True,
            "status": "Success",
            "message": "Successfully fetched arm data.",
            "data": data,
        }
    except SensorDataFetchFailure as sdf:
        return {
            "success": False,
            "status": "Failure",
            "message": str(sdf),
            "data": None,
        }
