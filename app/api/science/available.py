from fastapi import APIRouter
from app.py_types import listOfStrings
    
router = APIRouter()
    
def sci_avi_l_ret() -> listOfStrings:
    
    #* Add all endpoints here without fail.
    return [
        "available", "reports", "get_report"
    ]
    
@router.post("/available")
async def sci_avi():
    return {
        "success": True,
        "status": "Success",
        "endpoints": sci_avi_l_ret()
    }