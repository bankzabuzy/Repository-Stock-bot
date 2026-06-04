
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
class ForwardTestEngine:

    def __init__(self):
        self.trades = []

    def record_signal(self, symbol, signal_type=None, score=None, price=None, metadata=None):
        row = {
            "symbol": symbol,
            "signal_type": signal_type,
            "score": score,
            "price": price,
            "metadata": metadata or {},
        }
        self.trades.append(row)
        return row

    def evaluate(self):
        return {
            "total_signals": len(self.trades),
            "win_rate": 0.0,
            "avg_return": 0.0,
            "max_drawdown": 0.0,
        }
