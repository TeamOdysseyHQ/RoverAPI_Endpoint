from fastapi import APIRouter, Request

router = APIRouter()

@router.post("/test")
async def api_test_point(request: Request):
    data = await request.json() if request.headers.get("content-type") == "application/json" else None
    
    return {
        "success": True,
        "status": "Success",
        "message": "The POST Request was successfully validated. Check the data we received.",
        "data": data
    }