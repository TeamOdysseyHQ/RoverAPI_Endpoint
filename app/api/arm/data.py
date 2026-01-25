from fastapi import APIRouter
from typing import Union
from app.ros.manager import ros_manager
from app.ros.topics import ARM_STATUS, ARM_COMMAND_TOPIC
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
    
    if ARM_STATUS not in ros_manager._subscribers:
        success = ros_manager.subscribe(ARM_STATUS, "std_msgs/Float32MultiArray")
        if not success:
            raise SensorDataFetchFailure(f"Failed to subscribe to {ARM_STATUS}")
            
    time.sleep(0.5)
    data = ros_manager.get_latest_message(ARM_STATUS)

    if data is None:
        time.sleep(1.0)
        data = ros_manager.get_latest_message(ARM_STATUS)
        
        if data is None:
            raise SensorDataFetchFailure("No data received from arm.")
        
    data = data["data"]  # Dict access, not attribute
    
    joint_1_servo = data[0]
    joint_2_servo = data[1]

    joint_1_dc = data[2]
    joint_2_dc = data[3]

    joint_1_stepper = data[4]
    joint_2_stepper = data[5]

    # servo, dc, stepper

    sensor_data = {
        "servo": {
            "joint_1_angle": joint_1_servo,
            "joint_2_angle": joint_2_servo,
        },
        "dc": {
            "joint_1_angle": joint_1_dc,
            "joint_2_angle": joint_2_dc,
        },
        "stepper": {
            "joint_1_angle": joint_1_stepper,
            "joint_2_angle": joint_2_stepper,
        }
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