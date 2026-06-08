from __future__ import annotations

from flask import jsonify, request, Response

from modules.v39_validation_paper_broker_proof_core import (
    V39_VERSION, load_config, save_config, paper_broker_connection_check,
    paper_order_proof, record_forward_day, forward_validation_dashboard,
    edge_proof_report, trade_freeze_mode, auto_daily_report, v39_full_validation_report
)


def _symbols():
    raw = request.args.get('symbols', 'NVDA,AAPL,TSLA,QQQ,SPY')
    return [s.strip().upper() for s in raw.split(',') if s.strip()]


def register_v39_validation_paper_broker_proof_routes(app):
    @app.get('/v39/report')
    def v39_report():
        return jsonify(v39_full_validation_report(_symbols()))

    @app.get('/v39/config')
    def v39_config():
        return jsonify(load_config())

    @app.post('/v39/config')
    def v39_config_update():
        return jsonify(save_config(request.get_json(silent=True) or {}))

    @app.get('/v39/paper-broker/check')
    def v39_paper_broker_check():
        return jsonify(paper_broker_connection_check(request.args.get('broker')))

    @app.post('/v39/paper-broker/order-proof')
    def v39_paper_order_proof():
        data = request.get_json(silent=True) or {}
        return jsonify(paper_order_proof(
            symbol=data.get('symbol', request.args.get('symbol', 'SPY')),
            side=data.get('side', request.args.get('side', 'BUY')),
            qty=float(data.get('qty', request.args.get('qty', 1))),
            price=float(data.get('price', request.args.get('price', 100))),
            broker_name=data.get('broker', request.args.get('broker')),
            dry_run=bool(data.get('dry_run', False)),
        ))

    @app.post('/v39/forward/record-day')
    def v39_forward_record_day():
        data = request.get_json(silent=True) or {}
        return jsonify(record_forward_day(float(data.get('day_return_pct', 0)), int(data.get('trades', 0)), str(data.get('notes', ''))))

    @app.get('/v39/forward/dashboard')
    def v39_forward_dashboard():
        return jsonify(forward_validation_dashboard())

    @app.get('/v39/edge-proof')
    def v39_edge_proof():
        return jsonify(edge_proof_report(_symbols(), request.args.getlist('benchmark') or None, request.args.get('period','1y'), request.args.get('interval','1d')))

    @app.get('/v39/trade-freeze')
    def v39_trade_freeze():
        return jsonify(trade_freeze_mode({'daily_pnl_pct': float(request.args.get('daily_pnl_pct', 0)), 'consecutive_losses': int(request.args.get('consecutive_losses', 0))}))

    @app.get('/v39/daily-report')
    def v39_daily_report():
        return jsonify(auto_daily_report(_symbols()))

    @app.get('/v39/dashboard')
    def v39_dashboard():
        r = v39_full_validation_report(_symbols())
        html = f"""
        <html><head><title>{V39_VERSION}</title><style>body{{font-family:Arial;margin:24px}}.card{{border:1px solid #ddd;border-radius:12px;padding:16px;margin:12px 0}}code{{background:#f4f4f4;padding:2px 6px;border-radius:4px}}</style></head>
        <body><h1>V39 Validation & Paper Broker Proof</h1>
        <div class='card'><b>Paper Broker:</b> {r['paper_broker'].get('broker')} / OK={r['paper_broker'].get('ok')}</div>
        <div class='card'><b>Edge Decision:</b> {r['edge_proof'].get('decision')} / Proven={r['edge_proof'].get('edge_proven')}</div>
        <div class='card'><b>Freeze:</b> {r['trade_freeze'].get('decision')} / Reasons={r['trade_freeze'].get('reasons')}</div>
        <div class='card'><b>Forward Days:</b> {r['edge_proof']['forward_validation'].get('total_recorded_days')}</div>
        <p>API: <code>/v39/report</code> <code>/v39/forward/dashboard</code> <code>/v39/paper-broker/check</code> <code>/v39/edge-proof</code></p>
        </body></html>
        """
        return Response(html, mimetype='text/html')
