from flask import Blueprint, jsonify

v41_top5_bp = Blueprint("v41_top5", __name__)

@v41_top5_bp.route("/v41/top5")
def top5():
    return jsonify({
        "version": "V41_TOP5_INSTITUTIONAL",
        "status": "OK"
    })
