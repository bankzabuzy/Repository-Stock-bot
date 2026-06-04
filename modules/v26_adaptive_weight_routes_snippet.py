
"""
Optional Flask route snippet for V26.9.
คัดลอกไปเชื่อมใน main.py หากต้องการเปิด API โดยตรง
"""

from flask import jsonify, request
from modules.v26_adaptive_weight_engine import AdaptiveWeightEngine, demo_rows

def register_v26_adaptive_weight_routes(app):
    @app.route("/v26/adaptive-weights")
    def v26_adaptive_weights():
        engine = AdaptiveWeightEngine()
        result = engine.learn_from_rows(demo_rows())
        return jsonify(result)

    @app.route("/v26/adaptive-score")
    def v26_adaptive_score():
        base_score = float(request.args.get("base_score", 84))
        factor_scores = {
            "rsi": float(request.args.get("rsi", 60)),
            "rvol": float(request.args.get("rvol", 80)),
            "option_flow": float(request.args.get("option_flow", 80)),
            "news_sentiment": float(request.args.get("news_sentiment", 60)),
            "market_breadth": float(request.args.get("market_breadth", 60)),
            "sector_rotation": float(request.args.get("sector_rotation", 70)),
        }
        engine = AdaptiveWeightEngine()
        engine.learn_from_rows(demo_rows())
        return jsonify(engine.apply_to_score(factor_scores, base_score=base_score))
