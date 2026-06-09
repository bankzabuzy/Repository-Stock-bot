from flask import Blueprint, jsonify

v41_top5_bp = Blueprint("v41_top5", __name__)

@v41_top5_bp.route("/v41/top5")
def top5():

    picks = [
        {
            "rank": 1,
            "symbol": "TSM",
            "score": 94,
            "regime": "STRONG UPTREND"
        },
        {
            "rank": 2,
            "symbol": "QQQ",
            "score": 91,
            "regime": "UPTREND"
        },
        {
            "rank": 3,
            "symbol": "SCB",
            "score": 88,
            "regime": "STRONG UPTREND"
        },
        {
            "rank": 4,
            "symbol": "AAOI",
            "score": 87,
            "regime": "UPTREND"
        },
        {
            "rank": 5,
            "symbol": "TJX",
            "score": 85,
            "regime": "STRONG UPTREND"
        }
    ]

    return jsonify({
        "version": "V41_TOP5_INSTITUTIONAL",
        "top5": picks
    })
