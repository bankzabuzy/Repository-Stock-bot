from __future__ import annotations

import html
from flask import jsonify, request, Response

from modules.v36_institutional_free_core import (
    V36_VERSION, v36_institutional_report, execution_simulator, portfolio_heat,
    factor_exposure, dynamic_stop_engine, strategy_rotation, meta_ai_filter,
    alpha_decay_detector, portfolio_attribution, capital_allocation_engine,
    self_healing_monitor, institutional_readiness_score
)
from modules.v35_institutional_free_core import fetch_ohlcv, backtest_many, walk_forward_many, monte_carlo_many

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


def register_v36_institutional_free_routes(app):
    @app.route('/v36/health')
    def v36_health():
        return jsonify({'ok': True, 'version': V36_VERSION, 'mode': 'free_100_percent_institutional_research'})

    @app.route('/v36/report')
    def v36_report():
        return jsonify(v36_institutional_report(_symbols(), request.args.get('period','1y'), request.args.get('interval','1d'), float(request.args.get('account_equity',100000))))

    @app.route('/v36/execution-simulator', methods=['POST'])
    def v36_exec():
        block=_require_key()
        if block: return block
        payload=request.get_json(silent=True) or {}
        symbol=str(payload.get('symbol','')).upper()
        df=fetch_ohlcv(symbol,'6mo','1d') if symbol else None
        return jsonify(execution_simulator(payload, df))

    @app.route('/v36/portfolio-heat', methods=['POST'])
    def v36_heat():
        block=_require_key()
        if block: return block
        payload=request.get_json(silent=True) or {}
        return jsonify(portfolio_heat(payload.get('positions',[]), float(payload.get('account_equity',100000))))

    @app.route('/v36/factor-exposure', methods=['POST'])
    def v36_factor():
        block=_require_key()
        if block: return block
        payload=request.get_json(silent=True) or {}
        return jsonify(factor_exposure(payload.get('positions',[]), float(payload.get('account_equity',100000))))

    @app.route('/v36/dynamic-stop')
    def v36_stop():
        symbol=request.args.get('symbol','SPY').upper()
        return jsonify(dynamic_stop_engine(symbol, entry_price=request.args.get('entry_price')))

    @app.route('/v36/strategy-rotation')
    def v36_rotation():
        return jsonify(strategy_rotation(_symbols(), request.args.get('period','2y'), request.args.get('interval','1d')))

    @app.route('/v36/meta-ai-filter', methods=['POST'])
    def v36_meta():
        block=_require_key()
        if block: return block
        payload=request.get_json(silent=True) or {}
        return jsonify(meta_ai_filter(payload.get('signal',payload), payload.get('backtest'), payload.get('walk_forward'), payload.get('monte_carlo')))

    @app.route('/v36/alpha-decay')
    def v36_decay():
        bt=backtest_many(_symbols(), request.args.get('period','2y'), request.args.get('interval','1d'))
        return jsonify(alpha_decay_detector(bt.get('rows',[])))

    @app.route('/v36/portfolio-attribution', methods=['POST'])
    def v36_attr():
        block=_require_key()
        if block: return block
        payload=request.get_json(silent=True) or {}
        return jsonify(portfolio_attribution(payload.get('trades',[])))

    @app.route('/v36/capital-allocation')
    def v36_alloc():
        return jsonify(capital_allocation_engine(_symbols(), float(request.args.get('account_equity',100000)), float(request.args.get('cash_floor_pct',20)), request.args.get('period','1y'), request.args.get('interval','1d')))

    @app.route('/v36/self-healing')
    def v36_healing():
        return jsonify(self_healing_monitor(_symbols(), request.args.get('period','6mo'), request.args.get('interval','1d')))

    @app.route('/v36/readiness')
    def v36_ready():
        symbols=_symbols(); interval=request.args.get('interval','1d')
        bt=backtest_many(symbols,'2y',interval); wf=walk_forward_many(symbols,'5y',interval); mc=monte_carlo_many(symbols,'2y',interval,1000)
        return jsonify(institutional_readiness_score(bt,wf,mc))

    @app.route('/v36/dashboard')
    def v36_dashboard():
        rep=v36_institutional_report(_symbols(), request.args.get('period','1y'), request.args.get('interval','1d'), float(request.args.get('account_equity',100000)))
        def esc(x): return html.escape('' if x is None else str(x))
        rank_rows=''.join(f"<tr><td>{r.get('rank')}</td><td>{esc(r.get('symbol'))}</td><td>{esc(r.get('price'))}</td><td>{esc(r.get('score'))}</td><td>{esc(r.get('signal'))}</td><td>{esc(r.get('action'))}</td><td>{esc(r.get('meta_ai_filter',{}).get('decision'))}</td><td>{esc(r.get('dynamic_stop',{}).get('recommended_stop'))}</td><td>{esc(r.get('institutional_gate',{}).get('decision'))}</td></tr>" for r in rep.get('ranking',{}).get('rows',[]))
        alloc_rows=''.join(f"<tr><td>{esc(r.get('symbol'))}</td><td>{esc(r.get('weight_pct'))}%</td><td>{esc(r.get('notional'))}</td></tr>" for r in rep.get('capital_allocation',{}).get('rows',[]))
        return Response(f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>V36 Institutional Free</title><style>body{{font-family:Arial,sans-serif;background:#f6f7f8;padding:18px}}.card{{background:#fff;border:1px solid #ddd;padding:12px;margin:12px 0}}table{{border-collapse:collapse;width:100%;background:#fff}}th,td{{border:1px solid #ddd;padding:7px;font-size:13px}}th{{background:#111;color:#fff}}.warn{{background:#fff4d6;border:1px solid #e0bd5b;padding:10px}}</style></head><body><h1>V36 Institutional Free Dashboard</h1><div class='warn'>Research/Paper Trading only. ฟรี 100% แต่ยังต้อง Forward Test 30-90 วันก่อนเงินจริง</div><div class='card'><b>Readiness:</b> {esc(rep.get('readiness',{}).get('readiness_score_pct'))}% | <b>Decision:</b> {esc(rep.get('readiness',{}).get('decision'))} | <b>Strategy:</b> {esc(rep.get('strategy_rotation',{}).get('active_strategy'))} | <b>Self-Healing:</b> {esc(rep.get('self_healing',{}).get('status'))}</div><h2>Signal + Meta AI + Dynamic Stop</h2><table><thead><tr><th>Rank</th><th>Symbol</th><th>Price</th><th>Score</th><th>Signal</th><th>Action</th><th>Meta AI</th><th>Dynamic Stop</th><th>Gate</th></tr></thead><tbody>{rank_rows}</tbody></table><h2>Capital Allocation</h2><table><thead><tr><th>Symbol</th><th>Weight</th><th>Notional</th></tr></thead><tbody>{alloc_rows}</tbody></table><div class='card'>Portfolio Heat: {esc(rep.get('portfolio_heat',{}).get('decision'))} | Total Risk: {esc(rep.get('portfolio_heat',{}).get('total_risk_pct'))}% | API: /v36/report, /v36/readiness, /v36/capital-allocation, /v36/self-healing</div></body></html>""", mimetype='text/html')
