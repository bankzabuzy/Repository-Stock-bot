from flask import jsonify, request, Response
from modules.v28_fund_validation_core import (
    V28_VERSION, init_v28_db, audit_signal, evaluate_portfolio_risk,
    run_outcome_scheduler, run_walk_forward, recent, dashboard_payload, dashboard_html,
    portfolio_gate
)


def register_v28_fund_validation_routes(app):
    init_v28_db()

    @app.route('/v28/health')
    def v28_health():
        init_v28_db()
        return jsonify({'ok': True, 'version': V28_VERSION})

    @app.route('/v28/audit', methods=['GET', 'POST'])
    def v28_audit():
        if request.method == 'POST':
            payload = request.get_json(silent=True) or {}
            return jsonify(audit_signal(
                payload.get('symbol', 'SPY'),
                payload.get('asset_type', 'US_STOCK'),
                payload.get('sig', payload.get('side', 'BUY')),
                payload.get('analysis', payload),
                payload.get('decision', 'PASS'),
                payload.get('reason', 'manual audit'),
                payload.get('portfolio_gate'),
                payload.get('market_open'),
                payload.get('message')
            ))
        return jsonify({'ok': True, 'version': V28_VERSION, 'rows': recent('v28_signal_audit', request.args.get('limit') or 50)})

    @app.route('/v28/open-signals')
    def v28_open_signals():
        return jsonify({'ok': True, 'version': V28_VERSION, 'rows': recent('v28_open_signals', request.args.get('limit') or 100)})

    @app.route('/v28/outcomes')
    def v28_outcomes():
        return jsonify({'ok': True, 'version': V28_VERSION, 'rows': recent('v28_signal_outcomes', request.args.get('limit') or 100)})

    @app.route('/v28/outcome/run', methods=['GET', 'POST'])
    def v28_outcome_run():
        return jsonify(run_outcome_scheduler(request.args.get('limit') or 100))

    @app.route('/v28/risk', methods=['GET', 'POST'])
    def v28_risk():
        payload = request.get_json(silent=True) or {}
        candidate = payload.get('candidate') or {'symbol': request.args.get('symbol', ''), 'risk_r': request.args.get('risk_r', 1)}
        if not candidate.get('symbol'):
            candidate = None
        return jsonify(evaluate_portfolio_risk(candidate, save=True))

    @app.route('/v28/portfolio-gate', methods=['GET', 'POST'])
    def v28_portfolio_gate_route():
        payload = request.get_json(silent=True) or {}
        symbol = payload.get('symbol') or request.args.get('symbol') or 'SPY'
        analysis = payload.get('analysis') or {'price': request.args.get('price')}
        sig = payload.get('sig') or request.args.get('sig') or 'BUY'
        ok, detail = portfolio_gate(symbol, analysis, sig)
        return jsonify({'ok': True, 'send': ok, 'detail': detail})

    @app.route('/v28/walk-forward', methods=['GET', 'POST'])
    def v28_walk_forward():
        payload = request.get_json(silent=True) or {}
        symbol = payload.get('symbol') or request.args.get('symbol') or 'SPY'
        period = payload.get('period') or request.args.get('period') or '2y'
        interval = payload.get('interval') or request.args.get('interval') or '1d'
        train_bars = int(payload.get('train_bars') or request.args.get('train_bars') or 120)
        test_bars = int(payload.get('test_bars') or request.args.get('test_bars') or 30)
        fast = int(payload.get('fast') or request.args.get('fast') or 10)
        slow = int(payload.get('slow') or request.args.get('slow') or 30)
        return jsonify(run_walk_forward(symbol, period, interval, train_bars, test_bars, fast, slow))

    @app.route('/v28/walk-forward-runs')
    def v28_walk_forward_runs():
        return jsonify({'ok': True, 'version': V28_VERSION, 'rows': recent('v28_walk_forward_runs', request.args.get('limit') or 50)})

    @app.route('/v28/fund-dashboard.json')
    def v28_dashboard_json():
        return jsonify(dashboard_payload())

    @app.route('/v28/fund-dashboard')
    @app.route('/v28/dashboard')
    def v28_dashboard():
        return Response(dashboard_html(), mimetype='text/html')
