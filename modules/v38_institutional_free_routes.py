from __future__ import annotations

import html
from flask import jsonify, request, Response

from modules.v38_institutional_free_core import (
    V38_VERSION, explainable_ai_engine, multi_source_data_validation, exposure_manager,
    beta_control, liquidity_filter, confidence_score, scenario_stress_test,
    benchmark_comparison, ai_health_score, governance_layer, v38_pre_trade_pipeline,
    v38_institutional_report
)


def _symbols():
    raw = request.args.get('symbols', 'NVDA,AAPL,TSLA,QQQ,SPY')
    return [s.strip().upper() for s in raw.split(',') if s.strip()]


def _positions(account_equity=100000.0):
    syms = _symbols()
    n = max(1, len(syms))
    return [{'symbol': s, 'qty': 1, 'price': 100, 'notional': account_equity/n*0.5} for s in syms]


def register_v38_institutional_free_routes(app):
    @app.get('/v38/report')
    def v38_report():
        eq = float(request.args.get('equity', 100000))
        return jsonify(v38_institutional_report(_symbols(), _positions(eq), eq, request.args.get('period','1y'), request.args.get('interval','1d')))

    @app.get('/v38/explain')
    def v38_explain():
        symbol = request.args.get('symbol', 'NVDA').upper()
        sig = {'symbol': symbol, 'signal': request.args.get('signal','BUY'), 'score': float(request.args.get('score', 75)), 'price': float(request.args.get('price', 100))}
        return jsonify(explainable_ai_engine(sig))

    @app.get('/v38/data-validation')
    def v38_data_validation():
        return jsonify(multi_source_data_validation(request.args.get('symbol','NVDA'), request.args.get('period','1y'), request.args.get('interval','1d')))

    @app.get('/v38/exposure')
    def v38_exposure():
        eq = float(request.args.get('equity', 100000))
        return jsonify(exposure_manager(_positions(eq), eq))

    @app.get('/v38/beta')
    def v38_beta():
        eq = float(request.args.get('equity', 100000))
        return jsonify(beta_control(_positions(eq), request.args.get('benchmark','SPY'), eq))

    @app.get('/v38/liquidity')
    def v38_liquidity():
        return jsonify(liquidity_filter(request.args.get('symbol','NVDA'), intended_notional=float(request.args.get('notional',0))))

    @app.get('/v38/confidence')
    def v38_confidence():
        symbol = request.args.get('symbol','NVDA').upper()
        sig = {'symbol': symbol, 'signal': request.args.get('signal','BUY'), 'score': float(request.args.get('score', 75)), 'price': float(request.args.get('price', 100))}
        return jsonify(confidence_score(sig))

    @app.get('/v38/stress')
    def v38_stress():
        eq = float(request.args.get('equity', 100000))
        return jsonify(scenario_stress_test(_positions(eq), eq))

    @app.get('/v38/benchmark')
    def v38_benchmark():
        return jsonify(benchmark_comparison(_symbols(), ['SPY','QQQ'], request.args.get('period','1y'), request.args.get('interval','1d')))

    @app.get('/v38/ai-health')
    def v38_ai_health():
        metrics = {'sharpe': float(request.args.get('sharpe', 1.5)), 'profit_factor': float(request.args.get('profit_factor', 1.5)), 'win_rate_pct': float(request.args.get('win_rate_pct', 55)), 'max_drawdown_pct': float(request.args.get('max_drawdown_pct', -10))}
        return jsonify(ai_health_score(metrics))

    @app.get('/v38/governance')
    def v38_governance():
        ctx = {'trades_today': float(request.args.get('trades_today',0)), 'risk_per_trade_pct': float(request.args.get('risk_pct',1)), 'daily_pnl_pct': float(request.args.get('daily_pnl_pct',0))}
        return jsonify(governance_layer(ctx))

    @app.post('/v38/pre-trade')
    def v38_pre_trade():
        body = request.get_json(silent=True) or {}
        return jsonify(v38_pre_trade_pipeline(body.get('symbol','NVDA'), float(body.get('account_equity',100000)), body.get('positions') or [], body.get('context') or {}, bool(body.get('dry_run', True))))

    @app.get('/v38/dashboard')
    def v38_dashboard():
        eq = float(request.args.get('equity', 100000))
        rep = v38_institutional_report(_symbols(), _positions(eq), eq)
        esc = lambda x: html.escape(str(x))
        xai_rows = ''.join(f"<tr><td>{esc(r.get('symbol'))}</td><td>{esc(r.get('signal'))}</td><td>{esc(r.get('confidence'))}%</td><td>{esc(r.get('explain'))}</td></tr>" for r in rep.get('explainable_ai', []))
        exp_rows = ''.join(f"<tr><td>{esc(r.get('type'))}</td><td>{esc(r.get('name'))}</td><td>{esc(r.get('exposure_pct'))}%</td><td>{esc(r.get('limit_pct'))}%</td></tr>" for r in rep.get('exposure_manager', {}).get('rows', []))
        stress_rows = ''.join(f"<tr><td>{esc(r.get('scenario'))}</td><td>{esc(r.get('pnl_pct'))}%</td><td>{esc(r.get('pnl'))}</td></tr>" for r in rep.get('scenario_stress', {}).get('rows', []))
        return Response(f"""<html><head><title>{V38_VERSION}</title><style>body{{font-family:Arial,sans-serif;background:#f6f7f8;padding:18px}}.card{{background:white;border:1px solid #ddd;padding:12px;margin:12px 0}}table{{border-collapse:collapse;width:100%;background:#fff}}th,td{{border:1px solid #ddd;padding:7px;font-size:13px}}th{{background:#111;color:#fff}}.warn{{background:#fff4d6;border:1px solid #e0bd5b;padding:10px}}</style></head><body><h1>V38 Institutional Free Plus</h1><div class='warn'>Free 100% / Research & Paper Trading first. Do not use real money without broker paper forward testing.</div><div class='card'><b>Institutional Score:</b> {esc(rep.get('institutional_score_pct'))}% | <b>Decision:</b> {esc(rep.get('decision'))} | <b>AI Health:</b> {esc(rep.get('ai_health',{}).get('status'))}</div><h2>Explainable AI + Confidence</h2><table><tr><th>Symbol</th><th>Signal</th><th>Confidence</th><th>Explain</th></tr>{xai_rows}</table><h2>Exposure Manager</h2><table><tr><th>Type</th><th>Name</th><th>Exposure</th><th>Limit</th></tr>{exp_rows}</table><h2>Scenario Stress Test</h2><table><tr><th>Scenario</th><th>PnL %</th><th>PnL</th></tr>{stress_rows}</table><div class='card'>API: /v38/report, /v38/explain, /v38/data-validation, /v38/exposure, /v38/beta, /v38/liquidity, /v38/confidence, /v38/stress, /v38/benchmark, /v38/ai-health, /v38/governance, /v38/pre-trade</div></body></html>""", mimetype='text/html')
