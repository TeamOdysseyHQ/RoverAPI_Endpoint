from fastapi import APIRouter
from typing import Union
from app.ros.manager import ros_manager
from app.ros.topics import SCIENCE_DATA_TOPIC
import time
    
router = APIRouter()

SensorData = dict[str, Union[str, int, float]]

class SensorDataFetchFailure(Exception):
    
    def __init__(self, msg: str, *args):
        super().__init__(msg, *args)
        self.msg = msg
    
    def __str__(self):
        return f"Failed to obtain sensor data: {self.msg}"

def sci_sensor_data_handler():
    sensor_data: SensorData = {}
    # fetch sensor data

    if not ros_manager.is_connected:
        raise SensorDataFetchFailure("Not connected to ROS. Cannot fetch sensor data.")
    
    if SCIENCE_DATA_TOPIC not in ros_manager._subscribers:
        success = ros_manager.subscribe(SCIENCE_DATA_TOPIC, "std_msgs/Float32MultiArray")
        if not success:
            raise SensorDataFetchFailure(f"Failed to subscribe to {SCIENCE_DATA_TOPIC}")
            
    time.sleep(0.5)
    data = ros_manager.get_latest_message(SCIENCE_DATA_TOPIC)

    if data is None:
        time.sleep(1.0)
        data = ros_manager.get_latest_message(SCIENCE_DATA_TOPIC)
        
        if data is None:
            raise SensorDataFetchFailure("No data received from science sensors.")
        
    data = data["data"]  # Dict access, not attribute
    colourless = bool(data[0])
    purple = bool(data[1])
    humidity = data[2]

    N = data[3]
    P = data[4]
    K = data[5]

    ph = data[6]
    co2 = data[7]
    temp = data[8]
    press = data[9]
    alt = data[10]
    lat = data[11]
    lon = data[12]
    dist = data[13]

    sensor_data = {
        "cs_tcs_34725": f"Colourless: {'Yes' if colourless else 'No'}  Purple: {'Yes' if purple else 'No'}",
        "humidity": humidity,
        "NPK_sensor_nitrogen": N,
        "NPK_sensor_phos": P,
        "NPK_sensor_potassium": K,
        "ph": ph,
        "mq_135": co2,
        "gy-bmp280_temp": temp,
        "gy-bmp280_pressure": press,
        "gy-bmp280_altitude": alt,
        "gps": f"Lat: {lat}, Lon: {lon}",
        "vl53lox": dist
    }

    return sensor_data

@router.post("/sensor_data")
async def sci_sensor_data():

    try:
        data = sci_sensor_data_handler()
        return {
            "success": True,
            "status": "Success",
            "message": "Successfully fetched science sensor data.",
            "data": data,
        }
    except SensorDataFetchFailure as sdf:
        return {
            "success": False,
            "status": "Failure",
            "message": str(sdf),
            "data": None,
        }