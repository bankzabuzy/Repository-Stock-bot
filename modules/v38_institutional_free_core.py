from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.v35_institutional_free_core import (
    _safe_float, fetch_ohlcv, latest_signal, backtest_many, walk_forward_many,
    monte_carlo_many, performance_report, data_quality_gate
)
from modules.v36_institutional_free_core import (
    factor_exposure, portfolio_heat, capital_allocation_engine, meta_ai_filter,
    v36_institutional_report
)
from modules.v37_live_safety_broker_ready_core import (
    V37_VERSION, news_event_risk_filter, model_drift_detector, kill_switch_status,
    live_readiness_score, health_check_dashboard, v37_pre_trade_pipeline
)

V38_VERSION = "V38_INSTITUTIONAL_FREE_PLUS"

SECTOR_MAP = {
    'NVDA':'TECH','AMD':'TECH','AAPL':'TECH','MSFT':'TECH','META':'TECH','GOOGL':'TECH','GOOG':'TECH','AMZN':'TECH','QQQ':'TECH','TSLA':'TECH','PLTR':'TECH',
    'JPM':'FINANCIALS','BAC':'FINANCIALS','SCB':'FINANCIALS','KBANK':'FINANCIALS','BBL':'FINANCIALS','KTB':'FINANCIALS',
    'XOM':'ENERGY','CVX':'ENERGY','PTT':'ENERGY','PTTEP':'ENERGY', 'SPY':'BROAD_MARKET','DIA':'BROAD_MARKET','IWM':'BROAD_MARKET',
    'GOLD':'COMMODITY','GC=F':'COMMODITY','XAUUSD':'COMMODITY'
}
COUNTRY_MAP = {'SCB':'TH','KBANK':'TH','BBL':'TH','KTB':'TH','PTT':'TH','PTTEP':'TH','AOT':'TH','CPALL':'TH'}
ASSET_CLASS_MAP = {'SPY':'ETF','QQQ':'ETF','DIA':'ETF','IWM':'ETF','GOLD':'COMMODITY','GC=F':'COMMODITY','XAUUSD':'COMMODITY'}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sym(symbol: str) -> str:
    return str(symbol or 'UNKNOWN').upper().replace('.BK', '')


def classify_asset(symbol: str) -> Dict[str, str]:
    s = _sym(symbol)
    return {
        'symbol': s,
        'sector': SECTOR_MAP.get(s, 'OTHER'),
        'asset_class': ASSET_CLASS_MAP.get(s, 'EQUITY'),
        'country': COUNTRY_MAP.get(s, 'US'),
    }


def _position_notional(p: Dict[str, Any]) -> float:
    if 'notional' in p:
        return abs(_safe_float(p.get('notional'), 0) or 0)
    return abs((_safe_float(p.get('qty'), 0) or 0) * (_safe_float(p.get('price'), 0) or 0))


