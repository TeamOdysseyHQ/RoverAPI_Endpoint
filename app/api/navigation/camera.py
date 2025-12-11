from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from datetime import datetime
import os, json
from pathlib import Path

router = APIRouter()

IMAGE_DIR = "storage/images"
META_FILE = "storage/metadata.json"
WAYPOINT_FILE = "storage/waypoints.json"

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs("storage/reports", exist_ok=True)

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
    note: str = Form(''),
    mission_id: str = Form('default'),
    rover_id: str = Form('rover_001'),
    camera_settings: str = Form('{}'),
    tags: str = Form('')
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
            "heading": heading
        },
        "motion": {
            "speed": speed,
            "heading": heading
        },
        "environment": {
            "temperature": temperature,
            "humidity": humidity
        },
        "rover_status": {
            "battery_level": battery_level,
            "rover_id": rover_id,
            "mission_id": mission_id
        },
        "camera": {
            "settings": camera_settings_dict,
            "file_size_bytes": file_size
        },
        "note": note,
        "tags": tags.split(',') if tags else []
    }
    metadata.append(entry)
    save_json(META_FILE, metadata)
    
    return {
        "status": "ok", 
        "saved": filename, 
        "metadata": entry,
        "file_size_mb": round(file_size / (1024 * 1024), 2)
    }

@router.post("/waypoint")
async def add_waypoint(
    latitude: float = Form(0),
    longitude: float = Form(0),
    altitude: float = Form(0),
    mission_id: str = Form('default'),
    rover_id: str = Form('rover_001'),
    name: str = Form(None),
    category: str = Form('general'),
    description: str = Form(''),
    auto_generated: str = Form('false')
):
    """Add a waypoint (manual or auto). If 'name' is provided, it's manual; otherwise auto-generated."""
    waypoints = load_json(WAYPOINT_FILE)

    is_auto_generated = False

    if not name:
        # Auto-generate name
        waypoint_count = len([wp for wp in waypoints if wp.get('mission_id') == mission_id])
        name = f"Auto Waypoint {waypoint_count + 1}"
        is_auto_generated = True
        category = "auto"
        description = f"Automatically generated waypoint during {mission_id}"
    else:
        # Manual waypoint
        is_auto_generated = auto_generated.lower() == 'true'

    # Create waypoint entry
    entry = {
        "name": name,
        "location": {
            "latitude": latitude,
            "longitude": longitude,
            "altitude": altitude
        },
        "category": category,
        "description": description,
        "mission_id": mission_id,
        "rover_id": rover_id,
        "auto_generated": is_auto_generated,
        "timestamp": datetime.utcnow().isoformat(),
        "timestamp_readable": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "waypoint_id": f"wp_{len(waypoints) + 1:03d}"
    }

    waypoints.append(entry)
    save_json(WAYPOINT_FILE, waypoints)

    return {"status": "ok", "waypoint": entry}


@router.get("/get_waypoints")
async def get_waypoints(mission_id: str = Query(None)):
    """Get waypoints"""
    waypoints = load_json(WAYPOINT_FILE)
    
    if mission_id:
        waypoints = [wp for wp in waypoints if wp.get('mission_id') == mission_id]
    
    return {
        "status": "ok",
        "waypoints": waypoints,
        "count": len(waypoints)
    }

@router.get("/get_metadata")
async def get_metadata(mission_id: str = Query(None)):
    """Get image metadata"""
    metadata = load_json(META_FILE)
    
    if mission_id:
        metadata = [md for md in metadata if md.get('rover_status', {}).get('mission_id') == mission_id]
    
    return {
        "status": "ok",
        "metadata": metadata,
        "count": len(metadata)
    }

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
    note: str = Form("Rover mission data capture")
):
    """Generate test rover image with metadata - useful for testing and demos"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise HTTPException(status_code=500, detail="PIL not installed. Run: pip install pillow")
    
    # Create test image
    img = Image.new('RGB', (800, 600), color='lightblue')
    draw = ImageDraw.Draw(img)
    
    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except:
        try:
            font_large = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 28)
            font_medium = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 18)
        except:
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
    
    # Add content to image
    draw.text((30, 30), title, fill='black', font=font_large)
    draw.text((30, 80), description, fill='darkblue', font=font_medium)
    draw.text((30, 120), f"Rover Mission - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 
              fill='gray', font=font_medium)
    
    # Add rover visual
    draw.rectangle([30, 180, 770, 250], outline='black', width=3)
    draw.text((40, 200), "ROVER MISSION DATA CAPTURED", fill='black', font=font_medium)
    
    # Add mission info
    draw.text((30, 300), f"GPS Coordinates: {latitude}, {longitude}", fill='darkgreen', font=font_medium)
    draw.text((30, 330), f"Battery Level: {battery_level}%", fill='darkgreen', font=font_medium)
    draw.text((30, 360), f"Temperature: {temperature}°C", fill='darkgreen', font=font_medium)
    draw.text((30, 390), f"Mission ID: {mission_id}", fill='darkgreen', font=font_medium)
    
    # Border
    draw.rectangle([10, 10, 790, 590], outline='black', width=4)
    
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
            "heading": heading
        },
        "motion": {
            "speed": speed,
            "heading": heading
        },
        "environment": {
            "temperature": temperature,
            "humidity": humidity
        },
        "rover_status": {
            "battery_level": battery_level,
            "rover_id": rover_id,
            "mission_id": mission_id
        },
        "camera": {
            "settings": {"resolution": "800x600", "test_image": True},
            "file_size_bytes": file_size
        },
        "note": note,
        "tags": ["rover", "test", "generated"]
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
        "total_captures": len(metadata)
    }