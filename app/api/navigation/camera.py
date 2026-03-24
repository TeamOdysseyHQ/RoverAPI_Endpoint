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


# Camera hardware management
class MultiCameraManager:
    def __init__(self):
        self.cameras: dict[str, cv2.VideoCapture] = {}
        self.camera_info: dict[str, dict] = {}
        self.streaming_status: dict[str, bool] = {}
        self.lock = threading.RLock()  # Use RLock to allow reentrant locking
        self._executor = ThreadPoolExecutor(max_workers=2)

        # WebSocket client tracking
        self.ws_clients: dict[str, list] = {}  # camera_name -> list of WebSocket refs

    def _open_camera_with_timeout(
        self, camera_name: str, timeout: float = 5.0
    ) -> Optional[cv2.VideoCapture]:
        """Open camera with timeout to prevent hanging"""

        def open_camera():
            # Check if it's a named camera first
            device_path = CAMERA_DEVICES.get(camera_name)

            # If not a named camera, check if it's a video device (e.g., "video0")
            if device_path is None and camera_name.startswith("video"):
                try:
                    video_index = int(camera_name.replace("video", ""))
                    device_path = f"/dev/video{video_index}"
                except ValueError:
                    print(f"[Camera] Invalid video device name: {camera_name}")
                    return None

            if device_path is None:
                print(f"[Camera] Unknown camera name: {camera_name}")
                return None

            if not os.path.exists(device_path):
                print(
                    f"[Camera] Device path {device_path} not found for camera {camera_name}"
                )
                return None

            print(f"[Camera] Opening {camera_name} at {device_path}")
            return cv2.VideoCapture(device_path)

        try:
            future = self._executor.submit(open_camera)
            return future.result(timeout=timeout)
        except FuturesTimeoutError:
            print(f"[Camera] Timeout opening camera {camera_name}")
            return None
        except Exception as e:
            print(f"[Camera] Error opening camera {camera_name}: {e}")
            return None

    def detect_cameras(self):
        """Detect all available cameras by checking device paths and /dev/video* devices"""
        available = []
        used_device_paths = set()

        # First, detect named cameras
        for camera_name, device_path in CAMERA_DEVICES.items():
            used_device_paths.add(device_path)

            # Skip if camera is already active
            if camera_name in self.cameras:
                info = self.camera_info.get(camera_name, {})
                available.append(
                    {
                        "name": camera_name,
                        "device_path": device_path,
                        "backend": "V4L2",
                        "default_resolution": f"{info.get('width', 640)}x{info.get('height', 480)}",
                        "default_fps": info.get("fps", 30),
                        "active": True,
                        "is_named": True,
                    }
                )
                continue

            # Check if device exists
            if not os.path.exists(device_path):
                print(f"[Camera] Device {device_path} not found for {camera_name}")
                continue

            # Try to open camera to get info
            cap = self._open_camera_with_timeout(camera_name, timeout=2.0)
            if cap is not None and cap.isOpened():
                # Get camera info
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = int(cap.get(cv2.CAP_PROP_FPS))

                # Try to get camera backend
                backend = cap.getBackendName()

                available.append(
                    {
                        "name": camera_name,
                        "device_path": device_path,
                        "backend": backend,
                        "default_resolution": f"{width}x{height}",
                        "default_fps": fps,
                        "active": camera_name in self.cameras,
                        "is_named": True,
                    }
                )
                cap.release()

        # Now detect /dev/video* devices
        print("[Camera] Scanning for /dev/video* devices...")
        video_devices = []
        for i in range(20):  # Check /dev/video0 through /dev/video19
            device_path = f"/dev/video{i}"

            # Check if device exists
            if not os.path.exists(device_path):
                continue

            print(f"[Camera] Found {device_path}, checking if it's a capture device...")

            # Skip if already in named cameras
            if device_path in used_device_paths:
                print(
                    f"[Camera] Skipping {device_path} - already mapped as named camera"
                )
                continue

            # Check if this is a capture device (not a metadata device)
            # Metadata devices can't be opened for capture
            is_capture_device = False
            try:
                # Try to detect if this is a capture-capable device using v4l2
                result = subprocess.run(
                    ["v4l2-ctl", "-d", device_path, "--list-formats"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                # Check if it's a video capture device
                if result.returncode == 0 and "Video Capture" in result.stdout:
                    is_capture_device = True
                    print(f"[Camera] {device_path} is a Video Capture device")
                else:
                    print(
                        f"[Camera] Skipping {device_path} - not a Video Capture device"
                    )
            except FileNotFoundError:
                # v4l2-ctl not available, try opening anyway
                print(
                    f"[Camera] v4l2-ctl not available, attempting to open {device_path} directly"
                )
                is_capture_device = True
            except subprocess.TimeoutExpired:
                print(f"[Camera] v4l2-ctl timeout for {device_path}, skipping")
            except Exception as e:
                print(f"[Camera] v4l2-ctl error for {device_path}: {e}")
                is_capture_device = True  # Try anyway

            if not is_capture_device:
                continue

            # Generate a name for this video device
            video_name = f"video{i}"

            # Check if already active
            if video_name in self.cameras:
                info = self.camera_info.get(video_name, {})
                video_devices.append(
                    {
                        "name": video_name,
                        "device_path": device_path,
                        "backend": "V4L2",
                        "default_resolution": f"{info.get('width', 640)}x{info.get('height', 480)}",
                        "default_fps": info.get("fps", 30),
                        "active": True,
                        "is_named": False,
                    }
                )
                print(f"[Camera] Added active {video_name} ({device_path})")
                continue

            # Try to open device to get info
            print(f"[Camera] Attempting to open {video_name} at {device_path}...")
            try:
                cap = cv2.VideoCapture(device_path)
                if cap is not None and cap.isOpened():
                    # Get camera info
                    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    fps = int(cap.get(cv2.CAP_PROP_FPS))
                    backend = cap.getBackendName()

                    video_devices.append(
                        {
                            "name": video_name,
                            "device_path": device_path,
                            "backend": backend,
                            "default_resolution": f"{width}x{height}",
                            "default_fps": fps,
                            "active": False,
                            "is_named": False,
                        }
                    )
                    print(
                        f"[Camera] Successfully detected {video_name}: {width}x{height} @ {fps}fps ({backend})"
                    )
                    cap.release()
                else:
                    print(f"[Camera] Failed to open {device_path}")
            except Exception as e:
                print(f"[Camera] Error opening {device_path}: {e}")
                continue

        print(f"[Camera] Found {len(video_devices)} generic video device(s)")
        # Append video devices to the end
        available.extend(video_devices)
        return available

    def start_camera(
        self, camera_name: str, width: int = 640, height: int = 480, fps: int = 30
    ):
        """Initialize specific camera"""
        with self.lock:
            if camera_name in self.cameras and self.cameras[camera_name].isOpened():
                return True

            print(f"[Camera] Opening camera {camera_name}...")
            camera = self._open_camera_with_timeout(camera_name, timeout=5.0)

            if camera is None:
                print(f"[Camera] Failed to open camera {camera_name} (timeout)")
                return False

            if not camera.isOpened():
                print(f"[Camera] Camera {camera_name} not opened")
                return False

            print(
                f"[Camera] Setting camera {camera_name} to {width}x{height} @ {fps}fps"
            )
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            camera.set(cv2.CAP_PROP_FPS, fps)

            self.cameras[camera_name] = camera

            # Determine device path for video devices
            device_path = CAMERA_DEVICES.get(camera_name, "")
            if not device_path and camera_name.startswith("video"):
                try:
                    video_index = int(camera_name.replace("video", ""))
                    device_path = f"/dev/video{video_index}"
                except ValueError:
                    pass

            self.camera_info[camera_name] = {
                "width": width,
                "height": height,
                "fps": fps,
                "device_path": device_path,
            }
            self.streaming_status[camera_name] = False
            print(f"[Camera] Camera {camera_name} started successfully")
            return True

    def stop_camera(self, camera_name: str):
        """Release specific camera"""
        with self.lock:
            if camera_name in self.cameras:
                self.cameras[camera_name].release()
                del self.cameras[camera_name]
                del self.camera_info[camera_name]
                del self.streaming_status[camera_name]
                return True
            return False

    def stop_all_cameras(self):
        """Release all cameras"""
        with self.lock:
            for camera in self.cameras.values():
                camera.release()
            self.cameras.clear()
            self.camera_info.clear()
            self.streaming_status.clear()

    def capture_frame(self, camera_name: str):
        """Capture a single frame from specific camera"""
        with self.lock:
            if camera_name not in self.cameras:
                return None

            camera = self.cameras[camera_name]
            if not camera.isOpened():
                return None

            ret, frame = camera.read()
            if not ret:
                return None
            return frame

    def get_camera_status(self, camera_name: str):
        """Get specific camera status"""
        with self.lock:
            if (
                camera_name not in self.cameras
                or not self.cameras[camera_name].isOpened()
            ):
                return {"active": False, "streaming": False, "ws_clients": 0}

            camera = self.cameras[camera_name]
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
        """Get status of all cameras"""
        with self.lock:
            statuses = {}
            for name in self.cameras.keys():
                camera = self.cameras[name]
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

    # WebSocket client management methods

    def add_ws_client(self, camera_name: str, websocket):
        """Register WebSocket client for camera"""
        with self.lock:
            if camera_name not in self.ws_clients:
                self.ws_clients[camera_name] = []
            self.ws_clients[camera_name].append(websocket)

    def remove_ws_client(self, camera_name: str, websocket):
        """Unregister WebSocket client"""
        with self.lock:
            if camera_name in self.ws_clients:
                if websocket in self.ws_clients[camera_name]:
                    self.ws_clients[camera_name].remove(websocket)

                # Cleanup empty list
                if not self.ws_clients[camera_name]:
                    del self.ws_clients[camera_name]

    def get_ws_client_count(self, camera_name: str) -> int:
        """Get WebSocket client count for camera"""
        with self.lock:
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
    cameras = camera_manager.detect_cameras()
    return {"status": "ok", "cameras": cameras, "count": len(cameras)}


@router.get("/cameras/{camera_name}/resolutions")
async def get_camera_resolutions(camera_name: str):
    """Get supported resolutions for a specific camera"""
    # Validate camera name (named camera or video device)
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
):
    """Start specific camera"""
    # Validate camera name (named camera or video device)
    is_valid = camera_name in CAMERA_DEVICES or (
        camera_name.startswith("video") and camera_name[5:].isdigit()
    )

    if not is_valid:
        raise HTTPException(
            status_code=404,
            detail=f"Camera '{camera_name}' not found. Available named cameras: {', '.join(CAMERA_DEVICES.keys())}. Also supports video0, video1, etc.",
        )

    success = camera_manager.start_camera(camera_name, width, height, fps)
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
    success = camera_manager.stop_camera(camera_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"Camera '{camera_name}' not found")
    return {"status": "ok", "message": f"Camera '{camera_name}' stopped"}


@router.post("/cameras/stop_all")
async def stop_all_cameras():
    """Stop all cameras"""
    camera_manager.stop_all_cameras()
    return {"status": "ok", "message": "All cameras stopped"}


@router.get("/cameras/status")
async def cameras_status():
    """Get status of all cameras"""
    return {"status": "ok", "cameras": camera_manager.get_all_statuses()}


@router.get("/cameras/{camera_name}/status")
async def camera_status(camera_name: str):
    """Get specific camera status"""
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
    waypoints = load_json(WAYPOINT_FILE)

    if mission_id:
        waypoints = [wp for wp in waypoints if wp.get("mission_id") == mission_id]

    return {"status": "ok", "waypoints": waypoints, "count": len(waypoints)}


@router.get("/get_metadata")
async def get_metadata(mission_id: str = Query(None)):
    """Get image metadata"""
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
