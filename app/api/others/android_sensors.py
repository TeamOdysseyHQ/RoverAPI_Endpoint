"""
Android sensor data relay endpoint.

This module provides WebSocket endpoints to relay sensor data from an Android device
to the dashboard. The Android device connects to port 8989 on the rover via socket,
and this endpoint broadcasts that data to dashboard clients via WebSocket.

Endpoints:
    WS /android/sensors/ws - Live sensor data streaming
    GET /android/sensors/status - Connection status and latest readings
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from typing import Dict, List, Optional, Any
import asyncio
import json
import socket
import threading
import time
from datetime import datetime

router = APIRouter()

# Android sensor server configuration
ANDROID_SENSOR_PORT = 8989
ANDROID_HOST = "127.0.0.1"

# Latest sensor readings (shared state)
latest_sensor_data: Dict[str, Any] = {
    "gps": None,
    "accelerometer": None,
    "gyroscope": None,
    "compass": None,
    "connected": False,
    "last_update": None,
}

# WebSocket connection manager
active_dashboard_clients: List[WebSocket] = []
clients_lock = asyncio.Lock()

# Android socket connection
android_socket: Optional[socket.socket] = None
android_connected = False
android_thread: Optional[threading.Thread] = None
stop_android_listener = False


def connect_to_android() -> bool:
    """
    Connect to the Android sensor socket server.

    Returns:
        bool: True if connection successful, False otherwise
    """
    global android_socket, android_connected

    try:
        android_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        android_socket.settimeout(5)
        android_socket.connect((ANDROID_HOST, ANDROID_SENSOR_PORT))
        android_socket.settimeout(None)
        android_connected = True
        latest_sensor_data["connected"] = True
        print(
            f"Connected to Android sensor server at {ANDROID_HOST}:{ANDROID_SENSOR_PORT}"
        )
        return True
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        print(f"Failed to connect to Android sensor server: {e}")
        android_socket = None
        android_connected = False
        latest_sensor_data["connected"] = False
        return False


def listen_to_android():
    """
    Background thread that listens to Android socket and updates shared state.
    """
    global android_socket, android_connected, stop_android_listener, latest_sensor_data

    while not stop_android_listener:
        if not android_connected:
            # Try to reconnect
            if connect_to_android():
                print("Reconnected to Android sensor server")
            else:
                time.sleep(5)  # Wait before retrying
                continue

        try:
            if android_socket:
                file_obj = android_socket.makefile()
                line = file_obj.readline()

                if not line:
                    print("Android connection closed")
                    android_connected = False
                    latest_sensor_data["connected"] = False
                    if android_socket:
                        android_socket.close()
                        android_socket = None
                    continue

                try:
                    data = json.loads(line.strip())
                    sensor_type = data.get("type")

                    # Update shared state based on sensor type
                    if sensor_type in ["gps", "accelerometer", "gyroscope", "compass"]:
                        latest_sensor_data[sensor_type] = data
                        latest_sensor_data["last_update"] = datetime.now().isoformat()

                        # Broadcast to all connected dashboard clients
                        asyncio.run(broadcast_to_clients(data))

                except json.JSONDecodeError:
                    pass  # Ignore non-JSON lines

        except Exception as e:
            print(f"Error reading from Android socket: {e}")
            android_connected = False
            latest_sensor_data["connected"] = False
            if android_socket:
                android_socket.close()
                android_socket = None
            time.sleep(5)


async def broadcast_to_clients(data: Dict[str, Any]):
    """
    Broadcast sensor data to all connected dashboard WebSocket clients.

    Args:
        data: Sensor data dictionary to broadcast
    """
    async with clients_lock:
        disconnected = []
        for client in active_dashboard_clients:
            try:
                await client.send_json(data)
            except Exception:
                disconnected.append(client)

        # Remove disconnected clients
        for client in disconnected:
            active_dashboard_clients.remove(client)


def start_android_listener():
    """
    Start the background thread for Android sensor listening.
    """
    global android_thread, stop_android_listener

    if android_thread is None or not android_thread.is_alive():
        stop_android_listener = False
        android_thread = threading.Thread(target=listen_to_android, daemon=True)
        android_thread.start()
        print("Started Android sensor listener thread")


def stop_android_listener_thread():
    """
    Stop the background thread for Android sensor listening.
    """
    global stop_android_listener, android_socket, android_connected

    stop_android_listener = True
    android_connected = False
    if android_socket:
        android_socket.close()
        android_socket = None


# Start listener on module import
start_android_listener()


@router.websocket("/android/sensors/ws")
async def android_sensors_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for streaming Android sensor data to dashboard.

    Protocol:
        Server -> Client: JSON messages with sensor readings
        {
            "type": "gps" | "accelerometer" | "gyroscope" | "compass",
            ... sensor-specific fields
        }

    Connection lifecycle:
        1. Client connects
        2. Server sends latest readings (if available)
        3. Server streams live updates as they arrive from Android
        4. Client disconnects or connection lost
    """
    await websocket.accept()

    async with clients_lock:
        active_dashboard_clients.append(websocket)

    try:
        # Send latest readings on connect
        for sensor_type in ["gps", "accelerometer", "gyroscope", "compass"]:
            data = latest_sensor_data.get(sensor_type)
            if data:
                await websocket.send_json(data)

        # Send connection status
        await websocket.send_json(
            {
                "type": "status",
                "connected": latest_sensor_data["connected"],
                "last_update": latest_sensor_data["last_update"],
            }
        )

        # Keep connection alive and listen for client messages (optional)
        while True:
            # Wait for client messages (can be used for control messages)
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                # Process client commands if needed
            except asyncio.TimeoutError:
                # Send keepalive ping
                await websocket.send_json({"type": "ping"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        async with clients_lock:
            if websocket in active_dashboard_clients:
                active_dashboard_clients.remove(websocket)


@router.get("/android/sensors/status")
async def get_android_sensor_status():
    """
    Get current Android sensor connection status and latest readings.

    Returns:
        {
            "success": bool,
            "connected": bool,
            "last_update": str (ISO timestamp),
            "sensors": {
                "gps": {...},
                "accelerometer": {...},
                "gyroscope": {...},
                "compass": {...}
            }
        }
    """
    return {
        "success": True,
        "connected": latest_sensor_data["connected"],
        "last_update": latest_sensor_data["last_update"],
        "sensors": {
            "gps": latest_sensor_data.get("gps"),
            "accelerometer": latest_sensor_data.get("accelerometer"),
            "gyroscope": latest_sensor_data.get("gyroscope"),
            "compass": latest_sensor_data.get("compass"),
        },
    }