# 1) Explainable AI Engine
def explainable_ai_engine(signal: Dict[str, Any], validations: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    symbol = _sym(signal.get('symbol'))
    action = str(signal.get('signal') or signal.get('action') or 'HOLD').upper()
    score = _safe_float(signal.get('score') or signal.get('ensemble_score'), 50) or 50
    price = _safe_float(signal.get('price'), 0) or 0
    val = validations or {}
    components = []
    def add(name: str, points: float, reason: str):
        components.append({'name': name, 'points': round(points, 2), 'reason': reason})
    add('base_signal_score', min(35, max(0, (score - 40) * 0.7)), f'raw signal score={round(score,2)}')
    if val.get('meta_ai', {}).get('decision') == 'ALLOW': add('meta_ai_filter', 18, 'meta AI approved signal')
    elif val.get('meta_ai'): add('meta_ai_filter', -18, 'meta AI did not approve')
    if val.get('risk_gate', {}).get('decision') in {'ALLOW', 'PASS', None}: add('risk_gate', 12, 'risk gate acceptable')
    if val.get('event_filter', {}).get('decision') == 'ALLOW': add('event_risk', 10, 'no configured high-risk event today')
    elif val.get('event_filter'): add('event_risk', -20, 'event risk is active')
    if val.get('liquidity', {}).get('decision') == 'ALLOW': add('liquidity', 10, 'liquidity filter passed')
    elif val.get('liquidity'): add('liquidity', -15, 'liquidity filter blocked/reduced')
    if val.get('governance', {}).get('decision') == 'ALLOW': add('governance', 15, 'governance rules passed')
    elif val.get('governance'): add('governance', -30, 'governance rules blocked')
    total = max(0, min(100, 50 + sum(c['points'] for c in components)))
    decision = action if total >= 70 and action in {'BUY','SELL'} else ('WATCH' if total >= 55 else 'HOLD')
    return {'ok': True, 'version': V38_VERSION, 'symbol': symbol, 'input_action': action, 'price': price,
            'explainability_score': round(total, 2), 'final_decision': decision, 'components': components,
            'summary': f'{decision} {symbol} because explainability score is {round(total,2)}/100'}


# 2) Multi-source data validation, free/offline-safe
def multi_source_data_validation(symbol: str, period: str = '1y', interval: str = '1d', backup_df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    s = _sym(symbol)
    primary = fetch_ohlcv(s, period, interval)
    primary_gate = data_quality_gate(s, primary) if primary is not None else {'ok': False, 'decision': 'BLOCK'}
    backup_gate = None
    reconciliation = {'status': 'not_available'}
    if backup_df is not None and not backup_df.empty:
        backup_gate = data_quality_gate(s, backup_df)
        if primary is not None and not primary.empty and 'Close' in primary and 'Close' in backup_df:
            p = float(primary['Close'].dropna().iloc[-1]); b = float(backup_df['Close'].dropna().iloc[-1])
            diff_bps = abs(p / b - 1.0) * 10000 if b else 99999
            reconciliation = {'status': 'OK' if diff_bps <= 50 else 'PRICE_DIVERGENCE', 'primary_close': round(p,4), 'backup_close': round(b,4), 'diff_bps': round(diff_bps,2)}
    selected = 'primary' if primary_gate.get('ok') else ('backup' if backup_gate and backup_gate.get('ok') else 'none')
    decision = 'ALLOW' if selected != 'none' and reconciliation.get('status') != 'PRICE_DIVERGENCE' else 'BLOCK'
    return {'ok': selected != 'none', 'version': V38_VERSION, 'symbol': s, 'selected_source': selected,
            'decision': decision, 'primary': primary_gate, 'backup': backup_gate, 'reconciliation': reconciliation,
            'note': 'Free mode uses primary yfinance/fetch_ohlcv and optional provided backup_df for validation.'}


# 3) Exposure manager
def exposure_manager(positions: List[Dict[str, Any]], account_equity: float = 100000.0,
                     max_sector_pct: float = 45.0, max_asset_class_pct: float = 70.0, max_country_pct: float = 85.0) -> Dict[str, Any]:
    eq = max(float(account_equity or 1), 1.0)
    buckets = {'sector': {}, 'asset_class': {}, 'country': {}}
    gross = 0.0
    for p in positions or []:
        cls = classify_asset(str(p.get('symbol','UNKNOWN')))
        notion = _position_notional(p); gross += notion
        for k in buckets:
            buckets[k][cls[k]] = buckets[k].get(cls[k], 0.0) + notion
    rows = []
    limits = {'sector': max_sector_pct, 'asset_class': max_asset_class_pct, 'country': max_country_pct}
    violations = []
    for typ, vals in buckets.items():
        for name, notional in vals.items():
            pct = notional / eq * 100
            row = {'type': typ, 'name': name, 'notional': round(notional,2), 'exposure_pct': round(pct,2), 'limit_pct': limits[typ]}
            rows.append(row)
            if pct > limits[typ]: violations.append({**row, 'violation': f'{typ}_limit_exceeded'})
    return {'ok': True, 'version': V38_VERSION, 'gross_exposure_pct': round(gross/eq*100,2),
            'decision': 'ALLOW' if not violations else 'REDUCE_OR_BLOCK', 'rows': rows, 'violations': violations or []}


# 4) Beta control
def _returns(symbol: str, period: str = '1y', interval: str = '1d') -> pd.Series:
    df = fetch_ohlcv(symbol, period, interval)
    if df is None or df.empty or 'Close' not in df:
        return pd.Series(dtype=float)
    return df['Close'].pct_change().dropna()


def beta_control(positions: List[Dict[str, Any]], benchmark: str = 'SPY', account_equity: float = 100000.0,
                 max_portfolio_beta: float = 1.25, period: str = '1y', interval: str = '1d') -> Dict[str, Any]:
    eq = max(float(account_equity or 1), 1.0)
    bench = _returns(benchmark, period, interval)
    rows = []; weighted_beta = 0.0
    for p in positions or []:
        s = _sym(p.get('symbol')); weight = _position_notional(p) / eq
        r = _returns(s, period, interval)
        beta = 1.0
        if len(r) > 30 and len(bench) > 30:
            joined = pd.concat([r, bench], axis=1).dropna()
            if len(joined) > 30 and joined.iloc[:,1].var() != 0:
                beta = float(joined.iloc[:,0].cov(joined.iloc[:,1]) / joined.iloc[:,1].var())
        weighted_beta += weight * beta
        rows.append({'symbol': s, 'weight_pct': round(weight*100,2), 'beta': round(beta,3), 'beta_contribution': round(weight*beta,3)})
    decision = 'ALLOW' if abs(weighted_beta) <= max_portfolio_beta else 'REDUCE_BETA'
    return {'ok': True, 'version': V38_VERSION, 'benchmark': benchmark, 'portfolio_beta': round(weighted_beta,3),
            'max_portfolio_beta': max_portfolio_beta, 'decision': decision, 'rows': rows}


# 5) Liquidity filter
def liquidity_filter(symbol: str, min_avg_dollar_volume: float = 20_000_000, max_participation_pct: float = 5.0,
                     intended_notional: float = 0.0, period: str = '3mo', interval: str = '1d') -> Dict[str, Any]:
    s = _sym(symbol); df = fetch_ohlcv(s, period, interval)
    if df is None or df.empty or 'Close' not in df:
        return {'ok': False, 'version': V38_VERSION, 'symbol': s, 'decision': 'BLOCK', 'error': 'no_data'}
    vol = df['Volume'] if 'Volume' in df else pd.Series([0])
    avg_dv = float((df['Close'].tail(20) * vol.tail(20)).mean()) if len(df) else 0.0
    intended = _safe_float(intended_notional, 0) or 0
    participation = (intended / avg_dv * 100) if avg_dv > 0 and intended > 0 else 0.0
    reasons = []
    if avg_dv < min_avg_dollar_volume: reasons.append('avg_dollar_volume_too_low')
    if participation > max_participation_pct: reasons.append('intended_order_too_large_for_liquidity')
    return {'ok': True, 'version': V38_VERSION, 'symbol': s, 'avg_dollar_volume_20d': round(avg_dv,2),
            'intended_notional': round(intended,2), 'participation_pct': round(participation,3),
            'decision': 'ALLOW' if not reasons else 'REDUCE_OR_BLOCK', 'reasons': reasons or ['pass']}


# 6) Confidence score
def confidence_score(signal: Dict[str, Any], validations: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    xai = explainable_ai_engine(signal, validations)
    score = xai['explainability_score']
    if validations:
        if validations.get('data', {}).get('decision') == 'ALLOW': score += 5
        if validations.get('benchmark', {}).get('alpha_vs_benchmark_pct', 0) > 0: score += 5
        if validations.get('ai_health', {}).get('status') == 'HEALTHY': score += 5
    conf = max(0, min(99, round(score, 2)))
    return {'ok': True, 'version': V38_VERSION, 'symbol': _sym(signal.get('symbol')), 'confidence_pct': conf,
            'label': 'HIGH' if conf >= 80 else ('MEDIUM' if conf >= 60 else 'LOW'), 'explainability': xai}


# 7) Scenario stress test
def scenario_stress_test(positions: List[Dict[str, Any]], account_equity: float = 100000.0) -> Dict[str, Any]:
    scenarios = {
        'COVID_2020_PROXY': {'EQUITY': -0.25, 'ETF': -0.22, 'TECH': -0.28, 'COMMODITY': 0.03},
        'GFC_2008_PROXY': {'EQUITY': -0.45, 'ETF': -0.40, 'TECH': -0.50, 'COMMODITY': 0.08},
        'CRASH_MINUS_20': {'EQUITY': -0.20, 'ETF': -0.20, 'TECH': -0.25, 'COMMODITY': 0.02},
        'RATE_SHOCK_PROXY': {'EQUITY': -0.12, 'ETF': -0.10, 'TECH': -0.18, 'COMMODITY': -0.03},
    }
    eq = max(float(account_equity or 1), 1.0)
    results = []
    for name, shocks in scenarios.items():
        pnl = 0.0
        detail=[]
        for p in positions or []:
            cls = classify_asset(str(p.get('symbol','UNKNOWN')))
            key = 'TECH' if cls['sector'] == 'TECH' else cls['asset_class']
            shock = shocks.get(key, shocks.get('EQUITY', -0.15))
            pos_pnl = _position_notional(p) * shock
            pnl += pos_pnl
            detail.append({'symbol': cls['symbol'], 'shock_pct': round(shock*100,2), 'pnl': round(pos_pnl,2)})
        results.append({'scenario': name, 'pnl': round(pnl,2), 'pnl_pct': round(pnl/eq*100,2), 'detail': detail})
    worst = min(results, key=lambda r: r['pnl_pct']) if results else {'pnl_pct': 0}
    decision = 'ALLOW' if worst['pnl_pct'] > -20 else ('REDUCE_RISK' if worst['pnl_pct'] > -35 else 'BLOCK_NEW_RISK')
    return {'ok': True, 'version': V38_VERSION, 'decision': decision, 'worst_case': worst, 'rows': results}


# 8) Benchmark comparison
def benchmark_comparison(symbols: List[str], benchmark_symbols: Optional[List[str]] = None, period: str = '1y', interval: str = '1d') -> Dict[str, Any]:
    benchmarks = benchmark_symbols or ['SPY', 'QQQ']
    bt_perf = backtest_many(symbols, period, interval)
    rows_perf = bt_perf.get('rows', []) if bt_perf.get('ok') else []
    perf = {'ok': True, 'rows': rows_perf, 'total_return_pct': round(sum((_safe_float(r.get('return_pct'),0) or 0) for r in rows_perf)/max(1,len(rows_perf)),2), 'avg_sharpe': round(sum((_safe_float(r.get('sharpe'),0) or 0) for r in rows_perf)/max(1,len(rows_perf)),2)}
    bench_rows = []
    for b in benchmarks:
        r = _returns(b, period, interval)
        if len(r) == 0:
            bench_rows.append({'benchmark': b, 'ok': False})
            continue
        total = (1 + r).prod() - 1
        vol = r.std() * math.sqrt(252) if r.std() else 0
        sharpe = (r.mean()*252) / vol if vol else 0
        bench_rows.append({'benchmark': b, 'ok': True, 'return_pct': round(total*100,2), 'sharpe': round(sharpe,3)})
    strategy_ret = _safe_float(perf.get('total_return_pct') or perf.get('avg_return_pct'), 0) or 0
    best_bench = max([x for x in bench_rows if x.get('ok')], key=lambda x: x.get('return_pct', -999), default={'return_pct':0, 'benchmark':'NA'})
    alpha = strategy_ret - best_bench.get('return_pct', 0)
    return {'ok': True, 'version': V38_VERSION, 'strategy_performance': perf, 'benchmarks': bench_rows,
            'best_benchmark': best_bench, 'alpha_vs_benchmark_pct': round(alpha,2),
            'decision': 'OUTPERFORM' if alpha > 0 else 'UNDERPERFORM_OR_NEEDS_REVIEW'}


# 9) AI health score
def ai_health_score(current_metrics: Dict[str, Any], baseline_metrics: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    drift = model_drift_detector(current_metrics, baseline_metrics)
    score = 100 - _safe_float(drift.get('drift_score'), 0)
    pf = _safe_float(current_metrics.get('profit_factor'), 0) or 0
    sh = _safe_float(current_metrics.get('sharpe'), 0) or 0
    if pf >= 1.5: score += 5
    if sh >= 1.5: score += 5
    score = max(0, min(100, round(score, 2)))
    status = 'HEALTHY' if score >= 80 else ('WATCH' if score >= 60 else 'DEGRADED')
    return {'ok': True, 'version': V38_VERSION, 'ai_health_score_pct': score, 'status': status,
            'drift': drift, 'decision': 'ALLOW' if status == 'HEALTHY' else ('REDUCE_SIZE' if status == 'WATCH' else 'BLOCK_OR_RETRAIN')}


# 10) Governance layer
def governance_layer(context: Dict[str, Any], max_trades_per_day: int = 3, max_risk_per_trade_pct: float = 2.0,
                     max_daily_drawdown_pct: float = 5.0) -> Dict[str, Any]:
    trades_today = int(_safe_float(context.get('trades_today'), 0) or 0)
    risk_pct = _safe_float(context.get('risk_per_trade_pct'), 0) or 0
    daily_pnl = _safe_float(context.get('daily_pnl_pct'), 0) or 0
    reasons = []
    if trades_today >= max_trades_per_day: reasons.append('max_trades_per_day_reached')
    if risk_pct > max_risk_per_trade_pct: reasons.append('risk_per_trade_too_high')
    if daily_pnl <= -abs(max_daily_drawdown_pct): reasons.append('daily_drawdown_limit_hit')
    kill = kill_switch_status(today_pnl_pct=daily_pnl, max_daily_dd_pct=max_daily_drawdown_pct)
    if kill.get('active'): reasons.append('kill_switch_active')
    return {'ok': True, 'version': V38_VERSION, 'decision': 'ALLOW' if not reasons else 'BLOCK',
            'reasons': reasons or ['pass'], 'rules': {'max_trades_per_day': max_trades_per_day,
            'max_risk_per_trade_pct': max_risk_per_trade_pct, 'max_daily_drawdown_pct': max_daily_drawdown_pct}, 'kill_switch': kill}


def v38_pre_trade_pipeline(symbol: str, account_equity: float = 100000.0, positions: Optional[List[Dict[str, Any]]] = None,
                           context: Optional[Dict[str, Any]] = None, dry_run: bool = True) -> Dict[str, Any]:
    positions = positions or []
    df = fetch_ohlcv(symbol, '1y', '1d')
    sig = latest_signal(symbol, df)
    data = multi_source_data_validation(symbol)
    liq = liquidity_filter(symbol, intended_notional=context.get('intended_notional', 0) if context else 0)
    gov = governance_layer(context or {})
    event = news_event_risk_filter(symbol)
    meta = meta_ai_filter(sig)
    validations = {'data': data, 'liquidity': liq, 'governance': gov, 'event_filter': event, 'meta_ai': meta}
    xai = explainable_ai_engine(sig, validations)
    conf = confidence_score(sig, validations)
    exp = exposure_manager(positions, account_equity)
    beta = beta_control(positions, account_equity=account_equity) if positions else {'ok': True, 'decision': 'ALLOW', 'rows': []}
    allowed = (sig.get('signal') == 'BUY' and data.get('decision') == 'ALLOW' and liq.get('decision') == 'ALLOW'
               and gov.get('decision') == 'ALLOW' and event.get('decision') == 'ALLOW' and conf.get('confidence_pct', 0) >= 60
               and exp.get('decision') == 'ALLOW' and beta.get('decision') == 'ALLOW')
    v37_result = None
    if allowed:
        v37_result = v37_pre_trade_pipeline(symbol, account_equity=account_equity, dry_run=dry_run)
    return {'ok': True, 'version': V38_VERSION, 'symbol': _sym(symbol), 'allowed': allowed,
            'decision': 'PASS_TO_V37_ORDER_LAYER' if allowed else 'BLOCK', 'signal': sig,
            'explainable_ai': xai, 'confidence': conf, 'data_validation': data, 'liquidity': liq,
            'governance': gov, 'event_filter': event, 'exposure': exp, 'beta_control': beta, 'v37_order_layer': v37_result}


def v38_institutional_report(symbols: List[str], positions: Optional[List[Dict[str, Any]]] = None,
                             account_equity: float = 100000.0, period: str = '1y', interval: str = '1d') -> Dict[str, Any]:
    positions = positions or [{'symbol': s, 'qty': 1, 'price': 100, 'notional': account_equity/max(1, len(symbols))*0.5} for s in symbols]
    bt = backtest_many(symbols, '2y', interval)
    wf = walk_forward_many(symbols, '5y', interval)
    mc = monte_carlo_many(symbols, '2y', interval, 1000)
    bench = benchmark_comparison(symbols, ['SPY','QQQ'], period, interval)
    exp = exposure_manager(positions, account_equity)
    beta = beta_control(positions, account_equity=account_equity, period=period, interval=interval)
    stress = scenario_stress_test(positions, account_equity)
    health_metric = (bt.get('rows') or [{}])[0] if bt.get('rows') else {}
    ai_health = ai_health_score(health_metric)
    allocation = capital_allocation_engine(symbols, account_equity, period=period, interval=interval)
    v37_ready = live_readiness_score(symbols, period, interval, account_equity)
    xai_rows=[]
    for s in symbols:
        sig = latest_signal(s, fetch_ohlcv(s, period, interval))
        xai_rows.append({'symbol': _sym(s), 'signal': sig.get('signal'), 'confidence': confidence_score(sig).get('confidence_pct'), 'explain': explainable_ai_engine(sig).get('summary')})
    score = _safe_float(v37_ready.get('live_safety_score_pct'), 0) or 0
    if exp.get('decision') == 'ALLOW': score += 3
    if beta.get('decision') == 'ALLOW': score += 3
    if stress.get('decision') == 'ALLOW': score += 3
    if bench.get('alpha_vs_benchmark_pct', -1) > 0: score += 3
    if ai_health.get('status') == 'HEALTHY': score += 3
    score = max(0, min(100, round(score,2)))
    return {'ok': True, 'version': V38_VERSION, 'mode': 'free_100_percent_institutional_governance_layer',
            'institutional_score_pct': score, 'decision': 'V38_PAPER_READY' if score >= 88 else ('RESEARCH_ONLY' if score >= 70 else 'NOT_READY'),
            'explainable_ai': xai_rows, 'data_validation_sample': [multi_source_data_validation(s, period, interval) for s in symbols[:3]],
            'exposure_manager': exp, 'beta_control': beta, 'scenario_stress': stress,
            'benchmark_comparison': bench, 'ai_health': ai_health, 'governance': governance_layer({}),
            'capital_allocation': allocation, 'v37_readiness': v37_ready, 'backtest': bt, 'walk_forward': wf, 'monte_carlo': mc,
            'safety_notice': 'V38 is still free research/paper infrastructure. Use real money only after broker paper forward testing and your own risk approval.'}
