from flask import Blueprint

bp = Blueprint("root", __name__)

@bp.route("/", methods=["GET"])
def test():
    return "Success"