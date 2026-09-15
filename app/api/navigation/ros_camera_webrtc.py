"""
WebRTC-based streaming for ROS camera image topics.

Provides low-latency, bandwidth-efficient video streaming using
H.264/VP8 codec via WebRTC peer connections as an alternative to
the existing MJPEG stream from ros_camera.py.

Endpoints:
    POST /ros/camera/webrtc/offer   - SDP offer/answer exchange
    DELETE /ros/camera/webrtc       - Close all WebRTC connections
    GET /ros/camera/webrtc/status   - Connection status
"""

import base64

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.ros.manager import ros_manager
from app.ros.topics import CAMERA_COLOR_IMAGE_RAW_TOPIC
from app.api.webrtc_utils import (
    handle_offer,
    close_all_connections,
    close_peer_connection,
    update_peer_feedback,
    VideoFeedback,
    get_connection_count,
    MAX_WEBRTC_CLIENTS_PER_SOURCE,
)

router = APIRouter()


class WebRTCOfferRequest(BaseModel):
    """SDP offer from the client."""

    sdp: str
    type: str = "offer"
    topic_name: Optional[str] = None
    fps: Optional[int] = 24


def _make_ros_capture(topic: str):
    """Create a capture function that reads from a ROS camera topic.

    Returns BGR numpy array compatible with OpenCV / av.VideoFrame.
    """

    def capture():
        image_msg = ros_manager.get_latest_camera_image(topic_name=topic)
        if not image_msg:
            return None

        width = image_msg.get("width", 0)
        height = image_msg.get("height", 0)
        encoding = image_msg.get("encoding", "rgb8")
        data_base64 = image_msg.get("data", "")

        if not data_base64 or width <= 0 or height <= 0:
            return None

        try:
            image_data = base64.b64decode(data_base64)

            if encoding == "rgb8":
                arr = np.frombuffer(image_data, dtype=np.uint8).reshape(
                    (height, width, 3)
                )
                # Convert RGB to BGR for av.VideoFrame(format="bgr24")
                return arr[:, :, ::-1].copy()
            elif encoding == "bgr8":
                return np.frombuffer(image_data, dtype=np.uint8).reshape(
                    (height, width, 3)
                )
            elif encoding == "mono8":
                gray = np.frombuffer(image_data, dtype=np.uint8).reshape(
                    (height, width)
                )
                # Convert grayscale to BGR
                import cv2

                return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            else:
                return None
        except Exception:
            return None

    return capture


@router.post("/ros/camera/webrtc/offer")
async def webrtc_offer(request: WebRTCOfferRequest):
    """
    Establish a WebRTC peer connection for ROS camera streaming.

    Must subscribe to the topic first using POST /api/nav/ros/camera/subscribe.

    Example request:
    ```json
    {
        "sdp": "v=0\\r\\no=- ...",
        "type": "offer",
        "topic_name": "/camera/camera/color/image_raw",
        "fps": 24
    }
    ```
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to ROS. Ensure rosbridge_server is running.",
        )

    topic = request.topic_name or CAMERA_COLOR_IMAGE_RAW_TOPIC
    fps = max(1, min(60, request.fps or 24))
    source_name = f"ros_camera:{topic}"

    capture_fn = _make_ros_capture(topic)

    try:
        answer = await handle_offer(
            source_name=source_name,
            sdp=request.sdp,
            sdp_type=request.type,
            capture_fn=capture_fn,
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
        "peer_id": answer["peer_id"],
        "adaptive_quality": answer["adaptive_quality"],
        "target_fps": answer["target_fps"],
        "topic": topic,
        "fps": fps,
    }


@router.post("/ros/camera/webrtc/connections/{peer_id}/feedback")
async def webrtc_feedback(peer_id: str, feedback: VideoFeedback, topic_name: Optional[str] = None):
    topic = topic_name or CAMERA_COLOR_IMAGE_RAW_TOPIC
    result = await update_peer_feedback(f"ros_camera:{topic}", peer_id, feedback.model_dump())
    if result is None:
        raise HTTPException(status_code=404, detail="WebRTC viewer not found")
    return result


@router.delete("/ros/camera/webrtc/connections/{peer_id}")
async def webrtc_close_peer(peer_id: str, topic_name: Optional[str] = None):
    topic = topic_name or CAMERA_COLOR_IMAGE_RAW_TOPIC
    closed = await close_peer_connection(f"ros_camera:{topic}", peer_id)
    return {"success": True, "closed": closed}


@router.delete("/ros/camera/webrtc")
async def webrtc_close(topic_name: Optional[str] = None):
    """Close all WebRTC connections for a ROS camera topic."""
    topic = topic_name or CAMERA_COLOR_IMAGE_RAW_TOPIC
    source_name = f"ros_camera:{topic}"
    closed = await close_all_connections(source_name)
    return {
        "success": True,
        "message": f"Closed {closed} WebRTC connection(s) for topic '{topic}'",
        "closed": closed,
    }


@router.get("/ros/camera/webrtc/status")
async def webrtc_status(topic_name: Optional[str] = None):
    """Get WebRTC connection status for a ROS camera topic."""
    topic = topic_name or CAMERA_COLOR_IMAGE_RAW_TOPIC
    source_name = f"ros_camera:{topic}"
    count = await get_connection_count(source_name)
    return {
        "success": True,
        "topic": topic,
        "active_connections": count,
        "max_connections": MAX_WEBRTC_CLIENTS_PER_SOURCE,
    }
