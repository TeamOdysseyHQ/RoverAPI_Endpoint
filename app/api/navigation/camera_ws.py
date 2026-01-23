"""
WebSocket-based camera streaming for low-latency video transmission.

This module provides real-time video streaming over WebSocket connections,
offering significantly lower latency compared to MJPEG streaming.

Protocol:
    Binary frames: [24-byte header] + [JPEG data]
    Control messages: JSON text messages

Endpoints:
    WS /cameras/{camera_index}/ws - Video streaming with configurable quality/fps
    GET /cameras/ws/status - WebSocket connection statistics
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from typing import Dict, List, Optional
import asyncio
import struct
import time
import json
import cv2
import numpy as np

router = APIRouter()

# Protocol constants
MAGIC_NUMBER = 0x524F5652  # "ROVR" in ASCII
HEADER_SIZE = 24
MAX_CLIENTS_PER_CAMERA = 5
DEFAULT_QUALITY = 85
DEFAULT_FPS = 30


def encode_frame(
    frame: np.ndarray,
    camera_index: int,
    frame_number: int,
    quality: int = DEFAULT_QUALITY,
) -> bytes:
    """
    Encode frame with binary header + JPEG data.

    Frame Format:
        Header (24 bytes):
            - magic_number: 4 bytes (0x524F5652 - "ROVR")
            - camera_index: 4 bytes (int32)
            - timestamp_us: 8 bytes (int64) - microseconds since epoch
            - frame_number: 4 bytes (uint32)
            - jpeg_quality: 1 byte (uint8)
            - reserved: 3 bytes (padding)

        Data:
            - JPEG encoded image bytes (variable length)

    Args:
        frame: OpenCV frame (numpy array)
        camera_index: Camera identifier
        frame_number: Sequential frame number
        quality: JPEG quality (0-100)

    Returns:
        Binary message: header + JPEG bytes

    Raises:
        ValueError: If frame encoding fails
    """
    # Encode frame as JPEG
    encode_param = [cv2.IMWRITE_JPEG_QUALITY, quality]
    ret, buffer = cv2.imencode(".jpg", frame, encode_param)

    if not ret:
        raise ValueError("Failed to encode frame as JPEG")

    # Get current timestamp in microseconds
    timestamp_us = int(time.time() * 1_000_000)

    # Pack header (little-endian format)
    # Format: I (uint32), i (int32), Q (uint64), I (uint32), B (uint8), 3x (padding)
    header = struct.pack(
        "<IiQIBxxx", MAGIC_NUMBER, camera_index, timestamp_us, frame_number, quality
    )

    # Combine header + JPEG data
    return header + buffer.tobytes()


class WebSocketConnectionManager:
    """
    Manages WebSocket connections for camera streaming.

    Handles connection lifecycle, client tracking, and message broadcasting
    for multiple cameras with multiple clients per camera.
    """

    def __init__(self):
        # camera_index -> list of WebSocket connections
        self.active_connections: Dict[int, List[WebSocket]] = {}
        self.lock = asyncio.Lock()

        # Statistics tracking
        self.connection_stats: Dict[int, dict] = {}

    async def connect(self, camera_index: int, websocket: WebSocket) -> bool:
        """
        Accept and register new WebSocket connection.

        Args:
            camera_index: Camera identifier
            websocket: WebSocket connection to register

        Returns:
            True if connection accepted, False if rejected (too many clients)
        """
        async with self.lock:
            # Check connection limit
            current_count = len(self.active_connections.get(camera_index, []))
            if current_count >= MAX_CLIENTS_PER_CAMERA:
                return False

            # Accept connection
            await websocket.accept()

            # Register connection
            if camera_index not in self.active_connections:
                self.active_connections[camera_index] = []
            self.active_connections[camera_index].append(websocket)

            # Initialize stats
            if camera_index not in self.connection_stats:
                self.connection_stats[camera_index] = {
                    "total_connected": 0,
                    "total_disconnected": 0,
                    "frames_sent": 0,
                    "errors": 0,
                }
            self.connection_stats[camera_index]["total_connected"] += 1

        print(
            f"[WS] Client connected to camera {camera_index} ({current_count + 1} total)"
        )
        return True

    async def disconnect(self, camera_index: int, websocket: WebSocket):
        """
        Remove WebSocket connection and cleanup.

        Args:
            camera_index: Camera identifier
            websocket: WebSocket connection to remove
        """
        async with self.lock:
            if camera_index in self.active_connections:
                if websocket in self.active_connections[camera_index]:
                    self.active_connections[camera_index].remove(websocket)

                    if camera_index in self.connection_stats:
                        self.connection_stats[camera_index]["total_disconnected"] += 1

                # Clean up empty lists
                if not self.active_connections[camera_index]:
                    del self.active_connections[camera_index]

        remaining = len(self.active_connections.get(camera_index, []))
        print(
            f"[WS] Client disconnected from camera {camera_index} ({remaining} remaining)"
        )

    async def send_to_client(
        self, camera_index: int, websocket: WebSocket, message: bytes
    ) -> bool:
        """
        Send binary message to specific client.

        Args:
            camera_index: Camera identifier
            websocket: Target WebSocket connection
            message: Binary message to send

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            await websocket.send_bytes(message)

            # Update stats
            if camera_index in self.connection_stats:
                self.connection_stats[camera_index]["frames_sent"] += 1

            return True
        except Exception as e:
            print(f"[WS] Error sending to client: {e}")

            # Update error stats
            if camera_index in self.connection_stats:
                self.connection_stats[camera_index]["errors"] += 1

            return False

    async def send_json(self, websocket: WebSocket, data: dict) -> bool:
        """
        Send JSON message to specific client.

        Args:
            websocket: Target WebSocket connection
            data: Dictionary to send as JSON

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            await websocket.send_json(data)
            return True
        except Exception as e:
            print(f"[WS] Error sending JSON: {e}")
            return False

    def get_connection_count(self, camera_index: int) -> int:
        """Get number of active connections for camera."""
        return len(self.active_connections.get(camera_index, []))

    def get_stats(self, camera_index: int) -> dict:
        """Get connection statistics for camera."""
        return self.connection_stats.get(
            camera_index,
            {
                "total_connected": 0,
                "total_disconnected": 0,
                "frames_sent": 0,
                "errors": 0,
            },
        )

    def get_all_stats(self) -> dict:
        """Get statistics for all cameras."""
        return {
            cam_idx: {
                **self.get_stats(cam_idx),
                "active_connections": self.get_connection_count(cam_idx),
            }
            for cam_idx in set(
                list(self.active_connections.keys())
                + list(self.connection_stats.keys())
            )
        }


# Global WebSocket connection manager
ws_manager = WebSocketConnectionManager()


@router.websocket("/cameras/{camera_index}/ws")
async def camera_stream_ws(
    websocket: WebSocket,
    camera_index: int,
    quality: int = Query(DEFAULT_QUALITY, ge=1, le=100),
    fps: int = Query(DEFAULT_FPS, ge=1, le=60),
):
    """
    WebSocket endpoint for real-time camera streaming.

    Provides low-latency video streaming using binary WebSocket frames.
    Each frame consists of a 24-byte header followed by JPEG image data.

    Query Parameters:
        quality: JPEG quality (1-100, default 85)
        fps: Target frames per second (1-60, default 30)

    Protocol:
        Client -> Server:
            - Text messages (JSON) for control commands
            - Supported commands: ping, set_quality

        Server -> Client:
            - Binary messages: encoded video frames
            - JSON messages: status updates, acknowledgments

    Connection Flow:
        1. Client connects
        2. Server sends initial status (JSON)
        3. Server streams binary frames at configured FPS
        4. Client can send control messages anytime
        5. Connection closed on error or client disconnect

    Example:
        ws://localhost:6767/api/nav/cameras/0/ws?quality=85&fps=30
    """
    # Import camera manager
    from app.api.navigation.camera import camera_manager

    # Check if camera is started
    status = camera_manager.get_camera_status(camera_index)
    if not status["active"]:
        await websocket.close(
            code=4000,
            reason=f"Camera {camera_index} not started. Call /cameras/{camera_index}/start first",
        )
        return

    # Check connection limit
    if ws_manager.get_connection_count(camera_index) >= MAX_CLIENTS_PER_CAMERA:
        await websocket.close(
            code=4001, reason=f"Too many clients connected to camera {camera_index}"
        )
        return

    # Accept connection
    connection_accepted = await ws_manager.connect(camera_index, websocket)
    if not connection_accepted:
        await websocket.close(code=4001, reason="Connection limit reached")
        return

    # Register with camera manager
    camera_manager.add_ws_client(camera_index, websocket)

    # Send initial status
    await ws_manager.send_json(
        websocket,
        {
            "type": "status",
            "camera_index": camera_index,
            "connected": True,
            "quality": quality,
            "fps": fps,
            "resolution": f"{status['width']}x{status['height']}",
            "max_clients": MAX_CLIENTS_PER_CAMERA,
            "current_clients": ws_manager.get_connection_count(camera_index),
        },
    )

    # Streaming configuration
    frame_number = 0
    frame_delay = 1.0 / fps
    current_quality = quality

    try:
        # Main streaming loop
        while True:
            # Check for control messages (non-blocking with short timeout)
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.01)

                # Handle control message
                response = await handle_control_message(data, current_quality)
                if response:
                    await ws_manager.send_json(websocket, response)

                    # Update quality if changed
                    if response.get("type") == "ack" and "quality" in response:
                        current_quality = response["quality"]

            except asyncio.TimeoutError:
                # No control message, continue streaming
                pass
            except WebSocketDisconnect:
                # Client disconnected
                raise

            # Capture frame
            frame = camera_manager.capture_frame(camera_index)
            if frame is not None:
                try:
                    # Encode frame with header
                    binary_message = encode_frame(
                        frame, camera_index, frame_number, current_quality
                    )

                    # Send to client
                    success = await ws_manager.send_to_client(
                        camera_index, websocket, binary_message
                    )

                    if success:
                        frame_number += 1
                    else:
                        # Send failed, likely disconnected
                        break

                except ValueError as e:
                    print(f"[WS] Frame encoding error: {e}")
                except Exception as e:
                    print(f"[WS] Error processing frame: {e}")
                    break

            # Frame rate control
            await asyncio.sleep(frame_delay)

    except WebSocketDisconnect:
        print(f"[WS] Client disconnected from camera {camera_index}")
    except Exception as e:
        print(f"[WS] Error in streaming loop: {e}")
    finally:
        # Cleanup
        camera_manager.remove_ws_client(camera_index, websocket)
        await ws_manager.disconnect(camera_index, websocket)


async def handle_control_message(message: str, current_quality: int) -> Optional[dict]:
    """
    Handle JSON control messages from client.

    Supported message types:
        - ping: Health check, responds with pong
        - control: Configuration changes (quality, fps)

    Args:
        message: JSON string from client
        current_quality: Current JPEG quality setting

    Returns:
        Response dictionary to send back to client, or None
    """
    try:
        data = json.loads(message)
        msg_type = data.get("type")

        if msg_type == "ping":
            # Respond to ping
            return {"type": "pong", "timestamp": time.time()}

        elif msg_type == "control":
            action = data.get("action")

            if action == "set_quality":
                quality = data.get("params", {}).get("quality", current_quality)
                quality = max(1, min(100, quality))  # Clamp to valid range

                return {
                    "type": "ack",
                    "action": "set_quality",
                    "quality": quality,
                    "message": f"Quality set to {quality}",
                }

            elif action == "get_info":
                return {
                    "type": "info",
                    "quality": current_quality,
                    "protocol_version": "1.0",
                    "header_size": HEADER_SIZE,
                }

        return None

    except json.JSONDecodeError:
        print(f"[WS] Invalid JSON from client: {message}")
        return {"type": "error", "message": "Invalid JSON format"}
    except Exception as e:
        print(f"[WS] Error handling control message: {e}")
        return {"type": "error", "message": str(e)}


@router.get("/cameras/ws/status")
async def get_websocket_status():
    """
    Get WebSocket streaming status and statistics.

    Returns connection counts, frame statistics, and error counts
    for all cameras with active or historical WebSocket connections.

    Response:
        {
            "status": "ok",
            "cameras": {
                "0": {
                    "active_connections": 2,
                    "total_connected": 5,
                    "total_disconnected": 3,
                    "frames_sent": 1234,
                    "errors": 0,
                    "camera_active": true,
                    "resolution": "640x480",
                    "fps": 30
                }
            },
            "total_active_connections": 2,
            "max_clients_per_camera": 5
        }
    """
    from app.api.navigation.camera import camera_manager

    # Get statistics for all cameras
    all_stats = ws_manager.get_all_stats()

    # Enhance with camera info
    cameras_status = {}
    for camera_index in all_stats.keys():
        camera_status = camera_manager.get_camera_status(camera_index)

        cameras_status[str(camera_index)] = {
            **all_stats[camera_index],
            "camera_active": camera_status["active"],
            "resolution": f"{camera_status.get('width', 0)}x{camera_status.get('height', 0)}",
            "fps": camera_status.get("fps", 0),
        }

    # Calculate totals
    total_active = sum(
        ws_manager.get_connection_count(cam_idx) for cam_idx in all_stats.keys()
    )

    return {
        "status": "ok",
        "cameras": cameras_status,
        "total_active_connections": total_active,
        "max_clients_per_camera": MAX_CLIENTS_PER_CAMERA,
    }


@router.get("/cameras/{camera_index}/ws/status")
async def get_camera_websocket_status(camera_index: int):
    """
    Get WebSocket streaming status for specific camera.

    Args:
        camera_index: Camera identifier

    Returns:
        Detailed WebSocket statistics and camera info for the specified camera

    Raises:
        HTTPException: 404 if camera not found
    """
    from app.api.navigation.camera import camera_manager

    camera_status = camera_manager.get_camera_status(camera_index)
    if not camera_status["active"]:
        raise HTTPException(
            status_code=404, detail=f"Camera {camera_index} not found or not started"
        )

    ws_stats = ws_manager.get_stats(camera_index)

    return {
        "status": "ok",
        "camera_index": camera_index,
        "camera_active": camera_status["active"],
        "resolution": f"{camera_status['width']}x{camera_status['height']}",
        "fps": camera_status["fps"],
        "websocket": {
            "active_connections": ws_manager.get_connection_count(camera_index),
            "max_connections": MAX_CLIENTS_PER_CAMERA,
            **ws_stats,
        },
    }
