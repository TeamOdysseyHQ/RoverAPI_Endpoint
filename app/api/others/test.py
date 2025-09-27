from flask import Blueprint, request, jsonify

bp = Blueprint("test", __name__)

@bp.route("/test", methods=["POST"])
def api_test_point():
    if request.method != "POST":
        return jsonify({
            "message": f"Invalid Request: {request.method}. Not allowed!",
            "status": "Failed",
            "success": False
        }), 405

    return jsonify({
        "success": True,
        "status": "Success",
        "message": "The POST Request was successfully validated. Check the data we received.",
        "data": request.get_json(silent=True)
    }), 200