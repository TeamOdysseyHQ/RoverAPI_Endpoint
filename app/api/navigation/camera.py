from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import StreamingResponse
from datetime import datetime
import os, json, cv2, threading
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

router = APIRouter()

IMAGE_DIR = "storage/images"
META_FILE = "storage/metadata.json"
WAYPOINT_FILE = "storage/waypoints.json"

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs("storage/reports", exist_ok=True)


# Camera hardware management
class MultiCameraManager:
    def __init__(self):
        self.cameras: dict[int, cv2.VideoCapture] = {}
        self.camera_info: dict[int, dict] = {}
        self.streaming_status: dict[int, bool] = {}
        self.lock = threading.RLock()  # Use RLock to allow reentrant locking
        self._executor = ThreadPoolExecutor(max_workers=2)

        # WebSocket client tracking
        self.ws_clients: dict[int, list] = {}  # camera_index -> list of WebSocket refs

    def _open_camera_with_timeout(self, camera_index: int, timeout: float = 5.0):
        """Open camera with timeout to prevent hanging"""

        def open_camera():
            return cv2.VideoCapture(camera_index)

        try:
            future = self._executor.submit(open_camera)
            return future.result(timeout=timeout)
        except FuturesTimeoutError:
            print(f"[Camera] Timeout opening camera {camera_index}")
            return None
        except Exception as e:
            print(f"[Camera] Error opening camera {camera_index}: {e}")
            return None

    def detect_cameras(self, max_cameras: int = 10):
        """Detect all available cameras"""
        available = []
        for index in range(max_cameras):
            # Skip if camera is already active
            if index in self.cameras:
                info = self.camera_info.get(index, {})
                available.append(
                    {
                        "index": index,
                        "backend": "V4L2",
                        "default_resolution": f"{info.get('width', 640)}x{info.get('height', 480)}",
                        "default_fps": info.get("fps", 30),
                        "active": True,
                    }
                )
                continue

            cap = self._open_camera_with_timeout(index, timeout=2.0)
            if cap is not None and cap.isOpened():
                # Get camera info
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = int(cap.get(cv2.CAP_PROP_FPS))

                # Try to get camera name (platform-specific)
                backend = cap.getBackendName()

                available.append(
                    {
                        "index": index,
                        "backend": backend,
                        "default_resolution": f"{width}x{height}",
                        "default_fps": fps,
                        "active": index in self.cameras,
                    }
                )
                cap.release()
        return available

    def start_camera(
        self, camera_index: int = 0, width: int = 640, height: int = 480, fps: int = 30
    ):
        """Initialize specific camera"""
        with self.lock:
            if camera_index in self.cameras and self.cameras[camera_index].isOpened():
                return True

            print(f"[Camera] Opening camera {camera_index}...")
            camera = self._open_camera_with_timeout(camera_index, timeout=5.0)

            if camera is None:
                print(f"[Camera] Failed to open camera {camera_index} (timeout)")
                return False

            if not camera.isOpened():
                print(f"[Camera] Camera {camera_index} not opened")
                return False

            print(
                f"[Camera] Setting camera {camera_index} to {width}x{height} @ {fps}fps"
            )
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            camera.set(cv2.CAP_PROP_FPS, fps)

            self.cameras[camera_index] = camera
            self.camera_info[camera_index] = {
                "width": width,
                "height": height,
                "fps": fps,
            }
            self.streaming_status[camera_index] = False
            print(f"[Camera] Camera {camera_index} started successfully")
            return True

    def stop_camera(self, camera_index: int):
        """Release specific camera"""
        with self.lock:
            if camera_index in self.cameras:
                self.cameras[camera_index].release()
                del self.cameras[camera_index]
                del self.camera_info[camera_index]
                del self.streaming_status[camera_index]
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

    def capture_frame(self, camera_index: int):
        """Capture a single frame from specific camera"""
        with self.lock:
            if camera_index not in self.cameras:
                return None

            camera = self.cameras[camera_index]
            if not camera.isOpened():
                return None

            ret, frame = camera.read()
            if not ret:
                return None
            return frame

    def get_camera_status(self, camera_index: int):
        """Get specific camera status"""
        with self.lock:
            if (
                camera_index not in self.cameras
                or not self.cameras[camera_index].isOpened()
            ):
                return {"active": False, "streaming": False, "ws_clients": 0}

            camera = self.cameras[camera_index]
            return {
                "active": True,
                "streaming": self.streaming_status.get(camera_index, False),
                "camera_index": camera_index,
                "width": int(camera.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": int(camera.get(cv2.CAP_PROP_FPS)),
                "ws_clients": self.get_ws_client_count(camera_index),
            }

    def get_all_statuses(self):
        """Get status of all cameras"""
        with self.lock:
            statuses = {}
            for index in self.cameras.keys():
                camera = self.cameras[index]
                statuses[index] = {
                    "active": camera.isOpened(),
                    "streaming": self.streaming_status.get(index, False),
                    "width": int(camera.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    "height": int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                    "fps": int(camera.get(cv2.CAP_PROP_FPS)),
                }
            return statuses

    # WebSocket client management methods

    def add_ws_client(self, camera_index: int, websocket):
        """Register WebSocket client for camera"""
        with self.lock:
            if camera_index not in self.ws_clients:
                self.ws_clients[camera_index] = []
            self.ws_clients[camera_index].append(websocket)

    def remove_ws_client(self, camera_index: int, websocket):
        """Unregister WebSocket client"""
        with self.lock:
            if camera_index in self.ws_clients:
                if websocket in self.ws_clients[camera_index]:
                    self.ws_clients[camera_index].remove(websocket)

                # Cleanup empty list
                if not self.ws_clients[camera_index]:
                    del self.ws_clients[camera_index]

    def get_ws_client_count(self, camera_index: int) -> int:
        """Get WebSocket client count for camera"""
        with self.lock:
            return len(self.ws_clients.get(camera_index, []))


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


def secure_filename(filename: str) -> str:
    """Simple secure filename implementation"""
    return "".join(c for c in filename if c.isalnum() or c in "._-")


@router.get("/cameras/detect")
async def detect_cameras(max_cameras: int = Query(10)):
    """Detect all available cameras"""
    cameras = camera_manager.detect_cameras(max_cameras)
    return {"status": "ok", "cameras": cameras, "count": len(cameras)}


@router.post("/cameras/{camera_index}/start")
async def start_camera(
    camera_index: int,
    width: int = Form(640),
    height: int = Form(480),
    fps: int = Form(30),
):
    """Start specific camera"""
    success = camera_manager.start_camera(camera_index, width, height, fps)
    if not success:
        raise HTTPException(
            status_code=500, detail=f"Failed to open camera {camera_index}"
        )

    return {
        "status": "ok",
        "message": f"Camera {camera_index} started",
        "camera": camera_manager.get_camera_status(camera_index),
    }


@router.post("/cameras/{camera_index}/stop")
async def stop_camera(camera_index: int):
    """Stop specific camera"""
    success = camera_manager.stop_camera(camera_index)
    if not success:
        raise HTTPException(status_code=404, detail=f"Camera {camera_index} not found")
    return {"status": "ok", "message": f"Camera {camera_index} stopped"}


@router.post("/cameras/stop_all")
async def stop_all_cameras():
    """Stop all cameras"""
    camera_manager.stop_all_cameras()
    return {"status": "ok", "message": "All cameras stopped"}


@router.get("/cameras/status")
async def cameras_status():
    """Get status of all cameras"""
    return {"status": "ok", "cameras": camera_manager.get_all_statuses()}


@router.get("/cameras/{camera_index}/status")
async def camera_status(camera_index: int):
    """Get specific camera status"""
    return {"status": "ok", "camera": camera_manager.get_camera_status(camera_index)}


@router.post("/cameras/{camera_index}/capture")
async def capture_from_camera(
    camera_index: int,
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
):
    """Capture image from specific camera"""
    frame = camera_manager.capture_frame(camera_index)
    if frame is None:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to capture from camera {camera_index}. Is it started?",
        )

    # Save frame as JPEG
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_cam{camera_index}_capture.jpg"
    filepath = os.path.join(IMAGE_DIR, filename)

    cv2.imwrite(filepath, frame)
    file_size = os.path.getsize(filepath)

    # Get actual image dimensions
    height, width = frame.shape[:2]

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
            "camera_index": camera_index,
            "settings": {"resolution": f"{width}x{height}", "hardware_capture": True},
            "file_size_bytes": file_size,
        },
        "note": note,
        "tags": tags.split(",") if tags else [],
    }
    metadata.append(entry)
    save_json(META_FILE, metadata)

    return {
        "status": "ok",
        "message": f"Image captured from camera {camera_index}",
        "saved": filename,
        "metadata": entry,
        "file_size_mb": round(file_size / (1024 * 1024), 2),
    }


