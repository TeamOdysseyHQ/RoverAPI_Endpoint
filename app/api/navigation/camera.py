import fcntl
import json
import os
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import datetime
from pathlib import Path
from typing import Optional

from uuid import uuid4 as uuid

import cv2
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

router = APIRouter()

IMAGE_DIR = "storage/images"
META_FILE = "storage/metadata.json"
WAYPOINT_FILE = "storage/waypoints.json"
EXPEDITION_BASE_DIR = os.environ.get(
    "EXPEDITION_BASE_DIR", "/home/administrator/expeditions/unprocessed"
)

_metadata_lock = threading.Lock()

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs("storage/reports", exist_ok=True)


CAMERA_DEVICES = {
    "microscope": "/dev/camera-microscope",
    "arm": "/dev/camera-arm",
    "science": "/dev/camera-science",
    "rover": "/dev/camera-rover",
}

G_C_NAME = str(uuid())

# Camera hardware management
class MultiCameraManager:
    def __init__(self):
        self.cameras: dict[str, cv2.VideoCapture] = {}
        self.camera_info: dict[str, dict] = {}
        self.streaming_status: dict[str, bool] = {}
        self.ws_clients: dict[str, list] = {}

    def _device_path(self, camera_name: str) -> Optional[str]:
        if camera_name in CAMERA_DEVICES:
            return CAMERA_DEVICES[camera_name]

        if camera_name.startswith("video"):
            try:
                index = int(camera_name[5:])
                return f"/dev/video{index}"
            except ValueError:
                return None

        return None

    def _open_camera(self, camera_name: str) -> Optional[cv2.VideoCapture]:
        device_path = self._device_path(camera_name)

        if device_path is None:
            print(f"[Camera] Unknown camera: {camera_name}")
            return None

        if not os.path.exists(device_path):
            print(f"[Camera] Device does not exist: {device_path}")
            return None

        print(f"[Camera] RAW OPEN {camera_name} -> {device_path}")

        # Deliberately raw.
        # If this hangs, LET IT HANG.
        cap = cv2.VideoCapture(device_path)

        print(
            f"[Camera] RAW OPEN RETURNED {camera_name}: "
            f"isOpened={cap.isOpened()}"
        )

        return cap

    def detect_cameras(self):
        available = []
        used_paths = set()

        print("[Camera] === RAW CAMERA DETECTION START ===")

        # Named cameras
        for camera_name, device_path in CAMERA_DEVICES.items():
            used_paths.add(os.path.realpath(device_path))

            print(f"[Camera] Checking named camera {camera_name}: {device_path}")

            if not os.path.exists(device_path):
                print(f"[Camera] Missing: {device_path}")
                continue

            # If already started, don't try to open the same device twice.
            if camera_name in self.cameras:
                camera = self.cameras[camera_name]

                if camera.isOpened():
                    info = self.camera_info.get(camera_name, {})

                    available.append({
                        "name": camera_name,
                        "device_path": device_path,
                        "backend": "V4L2",
                        "default_resolution":
                            f"{info.get('width', 640)}x{info.get('height', 480)}",
                        "default_fps": info.get("fps", 30),
                        "active": True,
                        "is_named": True,
                    })

                    continue

            print(f"[Camera] Opening named camera {camera_name}")

            cap = cv2.VideoCapture(device_path)

            print(
                f"[Camera] VideoCapture returned for {camera_name}: "
                f"{cap.isOpened()}"
            )

            if not cap.isOpened():
                cap.release()
                continue

            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = int(cap.get(cv2.CAP_PROP_FPS))

            try:
                backend = cap.getBackendName()
            except Exception:
                backend = "unknown"

            available.append({
                "name": camera_name,
                "device_path": device_path,
                "backend": backend,
                "default_resolution": f"{width}x{height}",
                "default_fps": fps,
                "active": False,
                "is_named": True,
            })

            print(
                f"[Camera] Detected {camera_name}: "
                f"{width}x{height} @ {fps}"
            )

            cap.release()

        # Raw /dev/videoN enumeration
        for i in range(20):
            device_path = f"/dev/video{i}"

            if not os.path.exists(device_path):
                continue

            # Resolve symlinks so named devices aren't opened again.
            real_path = os.path.realpath(device_path)

            if real_path in used_paths:
                continue

            camera_name = f"video{i}"

            print(f"[Camera] Checking generic {camera_name}: {device_path}")

            if camera_name in self.cameras:
                camera = self.cameras[camera_name]

                if camera.isOpened():
                    info = self.camera_info.get(camera_name, {})

                    available.append({
                        "name": camera_name,
                        "device_path": device_path,
                        "backend": "V4L2",
                        "default_resolution":
                            f"{info.get('width', 640)}x{info.get('height', 480)}",
                        "default_fps": info.get("fps", 30),
                        "active": True,
                        "is_named": False,
                    })

                    continue

            # No v4l2-ctl prefilter.
            # No timeout.
            # No executor.
            print(f"[Camera] RAW generic open: {device_path}")

            cap = cv2.VideoCapture(device_path)

            print(
                f"[Camera] RAW generic open returned: {device_path}: "
                f"{cap.isOpened()}"
            )

            if not cap.isOpened():
                cap.release()
                continue

            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = int(cap.get(cv2.CAP_PROP_FPS))

            try:
                backend = cap.getBackendName()
            except Exception:
                backend = "unknown"

            available.append({
                "name": camera_name,
                "device_path": device_path,
                "backend": backend,
                "default_resolution": f"{width}x{height}",
                "default_fps": fps,
                "active": False,
                "is_named": False,
            })

            cap.release()

        print(
            f"[Camera] === RAW CAMERA DETECTION END: "
            f"{len(available)} found ==="
        )

        return available

    def start_camera(
        self,
        camera_name: str,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
        pixel_format: Optional[str] = None,
    ):
        existing = self.cameras.get(camera_name)

        if existing is not None and existing.isOpened():
            print(f"[Camera] {camera_name} already started")
            return True

        print(f"[Camera] Starting {camera_name}")

        camera = self._open_camera(camera_name)

        if camera is None:
            return False

        if not camera.isOpened():
            print(f"[Camera] Failed to open {camera_name}")
            camera.release()
            return False

        if pixel_format:
            camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*pixel_format))
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        camera.set(cv2.CAP_PROP_FPS, fps)

        device_path = self._device_path(camera_name) or ""

        self.cameras[camera_name] = camera
        self.camera_info[camera_name] = {
            "width": width,
            "height": height,
            "fps": fps,
            "device_path": device_path,
        }
        self.streaming_status[camera_name] = False

        print(f"[Camera] Started {camera_name}")

        return True

    def stop_camera(self, camera_name: str):
        camera = self.cameras.get(camera_name)

        if camera is None:
            return False

        print(f"[Camera] Releasing {camera_name}")

        camera.release()

        self.cameras.pop(camera_name, None)
        self.camera_info.pop(camera_name, None)
        self.streaming_status.pop(camera_name, None)

        return True

    def stop_all_cameras(self):
        for name, camera in list(self.cameras.items()):
            print(f"[Camera] Releasing {name}")
            camera.release()

        self.cameras.clear()
        self.camera_info.clear()
        self.streaming_status.clear()

    def capture_frame(self, camera_name: str):
        camera = self.cameras.get(camera_name)

        if camera is None:
            print(f"[Camera] capture_frame: {camera_name} doesn't exist")
            return None

        if not camera.isOpened():
            print(f"[Camera] capture_frame: {camera_name} isn't open")
            return None

        # Again deliberately raw.
        # If read() blocks, we want to see that.
        print(f"[Camera] READ START {camera_name}")

        ret, frame = camera.read()

        print(f"[Camera] READ END {camera_name}: ret={ret}")

        if not ret:
            return None

        return frame

    def get_camera_status(self, camera_name: str):
        camera = self.cameras.get(camera_name)

        if camera is None or not camera.isOpened():
            return {
                "active": False,
                "streaming": False,
                "ws_clients": 0,
            }

        info = self.camera_info.get(camera_name, {})

        return {
            "active": True,
            "streaming": self.streaming_status.get(camera_name, False),
            "camera_name": camera_name,
            "device_path": info.get("device_path", ""),
            "width": int(camera.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": int(camera.get(cv2.CAP_PROP_FPS)),
            "ws_clients": self.get_ws_client_count(camera_name),
        }

    def get_all_statuses(self):
        statuses = {}

        for name, camera in list(self.cameras.items()):
            info = self.camera_info.get(name, {})

            statuses[name] = {
                "active": camera.isOpened(),
                "streaming": self.streaming_status.get(name, False),
                "device_path": info.get("device_path", ""),
                "width": int(camera.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": int(camera.get(cv2.CAP_PROP_FPS)),
            }

        return statuses

    def add_ws_client(self, camera_name: str, websocket):
        self.ws_clients.setdefault(camera_name, []).append(websocket)

    def remove_ws_client(self, camera_name: str, websocket):
        clients = self.ws_clients.get(camera_name)

        if not clients:
            return

        if websocket in clients:
            clients.remove(websocket)

        if not clients:
            self.ws_clients.pop(camera_name, None)

    def get_ws_client_count(self, camera_name: str):
        return len(self.ws_clients.get(camera_name, []))

    def get_supported_resolutions(self, camera_name: str) -> dict:
        """Query supported resolutions for a camera using v4l2-ctl"""
        device_path = CAMERA_DEVICES.get(camera_name)

        # If not a named camera, check if it's a video device
        if device_path is None and camera_name.startswith("video"):
            try:
                video_index = int(camera_name.replace("video", ""))
                device_path = f"/dev/video{video_index}"
            except ValueError:
                return {
                    "success": False,
                    "error": f"Invalid video device name: {camera_name}",
                    "formats": [],
                }

        if not device_path or not os.path.exists(device_path):
            return {
                "success": False,
                "error": f"Camera '{camera_name}' not found",
                "formats": [],
            }

        # Preset fallback resolutions
        FALLBACK_RESOLUTIONS = [
            {"width": 1920, "height": 1080},
            {"width": 1280, "height": 720},
            {"width": 640, "height": 480},
            {"width": 320, "height": 240},
        ]

        try:
            # Try using v4l2-ctl to query supported formats
            result = subprocess.run(
                ["v4l2-ctl", "-d", device_path, "--list-formats-ext"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                print(
                    f"[Camera] v4l2-ctl failed for {camera_name}, using fallback presets"
                )
                return {
                    "success": True,
                    "formats": [
                        {
                            "fourcc": "PRESET",
                            "description": "Common resolutions (v4l2-ctl unavailable)",
                            "resolutions": FALLBACK_RESOLUTIONS,
                        }
                    ],
                }

            # Parse v4l2-ctl output
            formats = []
            current_format = None
            current_format_desc = None
            current_resolutions = []
            current_resolution = None

            for line in result.stdout.split("\n"):
                # Parse format line: [0]: 'MJPG' (Motion-JPEG, compressed)
                format_match = re.match(r"\s*\[\d+\]: '(\w+)' \((.+)\)", line)
                if format_match:
                    # Save previous format
                    if current_format and current_resolutions:
                        formats.append(
                            {
                                "fourcc": current_format,
                                "description": current_format_desc,
                                "resolutions": current_resolutions,
                            }
                        )

                    current_format = format_match.group(1)
                    current_format_desc = format_match.group(2)
                    current_resolutions = []
                    current_resolution = None
                    continue

                # Parse size line: Size: Discrete 1280x720
                size_match = re.match(r"\s*Size: Discrete (\d+)x(\d+)", line)
                if size_match and current_format:
                    width, height = int(size_match.group(1)), int(size_match.group(2))
                    # Avoid duplicates
                    if not any(
                        r["width"] == width and r["height"] == height
                        for r in current_resolutions
                    ):
                        current_resolutions.append({"width": width, "height": height})
                    current_resolution = next(
                        r for r in current_resolutions if r["width"] == width and r["height"] == height
                    )
                    continue

                # Frame rates belong to this pixel format AND resolution.
                interval_match = re.search(r"Interval: Discrete .*?\(([\d.]+) fps\)", line)
                if interval_match and current_resolution is not None:
                    rate = float(interval_match.group(1))
                    if 0 < rate <= 1000:
                        rates = current_resolution.setdefault("frame_rates", [])
                        if rate not in rates:
                            rates.append(rate)
                            rates.sort(reverse=True)

            # Save last format
            if current_format and current_resolutions:
                formats.append(
                    {
                        "fourcc": current_format,
                        "description": current_format_desc,
                        "resolutions": current_resolutions,
                    }
                )

            if not formats:
                print(
                    f"[Camera] No formats parsed from v4l2-ctl for {camera_name}, using fallback"
                )
                return {
                    "success": True,
                    "formats": [
                        {
                            "fourcc": "PRESET",
                            "description": "Common resolutions (parsing failed)",
                            "resolutions": FALLBACK_RESOLUTIONS,
                        }
                    ],
                }

            return {"success": True, "formats": formats}

        except FileNotFoundError:
            print(
                f"[Camera] v4l2-ctl not found, using fallback presets for {camera_name}"
            )
            return {
                "success": True,
                "formats": [
                    {
                        "fourcc": "PRESET",
                        "description": "Common resolutions (v4l2-ctl not installed)",
                        "resolutions": FALLBACK_RESOLUTIONS,
                    }
                ],
            }
        except subprocess.TimeoutExpired:
            print(f"[Camera] v4l2-ctl timeout for {camera_name}, using fallback")
            return {
                "success": True,
                "formats": [
                    {
                        "fourcc": "PRESET",
                        "description": "Common resolutions (query timeout)",
                        "resolutions": FALLBACK_RESOLUTIONS,
                    }
                ],
            }
        except Exception as e:
            print(f"[Camera] Error querying resolutions for {camera_name}: {e}")
            return {
                "success": True,
                "formats": [
                    {
                        "fourcc": "PRESET",
                        "description": "Common resolutions (query error)",
                        "resolutions": FALLBACK_RESOLUTIONS,
                    }
                ],
            }

# Global camera manager instance
camera_manager = MultiCameraManager()

def load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return []


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def save_json_locked(path, updater):
    """Atomically read-modify-write a JSON file with file locking.
    updater is a callable that receives the current data and returns modified data."""
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


def secure_filename(filename: str) -> str:
    """Simple secure filename implementation"""
    return "".join(c for c in filename if c.isalnum() or c in "._-")


def get_safe_expedition_dir(expedition_id: str) -> str:
    """Validate expedition_id and return a safe directory path.
    Raises HTTPException on path traversal attempts."""
    sanitized = secure_filename(expedition_id)
    if not sanitized:
        raise HTTPException(status_code=400, detail="Expedition ID must be provided.")
    base = Path(EXPEDITION_BASE_DIR).resolve()
    target = (base / sanitized).resolve()
    if not str(target).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Invalid expedition ID.")
    os.makedirs(str(target), exist_ok=True)
    return str(target)


@router.get("/cameras/detect")
async def detect_cameras():
    """Detect all available cameras"""
    with open(f"/home/administratror/DEBUG_CAMS_CSRAL/logger_{G_C_NAME}.log", "a") as out:
        out.write("DETECTION ENDPOINT: Accessing it gng")
    cameras = camera_manager.detect_cameras()
    return {"status": "ok", "cameras": cameras, "count": len(cameras)}


@router.get("/cameras/{camera_name}/resolutions")
async def get_camera_resolutions(camera_name: str):
    """Get supported resolutions for a specific camera"""
    # Validate camera name (named camera or video device)
    with open(f"/home/administratror/DEBUG_CAMS_CSRAL/logger_{G_C_NAME}.log", "a") as out:
        out.write("DETECTION RESOLUTION ENDPOINT: Accessing it gng")
    is_valid = camera_name in CAMERA_DEVICES or (
        camera_name.startswith("video") and camera_name[5:].isdigit()
    )

    if not is_valid:
        raise HTTPException(
            status_code=404,
            detail=f"Camera '{camera_name}' not found. Available named cameras: {', '.join(CAMERA_DEVICES.keys())}. Also supports video0, video1, etc.",
        )

    result = camera_manager.get_supported_resolutions(camera_name)

    if not result.get("success", False) and result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])

    # Get device path for response
    device_path = CAMERA_DEVICES.get(camera_name)
    if device_path is None and camera_name.startswith("video"):
        try:
            video_index = int(camera_name.replace("video", ""))
            device_path = f"/dev/video{video_index}"
        except ValueError:
            device_path = "unknown"

    return {
        "success": True,
        "camera_name": camera_name,
        "device_path": device_path,
        "formats": result.get("formats", []),
    }


@router.post("/cameras/{camera_name}/start")
async def start_camera(
    camera_name: str,
    width: int = Form(640),
    height: int = Form(480),
    fps: int = Form(30),
    pixel_format: Optional[str] = Form(None),
):
    """Start specific camera"""
    # Validate camera name (named camera or video device)
    with open(f"/home/administratror/DEBUG_CAMS_CSRAL/logger_{G_C_NAME}.log", "a") as out:
        out.write("START CAM ENDPOINT: Accessing it gng")
    is_valid = camera_name in CAMERA_DEVICES or (
        camera_name.startswith("video") and camera_name[5:].isdigit()
    )

    if not is_valid:
        raise HTTPException(
            status_code=404,
            detail=f"Camera '{camera_name}' not found. Available named cameras: {', '.join(CAMERA_DEVICES.keys())}. Also supports video0, video1, etc.",
        )

    if pixel_format and not re.fullmatch(r"[A-Z0-9]{4}", pixel_format):
        raise HTTPException(status_code=400, detail="Invalid camera pixel format")
    success = camera_manager.start_camera(camera_name, width, height, fps, pixel_format)
    if not success:
        raise HTTPException(
            status_code=500, detail=f"Failed to open camera '{camera_name}'"
        )

    return {
        "status": "ok",
        "message": f"Camera '{camera_name}' started",
        "camera": camera_manager.get_camera_status(camera_name),
    }


@router.post("/cameras/{camera_name}/stop")
async def stop_camera(camera_name: str):
    """Stop specific camera"""
    with open(f"/home/administratror/DEBUG_CAMS_CSRAL/logger_{G_C_NAME}.log", "a") as out:
        out.write("STOP CAM ENDPOINT: Accessing it gng")
    success = camera_manager.stop_camera(camera_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"Camera '{camera_name}' not found")
    return {"status": "ok", "message": f"Camera '{camera_name}' stopped"}


@router.post("/cameras/stop_all")
async def stop_all_cameras():
    """Stop all cameras"""
    with open(f"/home/administratror/DEBUG_CAMS_CSRAL/logger_{G_C_NAME}.log", "a") as out:
        out.write("STOP CAM ENDPOINT: Accessing it gng")
    camera_manager.stop_all_cameras()
    return {"status": "ok", "message": "All cameras stopped"}


@router.get("/cameras/status")
async def cameras_status():
    """Get status of all cameras"""
    with open(f"/home/administratror/DEBUG_CAMS_CSRAL/logger_{G_C_NAME}.log", "a") as out:
        out.write("STATUS ENDPOINT: Accessing it gng")
    return {"status": "ok", "cameras": camera_manager.get_all_statuses()}


@router.get("/cameras/{camera_name}/status")
async def camera_status(camera_name: str):
    """Get specific camera status"""
    with open(f"/home/administratror/DEBUG_CAMS_CSRAL/logger_{G_C_NAME}.log", "a") as out:
        out.write("STATUS CAM ENDPOINT: Accessing it gng")
    return {"status": "ok", "camera": camera_manager.get_camera_status(camera_name)}


@router.post("/cameras/{camera_name}/capture")
async def capture_from_camera(
    camera_name: str,
    latitude: float = Form(0),
    longitude: float = Form(0),
    altitude: float = Form(0),
    heading: float = Form(0),
    speed: float = Form(0),
    battery_level: float = Form(100),
    temperature: float = Form(20),
    humidity: float = Form(50),
    note: str = Form(""),
    mission_id: str = Form("default"),
    rover_id: str = Form("rover_001"),
    tags: str = Form(""),
    expedition_id: str = Form(""),
):
    """Capture image from specific camera"""
    with open(f"/home/administratror/DEBUG_CAMS_CSRAL/logger_{G_C_NAME}.log", "a") as out:
        out.write("CAPTURE CAM ENDPOINT: Accessing it gng")
    frame = camera_manager.capture_frame(camera_name)
    if frame is None:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to capture from camera '{camera_name}'. Is it started?",
        )

    # Save frame as JPEG

    if not expedition_id:
        return {"status": "error", "message": "Expedition ID must be provided."}

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{camera_name}_capture.jpg"

    img_dir_loc = get_safe_expedition_dir(expedition_id)

    filepath = os.path.join(img_dir_loc, filename)

    cv2.imwrite(filepath, frame)
    file_size = os.path.getsize(filepath)

    # Get actual image dimensions
    img_height, img_width = frame.shape[:2]

    # Create metadata entry
    entry = {
        "file": filename,
        "timestamp": timestamp,
        "datetime_iso": datetime.utcnow().isoformat(),
        "location": {
            "latitude": latitude,
            "longitude": longitude,
            "altitude": altitude,
            "heading": heading,
        },
        "motion": {
            "speed": speed,
            "heading": heading,
        },
        "environment": {
            "temperature": temperature,
            "humidity": humidity,
        },
        "rover_status": {
            "battery_level": battery_level,
            "rover_id": rover_id,
            "mission_id": mission_id,
        },
        "camera": {
            "camera_name": camera_name,
            "device_path": CAMERA_DEVICES.get(camera_name)
            or (
                f"/dev/video{camera_name.replace('video', '')}"
                if camera_name.startswith("video")
                else ""
            ),
            "settings": {
                "resolution": f"{img_width}x{img_height}",
                "hardware_capture": True,
            },
            "file_size_bytes": file_size,
        },
        "note": note,
        "tags": tags.split(",") if tags else [],
        "expedition_id": expedition_id,
    }
    save_json_locked(META_FILE, lambda data: data + [entry])

    return {
        "status": "ok",
        "message": f"Image captured from camera '{camera_name}'",
        "saved": filename,
        "metadata": entry,
        "file_size_mb": round(file_size / (1024 * 1024), 2),
    }


def generate_video_stream(camera_name: str, target_fps: int = 30, quality: int = 85):
    """Generator function for MJPEG video streaming from specific camera"""
    with open(f"/home/administratror/DEBUG_CAMS_CSRAL/logger_{G_C_NAME}.log", "a") as out:
        out.write("GENERATE VIDEO CAM ENDPOINT: Accessing it gng")
    frame_delay = 1.0 / target_fps
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    while True:
        frame = camera_manager.capture_frame(camera_name)
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


@router.get("/cameras/{camera_name}/stream")
async def video_stream(
    camera_name: str,
    fps: int = Query(30, ge=1, le=60),
    quality: int = Query(85, ge=1, le=100),
):
    """Stream live video feed from specific camera (MJPEG)"""
    with open(f"/home/administratror/DEBUG_CAMS_CSRAL/logger_{G_C_NAME}.log", "a") as out:
        out.write("VIDEO CAM STREAM ENDPOINT: Accessing it gng")
    status = camera_manager.get_camera_status(camera_name)
    if not status["active"]:
        raise HTTPException(
            status_code=400,
            detail=f"Camera '{camera_name}' not started. Call /cameras/{camera_name}/start first",
        )

    camera_manager.streaming_status[camera_name] = True
    return StreamingResponse(
        generate_video_stream(camera_name, target_fps=fps, quality=quality),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.post("/capture")
async def capture(
    image: UploadFile = File(...),
    latitude: float = Form(0),
    longitude: float = Form(0),
    altitude: float = Form(0),
    heading: float = Form(0),
    speed: float = Form(0),
    battery_level: float = Form(100),
    temperature: float = Form(20),
    humidity: float = Form(50),
    note: str = Form(""),
    mission_id: str = Form("default"),
    rover_id: str = Form("rover_001"),
    camera_settings: str = Form("{}"),
    tags: str = Form(""),
    expedition_id: str = Form(""),
):
    """Capture camera screenshot with metadata"""
    with open(f"/home/administratror/DEBUG_CAMS_CSRAL/logger_{G_C_NAME}.log", "a") as out:
        out.write("CAPTURE CAM ENDPOINT: Accessing it gng")
    if not image.filename:
        raise HTTPException(status_code=400, detail="No image selected")

    try:
        camera_settings_dict = json.loads(camera_settings) if camera_settings else {}
    except json.JSONDecodeError:
        camera_settings_dict = {}

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{secure_filename(image.filename)}"
    img_dir_loc = get_safe_expedition_dir(expedition_id) if expedition_id else IMAGE_DIR
    os.makedirs(img_dir_loc, exist_ok=True)

    filepath = os.path.join(img_dir_loc, filename)
    print(f"---->0x100 [Capture] Saving uploaded image to {filepath}")

    # Save uploaded file
    contents = await image.read()
    with open(filepath, "wb") as f:
        f.write(contents)

    file_size = os.path.getsize(filepath)

    entry = {
        "file": filename,
        "timestamp": timestamp,
        "datetime_iso": datetime.utcnow().isoformat(),
        "location": {
            "latitude": latitude,
            "longitude": longitude,
            "altitude": altitude,
            "heading": heading,
        },
        "motion": {"speed": speed, "heading": heading},
        "environment": {"temperature": temperature, "humidity": humidity},
        "rover_status": {
            "battery_level": battery_level,
            "rover_id": rover_id,
            "mission_id": mission_id,
        },
        "camera": {"settings": camera_settings_dict, "file_size_bytes": file_size},
        "note": note,
        "tags": tags.split(",") if tags else [],
    }
    save_json_locked(META_FILE, lambda data: data + [entry])

    return {
        "status": "ok",
        "saved": filename,
        "metadata": entry,
        "file_size_mb": round(file_size / (1024 * 1024), 2),
    }


@router.post("/waypoint")
async def add_waypoint(
    latitude: float = Form(0),
    longitude: float = Form(0),
    altitude: float = Form(0),
    mission_id: str = Form("default"),
    rover_id: str = Form("rover_001"),
    name: str = Form(None),
    category: str = Form("general"),
    description: str = Form(""),
    auto_generated: str = Form("false"),
):
    """Add a waypoint (manual or auto). If 'name' is provided, it's manual; otherwise auto-generated."""
    waypoints = load_json(WAYPOINT_FILE)
    with open(f"/home/administratror/DEBUG_CAMS_CSRAL/logger_{G_C_NAME}.log", "a") as out:
        out.write("WAYPOINT ENDPOINT: Accessing it gng")

    is_auto_generated = False

    if not name:
        # Auto-generate name
        waypoint_count = len(
            [wp for wp in waypoints if wp.get("mission_id") == mission_id]
        )
        name = f"Auto Waypoint {waypoint_count + 1}"
        is_auto_generated = True
        category = "auto"
        description = f"Automatically generated waypoint during {mission_id}"
    else:
        # Manual waypoint
        is_auto_generated = auto_generated.lower() == "true"

    # Create waypoint entry
    entry = {
        "name": name,
        "location": {
            "latitude": latitude,
            "longitude": longitude,
            "altitude": altitude,
        },
        "category": category,
        "description": description,
        "mission_id": mission_id,
        "rover_id": rover_id,
        "auto_generated": is_auto_generated,
        "timestamp": datetime.utcnow().isoformat(),
        "timestamp_readable": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "waypoint_id": f"wp_{len(waypoints) + 1:03d}",
    }

    waypoints.append(entry)
    save_json(WAYPOINT_FILE, waypoints)

    return {"status": "ok", "waypoint": entry}


@router.get("/get_waypoints")
async def get_waypoints(mission_id: str = Query(None)):
    """Get waypoints"""
    with open(f"/home/administratror/DEBUG_CAMS_CSRAL/logger_{G_C_NAME}.log", "a") as out:
        out.write("GET WAYPOINTS ENDPOINT: Accessing it gng")
    waypoints = load_json(WAYPOINT_FILE)

    if mission_id:
        waypoints = [wp for wp in waypoints if wp.get("mission_id") == mission_id]

    return {"status": "ok", "waypoints": waypoints, "count": len(waypoints)}


@router.get("/get_metadata")
async def get_metadata(mission_id: str = Query(None)):
    """Get image metadata"""
    with open(f"/home/administratror/DEBUG_CAMS_CSRAL/logger_{G_C_NAME}.log", "a") as out:
        out.write("GET METADATA ENDPOINT: Accessing it gng")
    metadata = load_json(META_FILE)

    if mission_id:
        metadata = [
            md
            for md in metadata
            if md.get("rover_status", {}).get("mission_id") == mission_id
        ]

    return {"status": "ok", "metadata": metadata, "count": len(metadata)}


@router.post("/capture_test_data")
async def capture_test_data(
    title: str = Form("Rover Mission Capture"),
    description: str = Form("Camera feed screenshot with metadata"),
    latitude: float = Form(37.7749),
    longitude: float = Form(-122.4194),
    altitude: float = Form(100.5),
    heading: float = Form(45.0),
    speed: float = Form(1.5),
    battery_level: float = Form(85.0),
    temperature: float = Form(22.0),
    humidity: float = Form(50.0),
    mission_id: str = Form("rover_challenge_mission"),
    rover_id: str = Form("rover_challenge_001"),
    note: str = Form("Rover mission data capture"),
):
    """Generate test rover image with metadata - useful for testing and demos"""
    with open(f"/home/administratror/DEBUG_CAMS_CSRAL/logger_{G_C_NAME}.log", "a") as out:
        out.write("CAPTURE TEST ENDPOINT: Accessing it gng")
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise HTTPException(
            status_code=500, detail="PIL not installed. Run: pip install pillow"
        )

    # Create test image
    img = Image.new("RGB", (800, 600), color="lightblue")
    draw = ImageDraw.Draw(img)

    try:
        font_large = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28
        )
        font_medium = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18
        )
    except:
        try:
            font_large = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 28)
            font_medium = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 18)
        except:
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()

    # Add content to image
    draw.text((30, 30), title, fill="black", font=font_large)
    draw.text((30, 80), description, fill="darkblue", font=font_medium)
    draw.text(
        (30, 120),
        f"Rover Mission - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        fill="gray",
        font=font_medium,
    )

    # Add rover visual
    draw.rectangle([30, 180, 770, 250], outline="black", width=3)
    draw.text((40, 200), "ROVER MISSION DATA CAPTURED", fill="black", font=font_medium)

    # Add mission info
    draw.text(
        (30, 300),
        f"GPS Coordinates: {latitude}, {longitude}",
        fill="darkgreen",
        font=font_medium,
    )
    draw.text(
        (30, 330),
        f"Battery Level: {battery_level}%",
        fill="darkgreen",
        font=font_medium,
    )
    draw.text(
        (30, 360), f"Temperature: {temperature}°C", fill="darkgreen", font=font_medium
    )
    draw.text(
        (30, 390), f"Mission ID: {mission_id}", fill="darkgreen", font=font_medium
    )

    # Border
    draw.rectangle([10, 10, 790, 590], outline="black", width=4)

    # Save image
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_rover_test_capture.jpg"
    filepath = os.path.join(IMAGE_DIR, filename)
    img.save(filepath, "JPEG", quality=95)

    file_size = os.path.getsize(filepath)

    # Create metadata entry
    metadata = load_json(META_FILE)
    entry = {
        "file": filename,
        "timestamp": timestamp,
        "datetime_iso": datetime.utcnow().isoformat(),
        "location": {
            "latitude": latitude,
            "longitude": longitude,
            "altitude": altitude,
            "heading": heading,
        },
        "motion": {"speed": speed, "heading": heading},
        "environment": {"temperature": temperature, "humidity": humidity},
        "rover_status": {
            "battery_level": battery_level,
            "rover_id": rover_id,
            "mission_id": mission_id,
        },
        "camera": {
            "settings": {"resolution": "800x600", "test_image": True},
            "file_size_bytes": file_size,
        },
        "note": note,
        "tags": ["rover", "test", "generated"],
    }

    metadata.append(entry)
    save_json(META_FILE, metadata)

    return {
        "status": "ok",
        "message": "Test data captured successfully",
        "saved": filename,
        "filepath": filepath,
        "file_size_bytes": file_size,
        "file_size_kb": round(file_size / 1024, 2),
        "metadata": entry,
        "total_captures": len(metadata),
    }
