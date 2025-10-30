
from fastapi import FastAPI
from app.api.router import router

app = FastAPI(
    title="RoverAPI Endpoint",
    description="FastAPI-based Rover Control and Data Collection API",
    version="2.0.0"
)

app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