def generate_video_stream(camera_index: int):
    """Generator function for MJPEG video streaming from specific camera"""
    while True:
        frame = camera_manager.capture_frame(camera_index)
        if frame is None:
            break

        # Encode frame as JPEG
        ret, buffer = cv2.imencode(".jpg", frame)
        if not ret:
            continue

        frame_bytes = buffer.tobytes()

        # Yield frame in multipart format
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")


@router.get("/cameras/{camera_index}/stream")
async def video_stream(camera_index: int):
    """Stream live video feed from specific camera (MJPEG)"""
    status = camera_manager.get_camera_status(camera_index)
    if not status["active"]:
        raise HTTPException(
            status_code=400,
            detail=f"Camera {camera_index} not started. Call /cameras/{camera_index}/start first",
        )

    camera_manager.streaming_status[camera_index] = True
    return StreamingResponse(
        generate_video_stream(camera_index),
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
    filepath = os.path.join(IMAGE_DIR, filename)

    # Save uploaded file
    contents = await image.read()
    with open(filepath, "wb") as f:
        f.write(contents)

    file_size = os.path.getsize(filepath)

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
        "camera": {"settings": camera_settings_dict, "file_size_bytes": file_size},
        "note": note,
        "tags": tags.split(",") if tags else [],
    }
    metadata.append(entry)
    save_json(META_FILE, metadata)

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
