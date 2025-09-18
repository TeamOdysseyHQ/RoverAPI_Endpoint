from flask import Blueprint, request, jsonify
from app.utils import validate_requests_body

bp = Blueprint("logs", __name__)

@bp.route("/save_log", methods=["POST"])
def api_save_log():
    if request.method != "POST":
        return jsonify({
            "message": f"Invalid Request: {request.method}. Not allowed!",
            "status": "Failed",
            "success": False
        }), 405

    data = request.get_json(silent=True) or {}
    if not validate_requests_body(data, ['department', 'content']):
        return jsonify({
            "message": "Invalid POST Request: Missing one or more fields.",
            "status": "Failed",
            "success": False
        }), 400

    print(f"Department: {data['department']} and Content: {data['content']}")
    with open("test.txt", "w") as out:
        out.write(f"Department: {data['department']} and Content: {data['content']}")

    return jsonify({
        "success": True,
        "status": "Success",
        "message": "Log saved."
    }), 200

# Optional: expose ros2 doctor output (run in the same environment where ROS 2 is installed)
