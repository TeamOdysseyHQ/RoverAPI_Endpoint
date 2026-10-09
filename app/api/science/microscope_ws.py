from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import cv2
import asyncio

from app.api.science.microscope import microscope_manager

router = APIRouter()
MAX_CLIENTS = 5


def _capture_jpeg(quality):
    frame = microscope_manager.capture_frame()
    if frame is None:
        return None
    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return buffer.tobytes() if ok else None


@router.websocket("/microscope/stream/ws")
async def microscope_websocket_stream(
    websocket: WebSocket,
    quality: int = Query(85, ge=1, le=100),
    fps: int = Query(30, ge=1, le=60),
):
    await websocket.accept()
    status = await asyncio.to_thread(microscope_manager.get_status)
    if not status["active"]:
        await websocket.send_json({"type": "error", "message": "Microscope not started. Call /microscope/start first"})
        await websocket.close(code=4000)
        return

    if not microscope_manager.add_ws_client(websocket, MAX_CLIENTS):
        await websocket.send_json({"type": "error", "message": f"Too many clients connected (max {MAX_CLIENTS})"})
        await websocket.close(code=4001)
        return

    frame_delay = 1.0 / fps
    loop = asyncio.get_running_loop()
    try:
        await websocket.send_json({
            "type": "connected", "message": "Microscope stream connected",
            "resolution": f"{status['width']}x{status['height']}", "fps": fps,
        })
        while True:
            started = loop.time()
            frame = await asyncio.to_thread(_capture_jpeg, quality)
            if frame is None:
                await websocket.send_json({"type": "error", "message": "Failed to capture or encode frame"})
                break
            await asyncio.wait_for(websocket.send_bytes(frame), timeout=2)
            await asyncio.sleep(max(0, frame_delay - (loop.time() - started)))
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        microscope_manager.remove_ws_client(websocket)
        try:
            await websocket.close()
        except Exception:
            pass
