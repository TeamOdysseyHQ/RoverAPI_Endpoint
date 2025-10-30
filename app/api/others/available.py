from fastapi import APIRouter
from app.py_types import listOfStrings

router = APIRouter()

def o_avi_l_ret() -> listOfStrings:
    
    #* Add all endpoints here without fail.
    return [
        "available", "test"
    ]

@router.post("/available")
async def o_avi():
    return {
        "success": True,
        "status": "Success",
        "endpoints": o_avi_l_ret()
    }