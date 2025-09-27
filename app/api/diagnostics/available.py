from flask import Blueprint, request, jsonify
from app.py_types import listOfStrings

bp = Blueprint("dgt_avail", __name__)

def dgt_avi_l_ret() -> listOfStrings:
    
    #* Add all endpoints here without fail.
    return [
        "available", "doctor"
    ]

@bp.route("/available", methods=["POST"])
def dgt_avi():
    if request.method != "POST":
        return jsonify({
            "message": f"Invalid Request: {request.method}. Not allowed!",
            "status": "Failed",
            "success": False
        }), 405

    return jsonify({
        "success": True,
        "status": "Success",
        "endpoints": dgt_avi_l_ret()
    }), 200