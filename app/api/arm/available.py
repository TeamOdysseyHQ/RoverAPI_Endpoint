from fastapi import APIRouter
from app.py_types import listOfStrings

router = APIRouter()


def arm_avi_l_ret() -> listOfStrings:
    # * Add all endpoints here without fail.
    return [
        "available",
        "data",
        "ros/command",
        "ros/target",
        "ros/telemetry/subscribe",
        "ros/telemetry",
        "ros/drop",
        "ros/stop",
    ]


@router.post("/available")
async def arm_avi():
    return {"success": True, "status": "Success", "endpoints": arm_avi_l_ret()}
