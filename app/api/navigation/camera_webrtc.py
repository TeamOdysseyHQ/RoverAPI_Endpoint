"""
WebRTC-based camera streaming for navigation cameras.

Provides low-latency, bandwidth-efficient video streaming using
H.264/VP8 codec via WebRTC peer connections. This is an alternative
to the existing WebSocket (camera_ws.py) and MJPEG (camera.py) streams.

Endpoints:
    POST /cameras/{camera_name}/webrtc/offer  - SDP offer/answer exchange
    DELETE /cameras/{camera_name}/webrtc       - Close all WebRTC connections
    GET /cameras/{camera_name}/webrtc/status   - Connection status
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from app.api.webrtc_utils import (
    handle_offer,
    close_all_connections,
    get_connection_count,
    get_all_webrtc_stats,
    MAX_WEBRTC_CLIENTS_PER_SOURCE,
)

router = APIRouter()


class WebRTCOfferRequest(BaseModel):
    """SDP offer from the client."""

    sdp: str
    type: str = "offer"
    fps: Optional[int] = 30


@router.post("/cameras/{camera_name}/webrtc/offer")
async def webrtc_offer(
    camera_name: str,
    request: WebRTCOfferRequest,
):
    """
    Establish a WebRTC peer connection for camera streaming.

    Send an SDP offer and receive an SDP answer. The server will
    stream H.264/VP8 encoded video from the specified camera.

    This provides better bandwidth efficiency than WebSocket JPEG streaming
    due to inter-frame compression, and lower latency than MJPEG due to
    UDP transport.

    Example request:
    ```json
    {
        "sdp": "v=0\\r\\no=- ...",
        "type": "offer",
        "fps": 30
    }
    ```
    """
    from app.api.navigation.camera import camera_manager, CAMERA_DEVICES

    # Validate camera name
    if camera_name not in CAMERA_DEVICES:
        raise HTTPException(
            status_code=404,
            detail=f"Camera '{camera_name}' not found. "
            f"Available: {', '.join(CAMERA_DEVICES.keys())}",
        )

    # Check if camera is started
    status = camera_manager.get_camera_status(camera_name)
    if not status["active"]:
        raise HTTPException(
            status_code=400,
            detail=f"Camera '{camera_name}' not started. "
            f"Call /cameras/{camera_name}/start first",
        )

    fps = max(1, min(60, request.fps or 30))

    # Create a capture function bound to this camera
    def capture():
        return camera_manager.capture_frame(camera_name)

    source_name = f"camera:{camera_name}"

    try:
        answer = await handle_offer(
            source_name=source_name,
            sdp=request.sdp,
            sdp_type=request.type,
            capture_fn=capture,
            fps=fps,
        )
    except ValueError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create WebRTC connection: {e}",
        )

    return {
        "success": True,
        "sdp": answer["sdp"],
        "type": answer["type"],
        "camera_name": camera_name,
        "fps": fps,
    }


@router.delete("/cameras/{camera_name}/webrtc")
async def webrtc_close(camera_name: str):
    """Close all WebRTC connections for a camera."""
    source_name = f"camera:{camera_name}"
    closed = await close_all_connections(source_name)
    return {
        "success": True,
        "message": f"Closed {closed} WebRTC connection(s) for camera '{camera_name}'",
        "closed": closed,
    }


@router.get("/cameras/{camera_name}/webrtc/status")
async def webrtc_status(camera_name: str):
    """Get WebRTC connection status for a camera."""
    source_name = f"camera:{camera_name}"
    count = await get_connection_count(source_name)
    return {
        "success": True,
        "camera_name": camera_name,
        "active_connections": count,
        "max_connections": MAX_WEBRTC_CLIENTS_PER_SOURCE,
    }


@router.get("/cameras/webrtc/status")
async def webrtc_all_status():
    """Get WebRTC connection status for all cameras."""
    stats = await get_all_webrtc_stats()
    return {
        "success": True,
        "sources": stats,
    }
