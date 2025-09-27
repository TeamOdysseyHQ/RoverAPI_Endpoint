from flask import Blueprint, request, jsonify
from app.py_types import listOfStrings

bp = Blueprint("sci_avail", __name__)

def sci_avi_l_ret() -> listOfStrings:
    
    #* Add all endpoints here without fail.
    return [
        "available"
    ]

@bp.route("/available", methods=["POST"])
def sci_avi():
    if request.method != "POST":
        return jsonify({
            "message": f"Invalid Request: {request.method}. Not allowed!",
            "status": "Failed",
            "success": False
        }), 405

    return jsonify({
        "success": True,
        "status": "Success",
        "endpoints": sci_avi_l_ret()
    }), 200