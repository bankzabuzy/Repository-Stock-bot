from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from modules.v36_institutional_free_core import (
    _safe_float, fetch_ohlcv, make_indicators, latest_signal, rank_signals,
    backtest_many, walk_forward_many, forward_test_plan, portfolio_optimizer,
    position_sizing_engine, ensemble_signal, monte_carlo_many, trade_journal_ai,
    portfolio_correlation_report, market_regime, data_quality_gate, institutional_decision,
    performance_report
)

V36_VERSION = "V36_INSTITUTIONAL_FREE"

# ------------------------------------------------------------
# 1) Execution Simulator: spread/slippage/delay/partial fill
# ------------------------------------------------------------
def execution_simulator(order: Dict[str, Any], df: Optional[pd.DataFrame] = None,
                        spread_bps: float = 8.0, slippage_bps: float = 12.0,
                        delay_bars: int = 1, liquidity_participation: float = 0.05) -> Dict[str, Any]:
    side = str(order.get('side') or order.get('signal') or 'BUY').upper()
    symbol = str(order.get('symbol', 'UNKNOWN')).upper()
    qty = abs(_safe_float(order.get('qty'), 0) or 0)
    ref_price = _safe_float(order.get('price') or order.get('entry'), 0) or 0
    if (df is None or df.empty) and symbol != 'UNKNOWN':
        df = fetch_ohlcv(symbol, '6mo', '1d')
    if df is not None and not df.empty and 'Close' in df:
        idx = -1
        if len(df) > max(1, delay_bars):
            idx = min(len(df)-1, max(0, len(df)-1))
        ref_price = ref_price or float(df['Close'].iloc[idx])
        avg_vol = float(df.get('Volume', pd.Series([0])).tail(20).mean()) if 'Volume' in df else 0.0
    else:
        avg_vol = 0.0
    if ref_price <= 0 or qty <= 0:
        return {'ok': False, 'version': V36_VERSION, 'symbol': symbol, 'error': 'invalid_price_or_qty'}
    max_fill = qty
    if avg_vol > 0:
        max_fill = max(1.0, avg_vol * max(0.001, min(liquidity_participation, 0.25)))
    filled_qty = min(qty, max_fill)
    partial_fill = filled_qty < qty
    direction = 1 if side in {'BUY', 'LONG'} else -1
    fill_price = ref_price * (1 + direction * ((spread_bps / 2.0 + slippage_bps) / 10000.0))
    cost = abs(fill_price - ref_price) * filled_qty
    return {'ok': True, 'version': V36_VERSION, 'symbol': symbol, 'side': side, 'requested_qty': round(qty, 6),
            'filled_qty': round(filled_qty, 6), 'partial_fill': bool(partial_fill), 'reference_price': round(ref_price, 4),
            'estimated_fill_price': round(fill_price, 4), 'estimated_cost': round(cost, 2),
            'assumptions': {'spread_bps': spread_bps, 'slippage_bps': slippage_bps, 'delay_bars': delay_bars,
                            'liquidity_participation': liquidity_participation}}

# ------------------------------------------------------------
# 2) Portfolio Heat + 3) Factor Exposure
# ------------------------------------------------------------
def _position_notional(p: Dict[str, Any]) -> float:
    if 'notional' in p:
        return abs(_safe_float(p.get('notional'), 0) or 0)
    return abs((_safe_float(p.get('qty'), 0) or 0) * (_safe_float(p.get('price'), 0) or 0))

def _sector(symbol: str) -> str:
    s = symbol.upper().replace('.BK','')
    tech = {'NVDA','AMD','AAPL','MSFT','META','GOOGL','GOOG','AMZN','QQQ','TSLA','PLTR','AVGO','SMCI','MU','CRWD','SNOW','NET','DDOG'}
    finance = {'JPM','BAC','SCB','KBANK','BBL','KTB'}
    energy = {'XOM','CVX','PTT','PTTEP'}
    defensive = {'SPY','DIA','IWM','WMT','COST','UNH','LLY'}
    if s in tech: return 'TECH_GROWTH'
    if s in finance: return 'FINANCIALS'
    if s in energy: return 'ENERGY'
    if s in defensive: return 'BROAD_DEFENSIVE'
    if s in {'GC=F','GOLD','XAUUSD'}: return 'GOLD_SAFE_HAVEN'
    return 'OTHER'

