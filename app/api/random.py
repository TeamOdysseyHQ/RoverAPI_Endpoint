from flask import Blueprint, jsonify
import os

# Create a blueprint (so we can register it in main.py)
random_bp = Blueprint("random", __name__)

@random_bp.route("/random_command", methods=["GET"])
def random_command():
    dummy_data = {
        "rover_id": "RoverX-101",
        "status": "active",
        "battery": "87%",
        "system_time": os.popen("date").read().strip()  # runs a system command
    }
    return jsonify(dummy_data)
