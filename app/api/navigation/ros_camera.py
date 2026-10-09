"""ROS camera image streaming endpoints"""

import asyncio
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from app.ros.manager import ros_manager
from app.ros.topics import CAMERA_COLOR_IMAGE_RAW_TOPIC
from app.api.ros_image import encode_ros_jpeg


router = APIRouter()


class SubscribeCameraRequest(BaseModel):
    """Request model for camera subscription"""

    topic_name: Optional[str] = CAMERA_COLOR_IMAGE_RAW_TOPIC


@router.post("/ros/camera/subscribe")
async def subscribe_to_camera(request: SubscribeCameraRequest):
    """
    Subscribe to ROS camera image topic.
    After subscribing, use GET /api/nav/ros/camera/latest to retrieve latest frame.

    Example request:
    ```json
    {
        "topic_name": "/camera/camera/color/image_raw"
    }
    ```
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to ROS. Ensure rosbridge_server is running.",
        )

    topic_name = request.topic_name or CAMERA_COLOR_IMAGE_RAW_TOPIC
    success = ros_manager.subscribe_camera_image(topic_name=topic_name)

    if not success:
        raise HTTPException(
            status_code=500, detail=f"Failed to subscribe to {topic_name}"
        )

    return {
        "success": True,
        "message": f"Subscribed to {topic_name} topic",
        "topic": topic_name,
        "info": "Use GET /api/nav/ros/camera/latest to retrieve latest image data",
    }


@router.get("/ros/camera/latest")
async def get_latest_camera_image(topic_name: Optional[str] = None):
    """
    Get the latest camera image from ROS topic.
    Must subscribe first using POST /api/nav/ros/camera/subscribe.

    Returns image message with base64 encoded image data.
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to ROS. Ensure rosbridge_server is running.",
        )

    topic = topic_name or CAMERA_COLOR_IMAGE_RAW_TOPIC
    image_msg = ros_manager.get_latest_camera_image(topic_name=topic)

    if image_msg is None:
        return {
            "success": False,
            "message": f"No image data received yet from {topic}. Ensure you've subscribed and messages are being published.",
            "data": None,
        }

    return {
        "success": True,
        "message": "Latest camera image",
        "topic": topic,
        "data": {
            "width": image_msg.get("width"),
            "height": image_msg.get("height"),
            "encoding": image_msg.get("encoding"),
            "data": image_msg.get("data"),  # base64 encoded
        },
    }


@router.get("/ros/camera/stream")
async def stream_camera_mjpeg(
    topic_name: Optional[str] = None,
    fps: int = Query(30, ge=1, le=60),
    quality: int = Query(85, ge=1, le=100),
):
    """
    Stream camera images as MJPEG over HTTP.
    Must subscribe to the topic first using POST /api/nav/ros/camera/subscribe.

    Returns a multipart MJPEG stream compatible with <img> tags.
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to ROS. Ensure rosbridge_server is running.",
        )

    topic = topic_name or CAMERA_COLOR_IMAGE_RAW_TOPIC
    frame_delay = 1.0 / fps

    async def generate_frames():
        """Generate MJPEG frames from ROS image messages"""
        loop = asyncio.get_running_loop()
        last_message = None

        while ros_manager.is_connected:
            started = loop.time()
            image_msg = ros_manager.get_latest_camera_image(topic_name=topic)

            if image_msg and image_msg is not last_message:
                last_message = image_msg
                try:
                    frame = await loop.run_in_executor(
                        None, encode_ros_jpeg, image_msg, quality
                    )

                    if frame is not None:
                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                        )

                except Exception as e:
                    print(f"Error processing frame: {e}")

            await asyncio.sleep(max(0, frame_delay - (loop.time() - started)))

    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.post("/ros/camera/unsubscribe")
async def unsubscribe_from_camera(request: SubscribeCameraRequest):
    """
    Unsubscribe from ROS camera topic.

    Example request:
    ```json
    {
        "topic_name": "/camera/camera/color/image_raw"
    }
    ```
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to ROS. Ensure rosbridge_server is running.",
        )

    topic_name = request.topic_name or CAMERA_COLOR_IMAGE_RAW_TOPIC
    ros_manager.unsubscribe(topic_name)

    return {
        "success": True,
        "message": f"Unsubscribed from {topic_name}",
        "topic": topic_name,
    }