def factor_exposure(positions: List[Dict[str, Any]], account_equity: float = 100000.0) -> Dict[str, Any]:
    account_equity = max(float(account_equity or 1), 1.0)
    buckets: Dict[str, float] = {}
    gross = 0.0
    for p in positions or []:
        sym = str(p.get('symbol','UNKNOWN')).upper()
        notional = _position_notional(p)
        gross += notional
        buckets[_sector(sym)] = buckets.get(_sector(sym), 0.0) + notional
    rows = [{'factor': k, 'notional': round(v,2), 'exposure_pct': round(v/account_equity*100,2)} for k,v in sorted(buckets.items(), key=lambda x:x[1], reverse=True)]
    warnings = []
    if any(r['exposure_pct'] > 45 for r in rows): warnings.append('single_factor_exposure_above_45pct')
    if gross/account_equity > 1.0: warnings.append('gross_exposure_above_100pct')
    return {'ok': True, 'version': V36_VERSION, 'gross_exposure_pct': round(gross/account_equity*100,2), 'rows': rows, 'warnings': warnings or ['pass']}

def portfolio_heat(positions: List[Dict[str, Any]], account_equity: float = 100000.0,
                   max_total_risk_pct: float = 6.0, max_single_risk_pct: float = 1.0) -> Dict[str, Any]:
    account_equity = max(float(account_equity or 1), 1.0)
    rows=[]; total_risk=0.0; gross=0.0
    for p in positions or []:
        sym=str(p.get('symbol','UNKNOWN')).upper(); qty=abs(_safe_float(p.get('qty'),0) or 0)
        price=_safe_float(p.get('price'),0) or 0; stop=_safe_float(p.get('stop_loss'), price*0.95) or price*0.95
        notional=_position_notional({**p,'price':price}); risk_cash=max(price-stop,0)*qty
        gross += notional; total_risk += risk_cash
        rows.append({'symbol': sym, 'notional': round(notional,2), 'risk_cash': round(risk_cash,2),
                     'risk_pct': round(risk_cash/account_equity*100,2), 'factor': _sector(sym)})
    warnings=[]
    if total_risk/account_equity*100 > max_total_risk_pct: warnings.append('portfolio_heat_too_high')
    if any(r['risk_pct'] > max_single_risk_pct for r in rows): warnings.append('single_position_risk_too_high')
    fx = factor_exposure(positions, account_equity)
    if fx['warnings'] != ['pass']: warnings.extend(fx['warnings'])
    return {'ok': True, 'version': V36_VERSION, 'total_risk_pct': round(total_risk/account_equity*100,2),
            'gross_exposure_pct': round(gross/account_equity*100,2), 'decision': 'ALLOW' if not warnings else 'REDUCE_RISK',
            'warnings': warnings or ['pass'], 'rows': rows, 'factor_exposure': fx}

# ------------------------------------------------------------
# 4) Dynamic Stop Engine
# ------------------------------------------------------------
def dynamic_stop_engine(symbol: str, df: Optional[pd.DataFrame] = None, entry_price: Optional[float] = None,
                        mode: str = 'adaptive') -> Dict[str, Any]:
    if df is None or df.empty:
        df = fetch_ohlcv(symbol, '1y', '1d')
    ind = make_indicators(df)
    if ind.empty or len(ind) < 60:
        return {'ok': False, 'version': V36_VERSION, 'symbol': symbol.upper(), 'error': 'not_enough_data'}
    row=ind.iloc[-1]; price=_safe_float(entry_price, None) or (_safe_float(row.get('Close'),0) or 0)
    atr=_safe_float(row.get('atr14'), price*0.03) or price*0.03
    vol=_safe_float(ind['ret'].tail(20).std()*math.sqrt(252), 0.25) or 0.25
    mult = 1.6 if vol < 0.25 else (2.2 if vol < 0.45 else 3.0)
    atr_stop = price - atr*mult
    vol_stop = price * (1 - min(0.12, max(0.025, vol/8)))
    trailing = max(float(ind['Close'].tail(20).max()) - atr*mult, atr_stop)
    stop = max(atr_stop, vol_stop, trailing) if mode == 'adaptive' else atr_stop
    return {'ok': True, 'version': V36_VERSION, 'symbol': symbol.upper(), 'price': round(price,4), 'mode': mode,
            'atr14': round(atr,4), 'vol20_ann': round(vol,4), 'atr_stop': round(atr_stop,4),
            'volatility_stop': round(vol_stop,4), 'trailing_stop': round(trailing,4), 'recommended_stop': round(stop,4)}

