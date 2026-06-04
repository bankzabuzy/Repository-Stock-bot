from flask import jsonify, request, Response
from modules.v29_governance_core import (
    V29_VERSION, init_v29_db, require_api_key, migrate_v28_to_postgres,
    provider_health, feedback_loop, governance_gate, scheduler_run_once,
    start_scheduler_once, set_state, get_state, dashboard_payload, dashboard_html,
    recent_rows, V29_ENABLE_CRON
)


def _protected():
    ok, reason = require_api_key(request.headers, request.args)
    if not ok:
        return jsonify({"ok": False, "error": reason, "hint": "Send X-API-Key or Authorization: Bearer token"}), 401
    return None


def register_v29_governance_routes(app):
    init_v29_db()

    @app.route('/v29/health')
    def v29_health():
        return jsonify(init_v29_db())

    @app.route('/v29/migrate', methods=['POST', 'GET'])
    def v29_migrate():
        block = _protected()
        if block:
            return block
        limit = int(request.args.get('limit') or (request.get_json(silent=True) or {}).get('limit') or 10000)
        return jsonify(migrate_v28_to_postgres(limit))

    @app.route('/v29/provider-health')
    def v29_provider_health():
        force = str(request.args.get('force', 'false')).lower() == 'true'
        return jsonify(provider_health(force=force))

    @app.route('/v29/feedback', methods=['GET', 'POST'])
    def v29_feedback():
        block = _protected()
        if block:
            return block
        payload = request.get_json(silent=True) or {}
        return jsonify(feedback_loop(payload.get('strategy_key') or request.args.get('strategy_key') or 'GLOBAL'))

    @app.route('/v29/governance-gate', methods=['GET', 'POST'])
    def v29_gate_route():
        payload = request.get_json(silent=True) or {}
        symbol = payload.get('symbol') or request.args.get('symbol') or 'SPY'
        sig = payload.get('sig') or request.args.get('sig') or 'BUY'
        analysis = payload.get('analysis') or {'score': request.args.get('score')}
        ok, detail = governance_gate(symbol, sig, analysis)
        return jsonify({'ok': True, 'send': ok, 'detail': detail})

    @app.route('/v29/scheduler/run', methods=['POST', 'GET'])
    def v29_scheduler_run():
        block = _protected()
        if block:
            return block
        return jsonify(scheduler_run_once())

    @app.route('/v29/scheduler/start', methods=['POST', 'GET'])
    def v29_scheduler_start():
        block = _protected()
        if block:
            return block
        return jsonify(start_scheduler_once())

    @app.route('/v29/state', methods=['GET', 'POST'])
    def v29_state():
        if request.method == 'POST':
            block = _protected()
            if block:
                return block
            payload = request.get_json(silent=True) or {}
            key = payload.get('key') or request.args.get('key')
            value = payload.get('value') or request.args.get('value')
            if not key or value is None:
                return jsonify({'ok': False, 'error': 'key and value required'}), 400
            return jsonify(set_state(key, str(value), updated_by='api', note=payload.get('note') or 'manual api update'))
        return jsonify({'ok': True, 'version': V29_VERSION, 'state': recent_rows('v29_system_state', 100)})

    @app.route('/v29/kill-switch/<mode>', methods=['POST', 'GET'])
    def v29_kill_switch(mode):
        block = _protected()
        if block:
            return block
        mode = 'on' if str(mode).lower() in {'on', '1', 'true'} else 'off'
        return jsonify(set_state('alert_kill_switch', mode, updated_by='api', note='manual kill switch'))

    @app.route('/v29/events')
    def v29_events():
        return jsonify({'ok': True, 'version': V29_VERSION, 'rows': recent_rows('v29_governance_events', int(request.args.get('limit') or 100))})

    @app.route('/v29/scheduler-runs')
    def v29_scheduler_runs():
        return jsonify({'ok': True, 'version': V29_VERSION, 'rows': recent_rows('v29_scheduler_runs', int(request.args.get('limit') or 100))})

    @app.route('/v29/dashboard.json')
    def v29_dashboard_json():
        return jsonify(dashboard_payload())

    @app.route('/v29/dashboard')
    @app.route('/v29/fund-governance')
    def v29_dashboard():
        return Response(dashboard_html(), mimetype='text/html')

    if V29_ENABLE_CRON:
        try:
            start_scheduler_once()
        except Exception as e:
            print('V29 scheduler autostart warning:', e)
