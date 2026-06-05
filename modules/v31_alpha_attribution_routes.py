from __future__ import annotations

from flask import jsonify, request, Response

from modules.v31_alpha_attribution_core import (
    V31_VERSION,
    init_v31_db,
    record_signal_components,
    sync_from_v28_outcomes,
    component_attribution,
    recommend_weights,
    monte_carlo_risk,
    regime_attribution,
    optimize_portfolio_candidates,
    alpha_gate,
    dashboard_payload,
    dashboard_html,
    recent_rows,
)

try:
    from modules.v29_governance_core import require_api_key
except Exception:  # pragma: no cover
    require_api_key = None


def require_v29_api_key():
    if require_api_key is None:
        return None
    ok, reason = require_api_key(request.headers, request.args)
    if not ok:
        return jsonify({"ok": False, "error": reason, "hint": "Send X-API-Key or Authorization: Bearer token"}), 401
    return None


def register_v31_alpha_attribution_routes(app):
    @app.route('/v31/health')
    def v31_health():
        return jsonify(init_v31_db())

    @app.route('/v31/sync-v28', methods=['POST', 'GET'])
    def v31_sync_v28():
        block = require_v29_api_key()
        if block:
            return block
        limit = int(request.args.get('limit') or (request.get_json(silent=True) or {}).get('limit') or 500)
        return jsonify(sync_from_v28_outcomes(limit))

    @app.route('/v31/components/record', methods=['POST'])
    def v31_record_components():
        block = require_v29_api_key()
        if block:
            return block
        payload = request.get_json(silent=True) or {}
        return jsonify(record_signal_components(
            symbol=payload.get('symbol'),
            side=payload.get('side'),
            components=payload.get('components') or {},
            return_r=payload.get('return_r'),
            outcome=payload.get('outcome'),
            regime=payload.get('regime'),
            strategy_key=payload.get('strategy_key'),
            source_signal_id=payload.get('source_signal_id'),
            metadata=payload,
        ))

    @app.route('/v31/attribution', methods=['POST', 'GET'])
    def v31_attribution():
        block = require_v29_api_key()
        if block:
            return block
        payload = request.get_json(silent=True) or {}
        lookback = int(payload.get('lookback') or request.args.get('lookback') or 500)
        min_obs = int(payload.get('min_observations') or request.args.get('min_observations') or 10)
        return jsonify(component_attribution(lookback, min_obs))

    @app.route('/v31/weights', methods=['POST', 'GET'])
    def v31_weights():
        block = require_v29_api_key()
        if block:
            return block
        payload = request.get_json(silent=True) or {}
        lookback = int(payload.get('lookback') or request.args.get('lookback') or 500)
        min_obs = int(payload.get('min_observations') or request.args.get('min_observations') or 10)
        return jsonify(recommend_weights(lookback, min_obs))

    @app.route('/v31/monte-carlo', methods=['POST', 'GET'])
    def v31_monte_carlo():
        block = require_v29_api_key()
        if block:
            return block
        payload = request.get_json(silent=True) or {}
        returns = payload.get('returns')
        simulations = int(payload.get('simulations') or request.args.get('simulations') or 5000)
        trades = int(payload.get('trades_per_run') or request.args.get('trades_per_run') or 100)
        ruin = float(payload.get('ruin_dd_r') or request.args.get('ruin_dd_r') or -10.0)
        return jsonify(monte_carlo_risk(returns, simulations, trades, ruin))

    @app.route('/v31/regime-attribution')
    def v31_regime():
        block = require_v29_api_key()
        if block:
            return block
        lookback = int(request.args.get('lookback') or 500)
        return jsonify(regime_attribution(lookback))

    @app.route('/v31/optimizer', methods=['POST'])
    def v31_optimizer():
        block = require_v29_api_key()
        if block:
            return block
        payload = request.get_json(silent=True) or {}
        return jsonify(optimize_portfolio_candidates(
            payload.get('candidates') or [],
            int(payload.get('max_selected') or 5),
            int(payload.get('max_same_group') or 2),
        ))

    @app.route('/v31/alpha-gate', methods=['POST', 'GET'])
    def v31_alpha_gate():
        payload = request.get_json(silent=True) or {}
        if not payload:
            payload = dict(request.args)
        send, detail = alpha_gate(payload)
        return jsonify({'ok': True, 'send': send, 'detail': detail})

    @app.route('/v31/table/<table>')
    def v31_table(table):
        block = require_v29_api_key()
        if block:
            return block
        return jsonify({'ok': True, 'version': V31_VERSION, 'rows': recent_rows(table, int(request.args.get('limit') or 100))})

    @app.route('/v31/dashboard.json')
    def v31_dashboard_json():
        block = require_v29_api_key()
        if block:
            return block
        return jsonify(dashboard_payload())

    @app.route('/v31/dashboard')
    @app.route('/v31/alpha-dashboard')
    def v31_dashboard():
        block = require_v29_api_key()
        if block:
            return block
        return Response(dashboard_html(), mimetype='text/html')
