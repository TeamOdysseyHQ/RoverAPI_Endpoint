from fastapi import APIRouter, Request, HTTPException
import asyncio
from app.ros.manager import ros_manager
from app.ros.topics import TEST_TOPIC

router = APIRouter()

@router.post("/test")
async def api_test_point(request: Request):
    data = (
        await request.json()
        if request.headers.get("content-type") == "application/json"
        else None
    )

    return {
        "success": True,
        "status": "Success",
        "message": "The POST Request was successfully validated. Check the data we received.",
        "data": data,
    }