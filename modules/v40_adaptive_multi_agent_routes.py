from __future__ import annotations

from flask import jsonify, request, Response

from modules.v40_adaptive_multi_agent_core import (
    V40_VERSION, adaptive_agent_ensemble, chief_risk_officer_ai, pyramid_tp_engine,
    news_context_layer, record_trade_memory, trade_memory_engine, v40_pre_trade_pipeline,
    v40_full_report
)


def _symbols():
    raw = request.args.get('symbols', 'NVDA,AAPL,TSLA,QQQ,SPY')
    return [s.strip().upper() for s in raw.split(',') if s.strip()]


def _ctx():
    data = request.get_json(silent=True) or {}
    ctx = dict(data.get('context', data)) if isinstance(data, dict) else {}
    for k in ['trades_today', 'risk_per_trade_pct', 'daily_pnl_pct', 'intended_notional', 'fear_greed']:
        if k in request.args:
            val = request.args.get(k)
            try:
                ctx[k] = float(val) if '.' in str(val) else int(val)
            except Exception:
                ctx[k] = val
    if request.args.get('events'):
        ctx['events'] = [x.strip() for x in request.args.get('events','').split(',') if x.strip()]
    if request.args.get('market_regime'):
        ctx['market_regime'] = request.args.get('market_regime')
    return ctx


def register_v40_adaptive_multi_agent_routes(app):
    @app.get('/v40/report')
    def v40_report():
        return jsonify(v40_full_report(_symbols(), _ctx()))

    @app.get('/v40/pre-trade')
    def v40_pre_trade():
        return jsonify(v40_pre_trade_pipeline(request.args.get('symbol','NVDA'), _ctx()))

    @app.get('/v40/agents')
    def v40_agents():
        return jsonify(adaptive_agent_ensemble(request.args.get('symbol','NVDA'), _ctx()))

    @app.get('/v40/news-context')
    def v40_news():
        return jsonify(news_context_layer(request.args.get('symbol','NVDA'), _ctx()))

    @app.get('/v40/pyramid-tp')
    def v40_pyramid():
        return jsonify(pyramid_tp_engine(float(request.args.get('entry_price', 100)), request.args.get('side','BUY'), atr=float(request.args.get('atr', 1))))

    @app.get('/v40/trade-memory')
    def v40_memory():
        return jsonify(trade_memory_engine(request.args.get('symbol'), request.args.get('setup')))

    @app.post('/v40/trade-memory')
    def v40_memory_record():
        data = request.get_json(silent=True) or {}
        return jsonify(record_trade_memory(data.get('symbol','SPY'), data.get('setup','unknown'), float(data.get('result_pct',0)), int(data.get('holding_minutes',0)), data.get('notes','')))

    @app.get('/v40/dashboard')
    def v40_dashboard():
        r = v40_full_report(_symbols(), _ctx())
        cards = ''.join([f"<tr><td>{x['symbol']}</td><td>{x['final_decision']}</td><td>{x['ensemble']['signal']}</td><td>{x['ensemble']['confidence_pct']}</td><td>{x['chief_risk_officer']['action']}</td></tr>" for x in r['rows']])
        html = f"""
        <html><head><title>{V40_VERSION}</title><style>body{{font-family:Arial;margin:24px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:8px}}th{{background:#111;color:white}}.card{{border:1px solid #ddd;border-radius:12px;padding:16px;margin:12px 0}}</style></head>
        <body><h1>V40 Adaptive Multi-Agent Institutional</h1>
        <div class='card'>Summary: {r['summary']}</div>
        <table><tr><th>Symbol</th><th>Final</th><th>Signal</th><th>Confidence</th><th>CRO</th></tr>{cards}</table>
        <p>API: /v40/report /v40/pre-trade /v40/agents /v40/pyramid-tp /v40/trade-memory</p>
        </body></html>
        """
        return Response(html, mimetype='text/html')
