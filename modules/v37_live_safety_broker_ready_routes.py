from __future__ import annotations

import html
from flask import jsonify, request, Response

from modules.v37_live_safety_broker_ready_core import (
    V37_VERSION, get_broker, oms_submit_order, oms_cancel_order, oms_order_history,
    kill_switch_status, set_kill_switch, capital_protection_mode, news_event_risk_filter,
    live_slippage_monitor, model_drift_detector, audit_log, health_check_dashboard,
    recovery_manager, live_readiness_score, v37_pre_trade_pipeline, v37_live_safety_report
)

try:
    from modules.v29_governance_core import require_api_key
except Exception:
    require_api_key = None


def _symbols():
    raw = request.args.get('symbols') or request.args.get('watchlist') or 'META,AMD,SPY,QQQ,TSLA,AAPL,NVDA,GC=F'
    return [x.strip().upper() for x in raw.split(',') if x.strip()]


def _require_key():
    if require_api_key is None:
        return None
    ok, reason = require_api_key(request.headers, request.args)
    if not ok:
        return jsonify({'ok': False, 'error': reason, 'hint': 'Send X-API-Key or Authorization: Bearer token'}), 401
    return None


def register_v37_live_safety_broker_ready_routes(app):
    @app.route('/v37/health')
    def v37_health():
        return jsonify({'ok': True, 'version': V37_VERSION, 'mode': 'live_safety_paper_broker_ready_free'})

    @app.route('/v37/report')
    def v37_report():
        return jsonify(v37_live_safety_report(_symbols(), float(request.args.get('account_equity', 100000)), request.args.get('period','1y'), request.args.get('interval','1d')))

    @app.route('/v37/readiness')
    def v37_readiness():
        return jsonify(live_readiness_score(_symbols(), request.args.get('period','1y'), request.args.get('interval','1d'), float(request.args.get('account_equity',100000))))

    @app.route('/v37/broker/account')
    def v37_broker_account():
        return jsonify(get_broker(request.args.get('broker')).account())

    @app.route('/v37/oms/submit', methods=['POST'])
    def v37_oms_submit():
        block = _require_key()
        if block: return block
        payload = request.get_json(silent=True) or {}
        dry = str(payload.get('dry_run', request.args.get('dry_run', 'true'))).lower() != 'false'
        return jsonify(oms_submit_order(payload, request.args.get('broker') or payload.get('broker'), dry))

    @app.route('/v37/oms/cancel', methods=['POST'])
    def v37_oms_cancel():
        block = _require_key()
        if block: return block
        payload = request.get_json(silent=True) or {}
        return jsonify(oms_cancel_order(payload.get('order_id') or request.args.get('order_id',''), request.args.get('broker') or payload.get('broker')))

    @app.route('/v37/oms/history')
    def v37_oms_history():
        return jsonify(oms_order_history(int(request.args.get('limit',100))))

    @app.route('/v37/kill-switch')
    def v37_kill_status():
        return jsonify(kill_switch_status(float(request.args.get('today_pnl_pct',0)), int(request.args.get('consecutive_losses',0))))

    @app.route('/v37/kill-switch/set', methods=['POST'])
    def v37_kill_set():
        block = _require_key()
        if block: return block
        payload = request.get_json(silent=True) or {}
        return jsonify(set_kill_switch(bool(payload.get('active')), payload.get('reason','manual')))

    @app.route('/v37/capital-protection', methods=['POST'])
    def v37_capital_protection():
        payload = request.get_json(silent=True) or {}
        return jsonify(capital_protection_mode(payload, float(request.args.get('base_risk_pct',0.5))))

    @app.route('/v37/event-risk')
    def v37_event_risk():
        return jsonify(news_event_risk_filter(request.args.get('symbol','SPY'), request.args.get('date')))

    @app.route('/v37/slippage')
    def v37_slippage():
        return jsonify(live_slippage_monitor(float(request.args.get('expected_price',0)), float(request.args.get('actual_price',0)), request.args.get('side','BUY'), float(request.args.get('max_slippage_bps',35))))

    @app.route('/v37/model-drift', methods=['POST'])
    def v37_drift():
        payload = request.get_json(silent=True) or {}
        return jsonify(model_drift_detector(payload.get('current', payload), payload.get('baseline')))

    @app.route('/v37/audit-log', methods=['POST'])
    def v37_audit():
        block = _require_key()
        if block: return block
        payload = request.get_json(silent=True) or {}
        return jsonify(audit_log(payload.get('event','manual_audit'), payload.get('payload', payload), payload.get('level','INFO')))

    @app.route('/v37/health-dashboard')
    def v37_health_dashboard_json():
        return jsonify(health_check_dashboard(_symbols(), request.args.get('period','6mo'), request.args.get('interval','1d')))

    @app.route('/v37/recovery', methods=['POST'])
    def v37_recovery():
        block = _require_key()
        if block: return block
        payload = request.get_json(silent=True) or {}
        return jsonify(recovery_manager(payload.get('symbols') or _symbols(), bool(payload.get('force_safe_mode', False))))

    @app.route('/v37/pre-trade')
    def v37_pre_trade():
        block = _require_key()
        if block: return block
        return jsonify(v37_pre_trade_pipeline(request.args.get('symbol','SPY'), float(request.args.get('account_equity',100000)), request.args.get('broker','mock'), request.args.get('dry_run','true').lower() != 'false'))

    @app.route('/v37/dashboard')
    def v37_dashboard():
        rep = v37_live_safety_report(_symbols(), float(request.args.get('account_equity',100000)), request.args.get('period','1y'), request.args.get('interval','1d'))
        def esc(x): return html.escape('' if x is None else str(x))
        events = ''.join(f"<tr><td>{esc(r.get('symbol'))}</td><td>{esc(r.get('decision'))}</td><td>{esc(', '.join(r.get('events') or []))}</td></tr>" for r in rep.get('event_risk',[]))
        orders = ''.join(f"<tr><td>{esc(r.get('status'))}</td><td>{esc((r.get('order') or r.get('submitted_order') or {}).get('symbol'))}</td><td>{esc((r.get('order') or r.get('submitted_order') or {}).get('qty'))}</td><td>{esc(r.get('created_at'))}</td></tr>" for r in rep.get('recent_orders',{}).get('rows',[])[:20])
        ready = rep.get('live_readiness',{})
        health = rep.get('health',{})
        return Response(f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>V37 Live Safety & Broker Ready</title><style>body{{font-family:Arial,sans-serif;background:#f6f7f8;padding:18px}}.card{{background:#fff;border:1px solid #ddd;padding:12px;margin:12px 0}}table{{border-collapse:collapse;width:100%;background:#fff}}th,td{{border:1px solid #ddd;padding:7px;font-size:13px}}th{{background:#111;color:#fff}}.warn{{background:#fff4d6;border:1px solid #e0bd5b;padding:10px}}.ok{{background:#e7ffe7;border:1px solid #79bb79;padding:10px}}</style></head><body><h1>V37 Live Safety & Broker Ready</h1><div class='warn'>Default = Dry-run / Mock broker. ห้ามใช้เงินจริงจนกว่า Paper Broker Forward Test 90 วันผ่านและตั้งค่า Risk/Compliance เองครบ</div><div class='card'><b>Live Safety Score:</b> {esc(ready.get('live_safety_score_pct'))}% | <b>Decision:</b> {esc(ready.get('decision'))} | <b>Health:</b> {esc(health.get('status'))}</div><h2>Event Risk Filter</h2><table><thead><tr><th>Symbol</th><th>Decision</th><th>Events</th></tr></thead><tbody>{events}</tbody></table><h2>Recent Orders</h2><table><thead><tr><th>Status</th><th>Symbol</th><th>Qty</th><th>Time</th></tr></thead><tbody>{orders}</tbody></table><div class='card'>API: /v37/report, /v37/readiness, /v37/pre-trade, /v37/oms/submit, /v37/kill-switch, /v37/health-dashboard</div></body></html>""", mimetype='text/html')
