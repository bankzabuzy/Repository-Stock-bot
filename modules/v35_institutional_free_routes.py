from __future__ import annotations
from flask import jsonify, request, Response
import html

from modules.v35_institutional_free_core import (
    V35_VERSION, rank_signals, backtest_many, forward_test_plan, risk_gate,
    walk_forward_many, portfolio_correlation_report, market_regime,
    portfolio_optimizer, position_sizing_engine, ensemble_signal, monte_carlo_many,
    trade_journal_ai, alpha_stack_report, fetch_ohlcv, latest_signal
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
        return jsonify({"ok": False, "error": reason, "hint": "Send X-API-Key or Authorization: Bearer token"}), 401
    return None


def register_v35_institutional_free_routes(app):
    @app.route('/v35/health')
    def v35_health():
        return jsonify({"ok": True, "version": V35_VERSION, "mode": "free_100_percent_research_paper_trading"})

    @app.route('/v35/ranking')
    def v35_ranking():
        return jsonify(rank_signals(_symbols(), request.args.get('period', '1y'), request.args.get('interval', '1d')))

    @app.route('/v35/backtest')
    def v35_backtest():
        return jsonify(backtest_many(_symbols(), request.args.get('period', '2y'), request.args.get('interval', '1d')))

    @app.route('/v35/forward-test')
    def v35_forward_test():
        return jsonify(forward_test_plan(_symbols()))

    @app.route('/v35/walk-forward')
    def v35_walk_forward():
        return jsonify(walk_forward_many(_symbols(), request.args.get('period', '5y'), request.args.get('interval', '1d')))

    @app.route('/v35/correlation')
    def v35_correlation():
        return jsonify(portfolio_correlation_report(_symbols(), request.args.get('period', '1y'), request.args.get('interval', '1d')))

    @app.route('/v35/market-regime')
    def v35_market_regime():
        return jsonify(market_regime(request.args.get('symbol', 'SPY'), request.args.get('period', '1y'), request.args.get('interval', '1d')))



    @app.route('/v35/portfolio-optimizer')
    def v35_portfolio_optimizer():
        return jsonify(portfolio_optimizer(_symbols(), request.args.get('period', '1y'), request.args.get('interval', '1d'), float(request.args.get('max_weight', 0.30))))

    @app.route('/v35/ensemble')
    def v35_ensemble():
        rows = []
        for s in _symbols():
            rows.append(ensemble_signal(s, fetch_ohlcv(s, request.args.get('period', '1y'), request.args.get('interval', '1d'))))
        return jsonify({"ok": True, "version": V35_VERSION, "rows": rows})

    @app.route('/v35/position-sizing', methods=['POST'])
    def v35_position_sizing():
        block = _require_key()
        if block:
            return block
        payload = request.get_json(silent=True) or {}
        sig = payload.get('signal') or payload
        return jsonify(position_sizing_engine(sig, payload.get('performance'), payload.get('account_equity', 100000), payload.get('risk_per_trade_pct', 0.5), payload.get('max_position_pct', 20.0), payload.get('target_vol_ann', 0.18)))

    @app.route('/v35/monte-carlo')
    def v35_monte_carlo():
        return jsonify(monte_carlo_many(_symbols(), request.args.get('period', '2y'), request.args.get('interval', '1d'), int(request.args.get('simulations', 2000))))

    @app.route('/v35/trade-journal', methods=['POST'])
    def v35_trade_journal():
        block = _require_key()
        if block:
            return block
        payload = request.get_json(silent=True) or {}
        return jsonify(trade_journal_ai(payload.get('trades', [])))

    @app.route('/v35/alpha-stack')
    def v35_alpha_stack():
        return jsonify(alpha_stack_report(_symbols(), request.args.get('period', '1y'), request.args.get('interval', '1d')))

    @app.route('/v35/risk-gate', methods=['POST'])
    def v35_risk_gate_route():
        block = _require_key()
        if block:
            return block
        payload = request.get_json(silent=True) or {}
        return jsonify(risk_gate(payload.get('signal') or payload, payload.get('account_equity', 100000), payload.get('risk_per_trade_pct', 0.5), payload.get('max_position_pct', 20.0), payload.get('min_score', 72)))

    @app.route('/v35/dashboard')
    def v35_dashboard():
        symbols = _symbols()
        ranking = rank_signals(symbols, request.args.get('period', '1y'), request.args.get('interval', '1d'))
        backtests = backtest_many(symbols, request.args.get('bt_period', '2y'), request.args.get('interval', '1d'))
        def esc(x): return html.escape('' if x is None else str(x))
        rows = ''.join(f"<tr><td>{r.get('rank')}</td><td>{esc(r.get('symbol'))}</td><td>{esc(r.get('price'))}</td><td>{esc(r.get('score'))}</td><td>{esc(r.get('signal'))}</td><td>{esc(r.get('action'))}</td><td>{esc(r.get('entry_zone'))}</td><td>{esc(r.get('stop_loss'))}</td><td>{esc(r.get('take_profit'))}</td><td>{esc(r.get('institutional_gate',{}).get('decision'))}</td><td>{esc(r.get('data_quality',{}).get('score'))}</td><td>{esc(', '.join(r.get('institutional_gate',{}).get('reasons',[])[:4]))}</td></tr>" for r in ranking.get('rows', []))
        btrows = ''.join(f"<tr><td>{esc(r.get('symbol'))}</td><td>{esc(r.get('return_pct'))}%</td><td>{esc(r.get('trades'))}</td><td>{esc(r.get('win_rate_pct'))}%</td><td>{esc(r.get('profit_factor'))}</td><td>{esc(r.get('max_drawdown_pct'))}%</td><td>{esc(r.get('sharpe'))}</td></tr>" for r in backtests.get('rows', []))
        return Response(f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>V35 Institutional Free Dashboard</title><style>body{{font-family:Arial,sans-serif;padding:18px;background:#f7f7f7;color:#111}}h1{{font-size:24px}}.note{{color:#555;margin-bottom:12px}}.wrap{{overflow-x:auto;background:white;border:1px solid #ddd;margin-bottom:18px}}table{{border-collapse:collapse;min-width:1100px;width:100%}}th,td{{border:1px solid #ddd;padding:7px;font-size:13px}}th{{background:#111;color:#fff}}tr:nth-child(even){{background:#fafafa}}.warn{{background:#fff7db;border:1px solid #e7c86a;padding:10px;margin:10px 0}}</style></head><body><h1>V35.3 Free Alpha Stack Dashboard</h1><div class='warn'>Research/Paper Trading only. Free data can be delayed/incomplete. Institutional Gate = Risk Gate + Data Quality + Market Regime.</div><h2>Signal Ranking: เข้าเมื่อไร / ซื้ออะไร</h2><div class='note'>Market Regime: {esc(ranking.get('market_regime',{}).get('regime'))} | High-correlation pairs: {len(ranking.get('correlation',{}).get('high_corr_pairs',[]) or [])}</div><div class='wrap'><table><thead><tr><th>Rank</th><th>Symbol</th><th>Price</th><th>Score</th><th>Signal</th><th>Action</th><th>Entry Zone</th><th>SL</th><th>TP</th><th>Institutional Gate</th><th>DQ Score</th><th>Gate Reasons</th></tr></thead><tbody>{rows}</tbody></table></div><h2>Backtest Performance</h2><div class='wrap'><table><thead><tr><th>Symbol</th><th>Return</th><th>Trades</th><th>Win Rate</th><th>Profit Factor</th><th>Max DD</th><th>Sharpe</th></tr></thead><tbody>{btrows}</tbody></table></div><div class='note'>API: /v35/ranking, /v35/alpha-stack, /v35/portfolio-optimizer, /v35/ensemble, /v35/position-sizing, /v35/monte-carlo, /v35/trade-journal, /v35/backtest, /v35/walk-forward, /v35/risk-gate</div></body></html>""", mimetype='text/html')
