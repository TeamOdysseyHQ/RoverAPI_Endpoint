import fcntl
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

router = APIRouter()

IMAGE_DIR = "storage/images"
META_FILE = "storage/metadata.json"
EXPEDITION_BASE_DIR = os.environ.get(
    "EXPEDITION_BASE_DIR", "/home/administrator/expeditions/unprocessed"
)

os.makedirs(IMAGE_DIR, exist_ok=True)


# Microscope hardware management
class MicroscopeManager:
    def __init__(self):
        self.microscope: cv2.VideoCapture | None = None
        self.microscope_info: dict = {}
        self.streaming_status: bool = False
        self.lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1)
        self.device_path = "/dev/camera-microscope"

        # WebSocket client tracking
        self.ws_clients: list = []

    def _open_microscope_with_timeout(self, timeout: float = 5.0):
        """Open microscope with timeout to prevent hanging"""

        def open_device():
            return cv2.VideoCapture(self.device_path)

        try:
            future = self._executor.submit(open_device)
            return future.result(timeout=timeout)
        except FuturesTimeoutError:
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
                print(f"[Microscope] Device not opened")
                return False

            print(f"[Microscope] Setting resolution to {width}x{height} @ {fps}fps")
            microscope.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            microscope.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            microscope.set(cv2.CAP_PROP_FPS, fps)

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
                "ws_clients": len(self.ws_clients),
            }

    # WebSocket client management methods
    def add_ws_client(self, websocket):
        """Register WebSocket client"""
        with self.lock:
            self.ws_clients.append(websocket)

    def remove_ws_client(self, websocket):
        """Unregister WebSocket client"""
        with self.lock:
            if websocket in self.ws_clients:
                self.ws_clients.remove(websocket)

    def get_ws_client_count(self) -> int:
        """Get WebSocket client count"""
        with self.lock:
            return len(self.ws_clients)


# Global microscope manager instance
microscope_manager = MicroscopeManager()


def load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return []


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def save_json_locked(path, updater):
    """Atomically read-modify-write a JSON file with file locking."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lock_path = path + ".lock"
    with open(lock_path, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            data = load_json(path)
            data = updater(data)
            save_json(path, data)
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)
    return data


def get_safe_expedition_dir(expedition_id: str) -> str:
    """Validate expedition_id and return a safe directory path."""
    sanitized = "".join(c for c in expedition_id if c.isalnum() or c in "._-")
    if not sanitized:
        raise HTTPException(status_code=400, detail="Expedition ID must be provided.")
    base = Path(EXPEDITION_BASE_DIR).resolve()
    target = (base / sanitized).resolve()
    if not str(target).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Invalid expedition ID.")
    os.makedirs(str(target), exist_ok=True)
    return str(target)


@router.post("/microscope/start")
async def start_microscope(
    width: int = Form(640), height: int = Form(480), fps: int = Form(30)
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
async def stop_microscope():
    """Stop microscope device"""
    success = microscope_manager.stop_microscope()
    if not success:
        raise HTTPException(status_code=404, detail="Microscope not active")
    return {"success": True, "message": "Microscope stopped"}


@router.get("/microscope/status")
async def microscope_status():
    """Get microscope status"""
    return {"success": True, "status": microscope_manager.get_status()}


@router.post("/microscope/capture")
async def capture_from_microscope(
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
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_microscope_capture.jpg"
    img_dir_loc = get_safe_expedition_dir(expedition_id) if expedition_id else IMAGE_DIR

    filepath = os.path.join(img_dir_loc, filename)

    cv2.imwrite(filepath, frame)
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

        time.sleep(frame_delay)


@router.get("/microscope/stream")
async def video_stream(
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
