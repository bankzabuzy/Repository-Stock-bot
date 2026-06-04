
"""
V27.1 Integration Phase route snippet
เชื่อม Alert Pipeline เข้า Flask

ให้เพิ่มใน main.py:
from modules.v27_integration_routes_snippet import register_v27_integration_routes
register_v27_integration_routes(app)
"""

from flask import jsonify, request
from modules.v27_integration_pipeline import AlertIntegrationPipeline, demo_signal


def register_v27_integration_routes(app):
    @app.route("/v27/integration/pipeline", methods=["POST", "GET"])
    def v27_integration_pipeline():
        if request.method == "POST":
            payload = request.get_json(silent=True) or {}
            signal = payload.get("signal", payload)
            market_state = payload.get("market_state", {})
        else:
            signal = demo_signal()
            market_state = {
                "alerts_today": 0,
                "daily_return_r": 0,
                "consecutive_losses": 0,
                "breadth_score": 76,
                "vix": 18,
            }

        result = AlertIntegrationPipeline().evaluate(signal, market_state)
        return jsonify(result)

    @app.route("/v27/integration/health")
    def v27_integration_health():
        return jsonify({
            "ok": True,
            "version": "V27.1 Integration Phase",
            "pipeline": "Data Quality -> Capital Protection -> Conviction -> Adaptive Weight -> Forward Test -> LINE",
            "forward_test_days": 30,
        })
class AlertAuditLogEngine:

    def __init__(self):
        self.logs = []

    def record(self, alert):
        self.logs.append(alert)
        return True

    def get_logs(self):
        return self.logs

    def count(self):
        return len(self.logs)