# ------------------------------------------------------------
# 5) Strategy Rotation + 6) Meta AI Filter + 7) Alpha Decay
# ------------------------------------------------------------
def strategy_rotation(symbols: List[str], period: str = '2y', interval: str = '1d') -> Dict[str, Any]:
    # Free proxy: infer from market regime + recent returns dispersion.
    reg = market_regime('SPY', '1y', interval)
    corr = portfolio_correlation_report(symbols, '1y', interval)
    high_corr = len(corr.get('high_corr_pairs', []) or []) if corr.get('ok') else 0
    if reg.get('regime') == 'RISK_ON' and high_corr < max(3, len(symbols)//2): active = 'trend_momentum'
    elif reg.get('regime') == 'RISK_OFF': active = 'capital_protection_mean_reversion_light'
    else: active = 'balanced_ensemble'
    weights = {'trend': 0.40, 'momentum': 0.35, 'mean_reversion': 0.15, 'volume': 0.10}
    if active == 'balanced_ensemble': weights = {'trend':0.30,'momentum':0.25,'mean_reversion':0.30,'volume':0.15}
    if active.startswith('capital'): weights = {'trend':0.20,'momentum':0.15,'mean_reversion':0.45,'volume':0.20}
    return {'ok': True, 'version': V36_VERSION, 'active_strategy': active, 'weights': weights, 'market_regime': reg, 'high_corr_pairs': high_corr}

def meta_ai_filter(signal: Dict[str, Any], backtest: Optional[Dict[str, Any]] = None,
                   wf: Optional[Dict[str, Any]] = None, mc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    score = _safe_float(signal.get('score') or signal.get('ensemble_score'), 0) or 0
    prob = 0.35 + max(0, score-50)/100.0
    reasons=[]
    if backtest and backtest.get('ok'):
        if (_safe_float(backtest.get('profit_factor'),0) or 0) >= 1.5: prob += 0.10; reasons.append('pf_pass')
        if (_safe_float(backtest.get('sharpe'),0) or 0) >= 1.0: prob += 0.08; reasons.append('sharpe_pass')
        if (_safe_float(backtest.get('max_drawdown_pct'),-99) or -99) > -15: prob += 0.06; reasons.append('dd_pass')
    if wf and wf.get('pass'): prob += 0.08; reasons.append('walk_forward_pass')
    if mc and mc.get('pass'): prob += 0.05; reasons.append('monte_carlo_pass')
    prob = max(0.0, min(0.95, prob))
    decision = 'ALLOW' if signal.get('signal') == 'BUY' and prob >= 0.62 else 'BLOCK'
    if decision == 'BLOCK': reasons.append('meta_probability_below_threshold_or_not_buy')
    return {'ok': True, 'version': V36_VERSION, 'probability_edge': round(prob,3), 'decision': decision, 'reasons': reasons or ['base_signal_only']}

def alpha_decay_detector(backtest_rows: List[Dict[str, Any]], lookback_label: str = 'latest') -> Dict[str, Any]:
    valid=[r for r in backtest_rows or [] if r.get('ok')]
    warnings=[]; rows=[]
    for r in valid:
        sharpe=_safe_float(r.get('sharpe'),0) or 0; pf=_safe_float(r.get('profit_factor'),0) or 0; dd=_safe_float(r.get('max_drawdown_pct'),-99) or -99
        health=100
        if sharpe < 1.0: health -= 25
        if pf < 1.3: health -= 25
        if dd < -15: health -= 25
        if (_safe_float(r.get('trades'),0) or 0) < 5: health -= 15
        status='HEALTHY' if health>=75 else ('WATCH' if health>=50 else 'DECAY_RISK')
        if status!='HEALTHY': warnings.append(f"{r.get('symbol')}:alpha_{status.lower()}")
        rows.append({'symbol':r.get('symbol'), 'alpha_health_score':max(0,health), 'status':status, 'sharpe':sharpe, 'profit_factor':pf, 'max_drawdown_pct':dd})
    return {'ok': True, 'version': V36_VERSION, 'lookback': lookback_label, 'warnings': warnings or ['pass'], 'rows': rows}

# ------------------------------------------------------------
# 8) Portfolio Attribution + 9) Capital Allocation + 10) Self-Healing
# ------------------------------------------------------------
def portfolio_attribution(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    buckets: Dict[str, float] = {}
    total=0.0
    for t in trades or []:
        pnl=_safe_float(t.get('pnl'), None)
        if pnl is None:
            entry=_safe_float(t.get('entry'),0) or 0; exitp=_safe_float(t.get('exit'),0) or 0; qty=_safe_float(t.get('qty'),1) or 1
            pnl=(exitp-entry)*qty
        strat=str(t.get('strategy') or t.get('reason') or 'unknown').lower()
        key='trend' if 'trend' in strat else ('momentum' if 'momentum' in strat else ('mean_reversion' if 'mean' in strat else ('position_sizing' if 'size' in strat else 'other')))
        buckets[key]=buckets.get(key,0.0)+pnl; total+=pnl
    rows=[{'bucket':k,'pnl':round(v,2),'contribution_pct':round(v/total*100,2) if total else 0} for k,v in sorted(buckets.items(), key=lambda x:abs(x[1]), reverse=True)]
    return {'ok': True, 'version': V36_VERSION, 'total_pnl': round(total,2), 'rows': rows, 'finding': 'positive_attribution' if total>0 else 'needs_more_forward_data'}

def capital_allocation_engine(symbols: List[str], account_equity: float = 100000.0, cash_floor_pct: float = 20.0,
                              period: str = '1y', interval: str = '1d') -> Dict[str, Any]:
    opt=portfolio_optimizer(symbols, period, interval, max_weight=0.30)
    reg=market_regime('SPY','1y',interval)
    cash_pct = max(cash_floor_pct, 45.0 if reg.get('regime')=='RISK_OFF' else (30.0 if reg.get('regime')=='CAUTION' else cash_floor_pct))
    invest_pct = max(0.0, 100.0-cash_pct)
    rows=[]
    for r in opt.get('rows',[]):
        w = (r.get('weight_pct',0) or 0) * invest_pct / 100.0
        rows.append({'symbol': r.get('symbol'), 'weight_pct': round(w,2), 'notional': round(account_equity*w/100.0,2),
                     'source_weight_pct': r.get('weight_pct'), 'score': r.get('score'), 'ensemble_score': r.get('ensemble_score')})
    rows.append({'symbol':'CASH', 'weight_pct': round(cash_pct,2), 'notional': round(account_equity*cash_pct/100.0,2), 'role':'risk_buffer'})
    return {'ok': True, 'version': V36_VERSION, 'account_equity': account_equity, 'market_regime': reg, 'rows': rows,
            'rule': 'free optimizer scaled by market regime cash floor'}

def self_healing_monitor(symbols: List[str], period: str = '6mo', interval: str = '1d') -> Dict[str, Any]:
    checks=[]; actions=[]
    for s in symbols:
        df=fetch_ohlcv(s, period, interval)
        dq=data_quality_gate(s, df, min_bars=60)
        checks.append({'symbol':s.upper(), 'data_quality_ok':dq.get('ok'), 'bars':dq.get('bars'), 'reasons':dq.get('reasons')})
        if not dq.get('ok'):
            actions.append({'symbol':s.upper(), 'action':'fallback_to_hold_and_skip_new_orders', 'reason':'data_quality_failed'})
    status='OK' if not actions else 'DEGRADED_SAFE_MODE'
    return {'ok': True, 'version': V36_VERSION, 'status': status, 'checks': checks, 'actions': actions or [{'action':'none','reason':'all_checks_pass'}],
            'heartbeat_utc': datetime.now(timezone.utc).isoformat()}

# ------------------------------------------------------------
# V36 integrated reports + validation gates
# ------------------------------------------------------------
def institutional_readiness_score(backtests: Dict[str,Any], wf: Dict[str,Any], mc: Dict[str,Any]) -> Dict[str,Any]:
    bt_rows=[r for r in backtests.get('rows',[]) if r.get('ok')]
    pass_metrics=0; total=5
    if bt_rows:
        avg_wr=sum((_safe_float(r.get('win_rate_pct'),0) or 0) for r in bt_rows)/len(bt_rows)
        avg_pf=sum((_safe_float(r.get('profit_factor'),0) or 0) for r in bt_rows)/len(bt_rows)
        avg_sh=sum((_safe_float(r.get('sharpe'),0) or 0) for r in bt_rows)/len(bt_rows)
        worst_dd=min((_safe_float(r.get('max_drawdown_pct'),-99) or -99) for r in bt_rows)
    else:
        avg_wr=avg_pf=avg_sh=0; worst_dd=-99
    if avg_wr > 50: pass_metrics+=1
    if avg_pf > 1.5: pass_metrics+=1
    if avg_sh > 1.5: pass_metrics+=1
    if worst_dd > -15: pass_metrics+=1
    if any(r.get('pass') for r in wf.get('rows',[])): pass_metrics+=1
    mc_pass=sum(1 for r in mc.get('rows',[]) if r.get('pass'))
    score=round(pass_metrics/total*100,2)
    return {'ok': True, 'version': V36_VERSION, 'readiness_score_pct': score,
            'metrics': {'avg_win_rate_pct':round(avg_wr,2), 'avg_profit_factor':round(avg_pf,2), 'avg_sharpe':round(avg_sh,2), 'worst_drawdown_pct':round(worst_dd,2), 'monte_carlo_pass_count':mc_pass},
            'decision': 'PAPER_READY' if score>=80 else 'RESEARCH_ONLY',
            'note': 'Forward test 30-90 calendar days must be collected from real paper-trade records before live money.'}

def v36_institutional_report(symbols: List[str], period: str='1y', interval: str='1d', account_equity: float=100000.0) -> Dict[str,Any]:
    ranking=rank_signals(symbols, period, interval)
    backtests=backtest_many(symbols, '2y', interval)
    wf=walk_forward_many(symbols, '5y', interval)
    mc=monte_carlo_many(symbols, '2y', interval, simulations=1000)
    rotation=strategy_rotation(symbols, '2y', interval)
    alloc=capital_allocation_engine(symbols, account_equity, period=period, interval=interval)
    decay=alpha_decay_detector(backtests.get('rows',[]))
    healing=self_healing_monitor(symbols, '6mo', interval)
    # Build paper positions from allowed buys for heat check
    positions=[]
    bt_map={r.get('symbol'):r for r in backtests.get('rows',[]) if r.get('ok')}
    wf_map={r.get('symbol'):r for r in wf.get('rows',[]) if r.get('ok')}
    mc_map={r.get('symbol'):r for r in mc.get('rows',[]) if r.get('ok')}
    for r in ranking.get('rows',[]):
        meta=meta_ai_filter(r, bt_map.get(r.get('symbol')), wf_map.get(r.get('symbol')), mc_map.get(r.get('symbol')))
        r['meta_ai_filter']=meta
        r['dynamic_stop']=dynamic_stop_engine(r.get('symbol'), entry_price=r.get('price'))
        if r.get('action') == 'BUY_NOW_ZONE' and meta.get('decision')=='ALLOW':
            ps=position_sizing_engine(r, bt_map.get(r.get('symbol')), account_equity=account_equity)
            r['v36_position_sizing']=ps
            positions.append({'symbol':r.get('symbol'), 'qty':ps.get('suggested_qty'), 'price':r.get('price'), 'stop_loss':r['dynamic_stop'].get('recommended_stop')})
    heat=portfolio_heat(positions, account_equity)
    readiness=institutional_readiness_score(backtests,wf,mc)
    return {'ok': True, 'version': V36_VERSION, 'mode':'free_100_percent_research_paper_trading', 'symbols':symbols,
            'ranking':ranking, 'strategy_rotation':rotation, 'capital_allocation':alloc, 'portfolio_heat':heat,
            'backtests':backtests, 'walk_forward':wf, 'monte_carlo':mc, 'alpha_decay':decay, 'self_healing':healing,
            'readiness':readiness}
