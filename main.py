import logging
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router
from app.ros.manager import ros_manager

# Configure logging so WebRTC / aiortc diagnostics are visible
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

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
    print("Starting Rover API Server...")

    # Connect to rosbridge in a separate thread to avoid blocking startup
    def connect_ros():
        print("Attempting to connect to rosbridge_server...")
        success = ros_manager.connect()
        if success:
            print(f"Successfully connected to rosbridge at {ros_manager.config.url}")
        else:
            print(f"ERROR: Failed to connect to rosbridge at {ros_manager.config.url}")
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
    """Clean up WebRTC connections and disconnect from ROS bridge on shutdown"""
    print("Shutting down Rover API Server...")

    # Close all WebRTC peer connections gracefully
    from app.api.webrtc_utils import _peer_connections, _pc_lock

    async with _pc_lock:
        all_sources = list(_peer_connections.keys())

    if all_sources:
        from app.api.webrtc_utils import close_all_connections

        for source in all_sources:
            closed = await close_all_connections(source)
            if closed:
                print(f"  ✓ Closed {closed} WebRTC connection(s) for '{source}'")

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
