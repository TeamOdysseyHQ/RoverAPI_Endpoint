from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import cv2
import asyncio

from app.api.science.microscope import microscope_manager

router = APIRouter()

MAX_CLIENTS = 5


@router.websocket("/microscope/stream/ws")
async def microscope_websocket_stream(
    websocket: WebSocket, quality: int = Query(85), fps: int = Query(30)
):
    """
    WebSocket endpoint for low-latency microscope video streaming

    Args:
        quality: JPEG compression quality (1-100, default: 85)
        fps: Target frames per second (default: 30)
    """
    await websocket.accept()

    # Check connection limit
    if microscope_manager.get_ws_client_count() >= MAX_CLIENTS:
        await websocket.send_json(
            {
                "type": "error",
                "message": f"Too many clients connected (max {MAX_CLIENTS})",
            }
        )
        await websocket.close(code=4001, reason="Too many clients")
        return

    # Register client
    microscope_manager.add_ws_client(websocket)
    print(
        f"[MicroscopeWS] Client connected. Total clients: {microscope_manager.get_ws_client_count()}"
    )

    # Check if microscope is active
    status = microscope_manager.get_status()
    if not status["active"]:
        await websocket.send_json(
            {
                "type": "error",
                "message": "Microscope not started. Call /microscope/start first",
            }
        )
        await websocket.close()
        microscope_manager.remove_ws_client(websocket)
        return

    # Send initial connection success
    await websocket.send_json(
        {
            "type": "connected",
            "message": "Microscope stream connected",
            "resolution": f"{status['width']}x{status['height']}",
            "fps": fps,
        }
    )

    frame_delay = 1.0 / fps
    loop = asyncio.get_event_loop()

    try:
        while True:
            # Capture frame in executor to avoid blocking the event loop
            frame = await loop.run_in_executor(
                None, microscope_manager.capture_frame
            )

            if frame is None:
                await websocket.send_json(
                    {"type": "error", "message": "Failed to capture frame"}
                )
                await asyncio.sleep(0.1)
                continue

            # Encode frame as JPEG
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
            ret, buffer = cv2.imencode(".jpg", frame, encode_param)

            if not ret:
                await websocket.send_json(
                    {"type": "error", "message": "Failed to encode frame"}
                )
                await asyncio.sleep(0.1)
                continue

            # Send frame as binary data
            frame_bytes = buffer.tobytes()
            await websocket.send_bytes(frame_bytes)

            # Control frame rate
            await asyncio.sleep(frame_delay)

    except WebSocketDisconnect:
        print("[MicroscopeWS] Client disconnected")
    except Exception as e:
        print(f"[MicroscopeWS] Error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        # Unregister client
        microscope_manager.remove_ws_client(websocket)
        print(
            f"[MicroscopeWS] Client removed. Remaining clients: {microscope_manager.get_ws_client_count()}"
        )
        try:
            await websocket.close()
        except Exception:
            pass
            pass
