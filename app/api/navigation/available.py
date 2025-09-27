from flask import Blueprint, request, jsonify
from app.py_types import listOfStrings

bp = Blueprint("nav_avail", __name__)

def nav_avi_l_ret() -> listOfStrings:
    
    #* Add all endpoints here without fail.
    return [
        "report", "available", "capture", "waypoint", "get_waypoints", "get_metadata", "generate_report",
        "export_data", "reports", "route_analysis", "download/<filename>"
    ]

@bp.route("/available", methods=["POST"])
def nav_avi():
    if request.method != "POST":
        return jsonify({
            "message": f"Invalid Request: {request.method}. Not allowed!",
            "status": "Failed",
            "success": False
        }), 405

    return jsonify({
        "success": True,
        "status": "Success",
        "endpoints": nav_avi_l_ret()
    }), 200