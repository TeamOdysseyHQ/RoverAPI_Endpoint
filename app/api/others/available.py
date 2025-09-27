from flask import Blueprint, request, jsonify
from app.py_types import listOfStrings

bp = Blueprint("o_avail", __name__)

def o_avi_l_ret() -> listOfStrings:
    
    #* Add all endpoints here without fail.
    return [
        "available", "test"
    ]

@bp.route("/available", methods=["POST"])
def o_avi():
    if request.method != "POST":
        return jsonify({
            "message": f"Invalid Request: {request.method}. Not allowed!",
            "status": "Failed",
            "success": False
        }), 405

    return jsonify({
        "success": True,
        "status": "Success",
        "endpoints": o_avi_l_ret()
    }), 200