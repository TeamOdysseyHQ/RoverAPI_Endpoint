"""
WebRTC-based streaming for the science microscope.

Provides low-latency, bandwidth-efficient video streaming using
H.264/VP8 codec via WebRTC peer connections as an alternative to
the existing WebSocket and MJPEG streams.

Endpoints:
    POST /microscope/webrtc/offer   - SDP offer/answer exchange
    DELETE /microscope/webrtc       - Close all WebRTC connections
    GET /microscope/webrtc/status   - Connection status
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.api.science.microscope import microscope_manager
from app.api.webrtc_utils import (
    handle_offer,
    close_all_connections,
    get_connection_count,
    MAX_WEBRTC_CLIENTS_PER_SOURCE,
)

router = APIRouter()

SOURCE_NAME = "microscope"


class WebRTCOfferRequest(BaseModel):
    """SDP offer from the client."""

    sdp: str
    type: str = "offer"
    fps: Optional[int] = 30


@router.post("/microscope/webrtc/offer")
async def webrtc_offer(request: WebRTCOfferRequest):
    """
    Establish a WebRTC peer connection for microscope streaming.

    Send an SDP offer and receive an SDP answer.

    Example request:
    ```json
    {
        "sdp": "v=0\\r\\no=- ...",
        "type": "offer",
        "fps": 30
    }
    ```
    """
    status = microscope_manager.get_status()
    if not status["active"]:
        raise HTTPException(
            status_code=400,
            detail="Microscope not started. Call /microscope/start first",
        )

    fps = max(1, min(60, request.fps or 30))

    try:
        answer = await handle_offer(
            source_name=SOURCE_NAME,
            sdp=request.sdp,
            sdp_type=request.type,
            capture_fn=microscope_manager.capture_frame,
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
        "fps": fps,
    }


@router.delete("/microscope/webrtc")
async def webrtc_close():
    """Close all WebRTC connections for the microscope."""
    closed = await close_all_connections(SOURCE_NAME)
    return {
        "success": True,
        "message": f"Closed {closed} WebRTC connection(s) for microscope",
        "closed": closed,
    }


@router.get("/microscope/webrtc/status")
async def webrtc_status():
    """Get WebRTC connection status for the microscope."""
    count = await get_connection_count(SOURCE_NAME)
    return {
        "success": True,
        "active_connections": count,
        "max_connections": MAX_WEBRTC_CLIENTS_PER_SOURCE,
    }
