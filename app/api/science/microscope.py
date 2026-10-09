import json
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import datetime
from pathlib import Path

import cv2
from fastapi import APIRouter, Form, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.utils.json_store import load_json, save_json, save_json_locked
from app.utils.expeditions import EXPEDITION_BASE_DIR, get_safe_expedition_dir

router = APIRouter()

IMAGE_DIR = "storage/images"
META_FILE = "storage/metadata.json"


os.makedirs(IMAGE_DIR, exist_ok=True)


# Microscope hardware management
class MicroscopeManager:
    def __init__(self):
        self.microscope: cv2.VideoCapture | None = None
        self.microscope_info: dict = {}
        self.streaming_status: bool = False
        self.lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._opening_future = None
        self.device_path = "/dev/camera-microscope"

        # WebSocket client tracking
        self.ws_clients: list = []
        self._clients_lock = threading.Lock()

    def _open_microscope_with_timeout(self, timeout: float = 5.0):
        """Open microscope with timeout to prevent hanging"""

        def open_device():
            return cv2.VideoCapture(self.device_path)

        try:
            if self._opening_future is not None and not self._opening_future.done():
                return None
            future = self._executor.submit(open_device)
            self._opening_future = future
            return future.result(timeout=timeout)
        except FuturesTimeoutError:
            def release_late_result(completed):
                if not completed.cancelled():
                    try:
                        completed.result().release()
                    except Exception:
                        pass
            if not future.cancel():
                future.add_done_callback(release_late_result)
            print(f"[Microscope] Timeout opening device {self.device_path}")
            return None
        except Exception as e:
            print(f"[Microscope] Error opening device {self.device_path}: {e}")
            return None

    def start_microscope(self, width: int = 640, height: int = 480, fps: int = 30):
        """Initialize microscope device"""
        with self.lock:
            if self.microscope is not None and self.microscope.isOpened():
                print("[Microscope] Already started")
                return True

            print(f"[Microscope] Opening device at {self.device_path}...")
            microscope = self._open_microscope_with_timeout(timeout=5.0)

            if microscope is None:
                print(f"[Microscope] Failed to open device (timeout)")
                return False

            if not microscope.isOpened():
                microscope.release()
                print(f"[Microscope] Device not opened")
                return False

            print(f"[Microscope] Setting resolution to {width}x{height} @ {fps}fps")
            microscope.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            microscope.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            microscope.set(cv2.CAP_PROP_FPS, fps)
            microscope.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            self.microscope = microscope
            self.microscope_info = {"width": width, "height": height, "fps": fps}
            self.streaming_status = False
            print(f"[Microscope] Device started successfully")
            return True

    def stop_microscope(self):
        """Release microscope device"""
        with self.lock:
            if self.microscope:
                self.microscope.release()
                self.microscope = None
                self.microscope_info = {}
                self.streaming_status = False
                print("[Microscope] Device stopped")
                return True
            return False

    def capture_frame(self):
        """Capture a single frame from microscope"""
        with self.lock:
            if self.microscope is None:
                return None

            if not self.microscope.isOpened():
                return None

            ret, frame = self.microscope.read()
            if not ret:
                return None
            return frame

    def get_status(self):
        """Get microscope status"""
        with self.lock:
            if self.microscope is None or not self.microscope.isOpened():
                return {
                    "active": False,
                    "streaming": False,
                    "ws_clients": 0,
                    "device": self.device_path,
                }

            return {
                "active": True,
                "streaming": self.streaming_status,
                "device": self.device_path,
                "width": int(self.microscope.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(self.microscope.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": int(self.microscope.get(cv2.CAP_PROP_FPS)),
                "ws_clients": self.get_ws_client_count(),
            }

    # WebSocket client management methods
    def add_ws_client(self, websocket, max_clients=5):
        """Register WebSocket client"""
        with self._clients_lock:
            if len(self.ws_clients) >= max_clients:
                return False
            self.ws_clients.append(websocket)
            return True

    def remove_ws_client(self, websocket):
        """Unregister WebSocket client"""
        with self._clients_lock:
            if websocket in self.ws_clients:
                self.ws_clients.remove(websocket)

    def get_ws_client_count(self) -> int:
        """Get WebSocket client count"""
        with self._clients_lock:
            return len(self.ws_clients)


# Global microscope manager instance
microscope_manager = MicroscopeManager()




@router.post("/microscope/start")
def start_microscope(
    width: int = Form(640, ge=1), height: int = Form(480, ge=1), fps: int = Form(30, ge=1, le=60)
):
    """Start microscope device"""
    success = microscope_manager.start_microscope(width, height, fps)
    if not success:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to open microscope at {microscope_manager.device_path}",
        )

    return {
        "success": True,
        "message": "Microscope started",
        "status": microscope_manager.get_status(),
    }


@router.post("/microscope/stop")
def stop_microscope():
    """Stop microscope device"""
    success = microscope_manager.stop_microscope()
    if not success:
        raise HTTPException(status_code=404, detail="Microscope not active")
    return {"success": True, "message": "Microscope stopped"}


@router.get("/microscope/status")
def microscope_status():
    """Get microscope status"""
    return {"success": True, "status": microscope_manager.get_status()}


@router.post("/microscope/capture")
def capture_from_microscope(
    latitude: float = Form(0),
    longitude: float = Form(0),
    altitude: float = Form(0),
    battery_level: float = Form(100),
    mission_id: str = Form("default"),
    rover_id: str = Form("rover_001"),
    note: str = Form(""),
    expedition_id: str = Form("")
):
    """Capture image from microscope with full metadata"""
    frame = microscope_manager.capture_frame()
    if frame is None:
        raise HTTPException(
            status_code=500,
            detail="Failed to capture from microscope. Is it started?",
        )

    # Save frame as JPEG
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{timestamp}_microscope_capture.jpg"
    img_dir_loc = get_safe_expedition_dir(expedition_id) if expedition_id else IMAGE_DIR

    filepath = os.path.join(img_dir_loc, filename)

    if not cv2.imwrite(filepath, frame):
        raise HTTPException(status_code=500, detail="Failed to save captured image")
    file_size = os.path.getsize(filepath)

    # Get actual image dimensions
    height, width = frame.shape[:2]

    # Create metadata entry
    entry = {
        "file": filename,
        "timestamp": timestamp,
        "datetime_iso": datetime.utcnow().isoformat(),
        "location": {
            "latitude": latitude,
            "longitude": longitude,
            "altitude": altitude,
        },
        "rover_status": {
            "battery_level": battery_level,
            "rover_id": rover_id,
            "mission_id": mission_id,
        },
        "camera": {
            "device": "microscope",
            "device_path": microscope_manager.device_path,
            "settings": {"resolution": f"{width}x{height}"},
            "file_size_bytes": file_size,
        },
        "note": note,
        "tags": ["microscope", "science"],  # Auto-tags
    }
    save_json_locked(META_FILE, lambda data: data + [entry])

    return {
        "success": True,
        "message": "Image captured from microscope",
        "saved": filename,
        "metadata": entry,
        "file_size_mb": round(file_size / (1024 * 1024), 2),
    }


def generate_video_stream(target_fps: int = 30, quality: int = 85):
    """Generator function for MJPEG video streaming from microscope"""
    frame_delay = 1.0 / target_fps
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    while True:
        frame_started = time.monotonic()
        frame = microscope_manager.capture_frame()
        if frame is None:
            break

        # Encode frame as JPEG
        ret, buffer = cv2.imencode(".jpg", frame, encode_param)
        if not ret:
            continue

        frame_bytes = buffer.tobytes()

        # Yield frame in multipart format
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")

        time.sleep(max(0, frame_delay - (time.monotonic() - frame_started)))


@router.get("/microscope/stream")
def video_stream(
    fps: int = Query(30, ge=1, le=60),
    quality: int = Query(85, ge=1, le=100),
):
    """Stream live video feed from microscope (MJPEG)"""
    status = microscope_manager.get_status()
    if not status["active"]:
        raise HTTPException(
            status_code=400,
            detail="Microscope not started. Call /microscope/start first",
        )

    microscope_manager.streaming_status = True
    return StreamingResponse(
        generate_video_stream(target_fps=fps, quality=quality),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
