from fastapi import APIRouter, Request, HTTPException
import asyncio
from app.ros.manager import ros_manager
from app.ros.topics import TEST_TOPIC

router = APIRouter()


@router.post("/test")
async def api_test_point(request: Request):
    data = (
        await request.json()
        if request.headers.get("content-type") == "application/json"
        else None
    )

    return {
        "success": True,
        "status": "Success",
        "message": "The POST Request was successfully validated. Check the data we received.",
        "data": data,
    }


@router.options("/test")
async def api_test_options():
    """Handle OPTIONS preflight request explicitly"""
    return {"success": True, "message": "OPTIONS request handled"}


@router.get("/teensy_topic")
async def get_teensy_topic_data():
    """
    Fetch the latest data from /teensy_topic.
    
    This endpoint subscribes to the teensy_topic and returns the most recent message.
    If not already subscribed, it will start the subscription.
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to ROS. Ensure rosbridge_server is running.",
        )

    # Subscribe if not already subscribed
    if TEST_TOPIC not in ros_manager._subscribers:
        success = ros_manager.subscribe(TEST_TOPIC, "std_msgs/Int32")
        if not success:
            raise HTTPException(
                status_code=500, detail=f"Failed to subscribe to {TEST_TOPIC}"
            )
        # Wait a moment for first message to arrive
        await asyncio.sleep(0.5)

    # Get latest message
    latest_message = ros_manager.get_latest_message(TEST_TOPIC)

    if latest_message is None:
        # Wait a bit longer for the first message
        await asyncio.sleep(1.0)
        latest_message = ros_manager.get_latest_message(TEST_TOPIC)
        
        if latest_message is None:
            return {
                "success": True,
                "subscribed": True,
                "message": f"Subscribed to {TEST_TOPIC}, waiting for data...",
                "data": None,
            }

    return {
        "success": True,
        "subscribed": True,
        "topic": TEST_TOPIC,
        "data": latest_message,
    }


@router.post("/teensy_topic/unsubscribe")
async def unsubscribe_teensy_topic():
    """
    Unsubscribe from /teensy_topic to stop receiving data.
    """
    if not ros_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to ROS. Ensure rosbridge_server is running.",
        )

    ros_manager.unsubscribe(TEST_TOPIC)

    return {
        "success": True,
        "message": f"Unsubscribed from {TEST_TOPIC}",
    }


@router.get("/teensy_topic/debug")
async def debug_teensy_topic():
    """
    Debug endpoint to check internal state of ROS manager for teensy_topic.
    """
    return {
        "connected": ros_manager.is_connected,
        "subscribed_topics": list(ros_manager._subscribers.keys()),
        "latest_messages_keys": list(ros_manager._latest_messages.keys()),
        "teensy_in_latest": TEST_TOPIC in ros_manager._latest_messages,
        "teensy_message": ros_manager._latest_messages.get(TEST_TOPIC),
        "all_latest_messages": ros_manager._latest_messages,
    }
