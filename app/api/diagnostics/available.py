from fastapi import APIRouter
from app.py_types import listOfStrings

router = APIRouter()

def dgt_avi_l_ret() -> listOfStrings:
    
    #* Add all endpoints here without fail.
    return [
        "available", "doctor"
    ]

@router.post("/available")
async def dgt_avi():
    return {
        "success": True,
        "status": "Success",
        "endpoints": dgt_avi_l_ret()
    }