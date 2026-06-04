from flask import jsonify, request, Response

from modules.v29_governance_core import require_api_key
from modules.v30_model_validation_core import (
    V30_VERSION,
    init_v30_db,
    run_model_validation,
    paper_apply_signal,
    mark_to_market,
    deployment_check,
    data_reconciliation,
    validation_gate,
    dashboard_payload,
    dashboard_html,
    recent_rows,
)


def _protected():
    ok, reason = require_api_key(request.headers, request.args)
    if not ok:
        return jsonify({"ok": False, "error": reason, "hint": "Send X-API-Key or Authorization: Bearer token"}), 401
    return None


def register_v30_model_validation_routes(app):
    init_v30_db()

    @app.route('/v30/health')
    def v30_health():
        return jsonify(init_v30_db())

    @app.route('/v30/deployment-check')
    def v30_deployment_check():
        return jsonify(deployment_check())

    @app.route('/v30/validate', methods=['GET', 'POST'])
    def v30_validate():
        payload = request.get_json(silent=True) or {}
        symbol = payload.get('symbol') or request.args.get('symbol') or 'SPY'
        period = payload.get('period') or request.args.get('period') or '3y'
        interval = payload.get('interval') or request.args.get('interval') or '1d'
        train = int(payload.get('train_bars') or request.args.get('train_bars') or 180)
        test = int(payload.get('test_bars') or request.args.get('test_bars') or 45)
        fast = int(payload.get('fast') or request.args.get('fast') or 10)
        slow = int(payload.get('slow') or request.args.get('slow') or 30)
        return jsonify(run_model_validation(symbol, period, interval, train, test, fast, slow))

    @app.route('/v30/paper/signal', methods=['POST', 'GET'])
    def v30_paper_signal():
        payload = request.get_json(silent=True) or {}
        symbol = payload.get('symbol') or request.args.get('symbol')
        side = payload.get('side') or request.args.get('side') or 'HOLD'
        price = payload.get('price') or request.args.get('price')
        account = payload.get('account_name') or request.args.get('account_name') or 'GLOBAL'
        return jsonify(paper_apply_signal(symbol, side, price, account, payload.get('confidence'), payload))

    @app.route('/v30/paper/mark-to-market', methods=['POST', 'GET'])
    def v30_mark_to_market():
        payload = request.get_json(silent=True) or {}
        account = payload.get('account_name') or request.args.get('account_name') or 'GLOBAL'
        return jsonify(mark_to_market(account, payload.get('price_map') or {}))

    @app.route('/v30/reconcile', methods=['POST', 'GET'])
    def v30_reconcile():
        payload = request.get_json(silent=True) or {}
        symbol = payload.get('symbol') or request.args.get('symbol') or 'SPY'
        sources = payload.get('sources') or {}
        return jsonify(data_reconciliation(symbol, sources))

    @app.route('/v30/validation-gate', methods=['POST', 'GET'])
    def v30_gate():
        payload = request.get_json(silent=True) or {}
        symbol = payload.get('symbol') or request.args.get('symbol') or 'SPY'
        sig = payload.get('sig') or request.args.get('sig') or 'BUY'
        ok, detail = validation_gate(symbol, sig, payload.get('analysis') or {})
        return jsonify({'ok': True, 'send': ok, 'detail': detail})

    @app.route('/v30/table/<table>')
    def v30_table(table):
        return jsonify({'ok': True, 'version': V30_VERSION, 'rows': recent_rows(table, int(request.args.get('limit') or 100))})

    @app.route('/v30/dashboard.json')
    def v30_dashboard_json():
        return jsonify(dashboard_payload())

    @app.route('/v30/dashboard')
    @app.route('/v30/institutional-validation')
    def v30_dashboard():
        return Response(dashboard_html(), mimetype='text/html')
