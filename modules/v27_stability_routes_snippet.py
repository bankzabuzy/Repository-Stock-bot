from flask import jsonify, request
from modules.v27_forward_test_engine import ForwardTestEngine
from modules.v27_outcome_tracker import OutcomeTracker
from modules.v27_data_quality_guard import DataQualityGuard
from modules.v27_capital_protection import CapitalProtection

def register_v27_stability_routes(app):
    @app.route("/v27/forward-test/create", methods=["POST"])
    def v27_forward_test_create():
        return jsonify(ForwardTestEngine().create_signal(request.get_json(silent=True) or {}))

    @app.route("/v27/outcome/check", methods=["POST"])
    def v27_outcome_check():
        payload = request.get_json(silent=True) or {}
        return jsonify(OutcomeTracker().evaluate_price(payload.get("signal", {}), payload.get("current_price", 0)))

    @app.route("/v27/data-quality", methods=["POST"])
    def v27_data_quality():
        payload = request.get_json(silent=True) or {}
        return jsonify(DataQualityGuard().should_block_alert(payload.get("quote", {}), payload.get("indicators", {})))

    @app.route("/v27/capital-protection", methods=["POST"])
    def v27_capital_protection():
        return jsonify(CapitalProtection().evaluate(request.get_json(silent=True) or {}))

    @app.route("/v27/position-multiplier", methods=["POST"])
    def v27_position_multiplier():
        return jsonify(CapitalProtection().position_size_multiplier(request.get_json(silent=True) or {}))
