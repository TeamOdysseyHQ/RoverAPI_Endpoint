import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router
from app.ros.manager import ros_manager

app = FastAPI(
    title="RoverAPI Endpoint",
    description="FastAPI-based Rover Control and Data Collection API with ROS2 Integration",
    version="2.0.0",
)

# Add CORS middleware to allow frontend connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (restrict in production)
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, OPTIONS, etc.)
    allow_headers=["*"],  # Allow all headers
)

app.include_router(router)


@app.on_event("startup")
async def startup_event():
    """Initialize ROS bridge connection on startup"""
    print("🚀 Starting Rover API Server...")

    # Connect to rosbridge in a separate thread to avoid blocking startup
    def connect_ros():
        print("🔌 Attempting to connect to rosbridge_server...")
        success = ros_manager.connect()
        if success:
            print(f"✓ Successfully connected to rosbridge at {ros_manager.config.url}")
        else:
            print(f"✗ Failed to connect to rosbridge at {ros_manager.config.url}")
            print(
                "  ROS endpoints will not be available until connection is established."
            )
            print(
                "  Ensure rosbridge_server is running: ros2 launch rosbridge_server rosbridge_websocket_launch.xml"
            )

    # Start connection attempt in background
    thread = threading.Thread(target=connect_ros, daemon=True)
    thread.start()


@app.on_event("shutdown")
async def shutdown_event():
    """Disconnect from ROS bridge on shutdown"""
    print("🛑 Shutting down Rover API Server...")
    if ros_manager.is_connected:
        ros_manager.disconnect()
        print("✓ Disconnected from rosbridge")


@app.get("/")
async def root():
    """Root endpoint to verify server is running"""
    ros_status = "connected" if ros_manager.is_connected else "disconnected"
    return {
        "status": "ok",
        "message": "Rover API Server is running",
        "version": "2.0.0",
        "ros_bridge": ros_status,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=6767)
