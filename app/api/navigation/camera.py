from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from datetime import datetime
import os, json

bp = Blueprint("camera", __name__)

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

@bp.route("/capture", methods=["POST"])
def capture():

    """Capture camera screenshot with metadata"""
    if 'image' not in request.files:
        return jsonify({"error": "No image file provided"}), 400
    
    image = request.files['image']
    if image.filename == '':
        return jsonify({"error": "No image selected"}), 400
    
    try:

        latitude = float(request.form.get('latitude', 0))
        longitude = float(request.form.get('longitude', 0))
        altitude = float(request.form.get('altitude', 0))
        heading = float(request.form.get('heading', 0))
        speed = float(request.form.get('speed', 0))
        battery_level = float(request.form.get('battery_level', 100))
        temperature = float(request.form.get('temperature', 20))
        humidity = float(request.form.get('humidity', 50))

    except (TypeError, ValueError):
        return jsonify({"error": "Invalid numeric parameter"}), 400
    
    note = request.form.get('note', '')
    mission_id = request.form.get('mission_id', 'default')
    rover_id = request.form.get('rover_id', 'rover_001')
    
    camera_settings = request.form.get('camera_settings', '{}')
    
    try:
        camera_settings_dict = json.loads(camera_settings) if camera_settings else {}
    except json.JSONDecodeError:
        camera_settings_dict = {}
    
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{secure_filename(image.filename)}"
    filepath = os.path.join(IMAGE_DIR, filename)
    image.save(filepath)
    
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
        "tags": request.form.get('tags', '').split(',') if request.form.get('tags') else []
    }
    metadata.append(entry)
    save_json(META_FILE, metadata)
    
    return jsonify({
        "status": "ok", 
        "saved": filename, 
        "metadata": entry,
        "file_size_mb": round(file_size / (1024 * 1024), 2)
    })

@bp.route("/waypoint", methods=["POST"])
def add_waypoint():
    """Add a waypoint (manual or auto). If 'name' is provided, it's manual; otherwise auto-generated."""
    try:
        # Common parameters
        latitude = float(request.form.get('latitude', 0))
        longitude = float(request.form.get('longitude', 0))
        altitude = float(request.form.get('altitude', 0))
        mission_id = request.form.get('mission_id', 'default')
        rover_id = request.form.get('rover_id', 'rover_001')

        waypoints = load_json(WAYPOINT_FILE)

        name = request.form.get('name')
        auto_generated = False

        if not name:
            # Auto-generate name
            waypoint_count = len([wp for wp in waypoints if wp.get('mission_id') == mission_id])
            name = f"Auto Waypoint {waypoint_count + 1}"
            auto_generated = True
            category = "auto"
            description = f"Automatically generated waypoint during {mission_id}"
        else:
            # Manual waypoint
            category = request.form.get('category', 'general')
            description = request.form.get('description', '')
            auto_generated = request.form.get('auto_generated', 'false').lower() == 'true'

    except (TypeError, ValueError):
        return jsonify({"error": "Invalid numeric parameter"}), 400

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
        "auto_generated": auto_generated,
        "timestamp": datetime.utcnow().isoformat(),
        "timestamp_readable": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "waypoint_id": f"wp_{len(waypoints) + 1:03d}"
    }

    waypoints.append(entry)
    save_json(WAYPOINT_FILE, waypoints)

    return jsonify({"status": "ok", "waypoint": entry})


@bp.route("/get_waypoints", methods=["GET"])
def get_waypoints():

    """Get waypoints"""
    mission_id = request.args.get('mission_id')
    waypoints = load_json(WAYPOINT_FILE)
    
    if mission_id:
        waypoints = [wp for wp in waypoints if wp.get('mission_id') == mission_id]
    
    return jsonify({
        "status": "ok",
        "waypoints": waypoints,
        "count": len(waypoints)
    })

@bp.route("/get_metadata", methods=["GET"])
def get_metadata():

    """Get image metadata"""
    mission_id = request.args.get('mission_id')
    metadata = load_json(META_FILE)
    
    if mission_id:
        metadata = [md for md in metadata if md.get('rover_status', {}).get('mission_id') == mission_id]
    
    return jsonify({
        "status": "ok",
        "metadata": metadata,
        "count": len(metadata)
    })