from __future__ import annotations

import math
import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None

V35_VERSION = "V35.3_FREE_ALPHA_STACK"


def _safe_float(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None:
            return default
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def normalize_symbol(symbol: str) -> str:
    s = str(symbol or "").strip().upper()
    if s in {"GOLD", "XAUUSD", "XAU/USD"}:
        return "GC=F"
    if s == "THAI_GOLD":
        return "GC=F"
    if s and ".BK" not in s and s in {"SCB", "AOT", "PTT", "CPALL", "KBANK", "BBL", "KTB", "ADVANC", "BDMS", "PTTEP"}:
        return s + ".BK"
    return s


def fetch_ohlcv(symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    if yf is None or os.getenv('DISABLE_YFINANCE', 'false').lower() == 'true':
        return pd.DataFrame()
    try:
        df = yf.download(normalize_symbol(symbol), period=period, interval=interval, auto_adjust=True, progress=False, threads=False, timeout=5)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        df = df.dropna().copy()
        return df
    except Exception:
        return pd.DataFrame()


def make_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if out.empty or "Close" not in out:
        return out
    close = out["Close"].astype(float)
    out["ret"] = close.pct_change()
    out["ema20"] = close.ewm(span=20, adjust=False).mean()
    out["ema50"] = close.ewm(span=50, adjust=False).mean()
    out["ema200"] = close.ewm(span=200, adjust=False).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, pd.NA)
    out["rsi"] = 100 - (100 / (1 + rs))
    high = out.get("High", close).astype(float)
    low = out.get("Low", close).astype(float)
    prev = close.shift(1)
    tr = pd.concat([(high - low), (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    out["atr14"] = tr.rolling(14).mean()
    if "Volume" in out:
        vol = out["Volume"].astype(float)
        out["rvol"] = vol / vol.rolling(20).mean().replace(0, pd.NA)
    else:
        out["rvol"] = 1.0
    out["rolling_peak"] = close.cummax()
    out["drawdown"] = close / out["rolling_peak"] - 1.0
    return out


def latest_signal(symbol: str, df: pd.DataFrame) -> Dict[str, Any]:
    df = make_indicators(df)
    if df.empty or len(df) < 60:
        return {"symbol": symbol, "signal": "NO_DATA", "score": 0, "rank_score": 0, "reasons": ["not_enough_data"]}
    row = df.iloc[-1]
    prev = df.iloc[-2]
    price = _safe_float(row.get("Close"), 0.0) or 0.0
    ema20 = _safe_float(row.get("ema20"), price) or price
    ema50 = _safe_float(row.get("ema50"), price) or price
    ema200 = _safe_float(row.get("ema200"), price) or price
    rsi = _safe_float(row.get("rsi"), 50.0) or 50.0
    rvol = _safe_float(row.get("rvol"), 1.0) or 1.0
    atr = _safe_float(row.get("atr14"), 0.0) or 0.0
    momentum20 = _safe_float(price / df["Close"].iloc[-21] - 1, 0.0) if len(df) > 22 else 0.0
    momentum60 = _safe_float(price / df["Close"].iloc[-61] - 1, 0.0) if len(df) > 62 else 0.0
    vol20 = _safe_float(df["ret"].tail(20).std() * math.sqrt(252), 0.0) or 0.0

    score = 50.0
    reasons: List[str] = []
    if price > ema20: score += 8; reasons.append("price>ema20")
    else: score -= 8; reasons.append("price<ema20")
    if ema20 > ema50: score += 10; reasons.append("ema20>ema50")
    else: score -= 10; reasons.append("ema20<ema50")
    if price > ema200: score += 8; reasons.append("price>ema200")
    else: score -= 8; reasons.append("price<ema200")
    if 50 <= rsi <= 68: score += 10; reasons.append("healthy_rsi")
    elif rsi > 75: score -= 8; reasons.append("overbought_rsi")
    elif rsi < 40: score -= 8; reasons.append("weak_rsi")
    if momentum20 and momentum20 > 0: score += min(10, momentum20 * 120); reasons.append("positive_20d_momentum")
    if momentum60 and momentum60 > 0: score += min(7, momentum60 * 60); reasons.append("positive_60d_momentum")
    if rvol >= 0.8: score += 4; reasons.append("volume_ok")
    if vol20 > 0.65: score -= 8; reasons.append("high_volatility")

    score = max(0, min(100, round(score, 2)))
    if score >= 72:
        signal = "BUY"
    elif score <= 32:
        signal = "SELL"
    else:
        signal = "HOLD"
    stop = price - max(atr * 1.8, price * 0.025)
    take_profit = price + max(atr * 2.8, price * 0.045)
    rr = (take_profit - price) / max(price - stop, 1e-9)
    return {
        "symbol": symbol.upper(), "normalized_symbol": normalize_symbol(symbol), "price": round(price, 4),
        "signal": signal, "score": score, "rank_score": score, "rsi": round(rsi, 2), "rvol": round(rvol, 2),
        "ema20": round(ema20, 4), "ema50": round(ema50, 4), "ema200": round(ema200, 4),
        "atr14": round(atr, 4), "vol20_ann": round(vol20, 4), "momentum20": round(momentum20 or 0, 4),
        "momentum60": round(momentum60 or 0, 4), "entry_zone": [round(price*0.995,4), round(price*1.005,4)],
        "stop_loss": round(stop, 4), "take_profit": round(take_profit, 4), "risk_reward": round(rr, 2),
        "reasons": reasons[-8:]
    }


def risk_gate(signal: Dict[str, Any], account_equity: float = 100000.0, risk_per_trade_pct: float = 0.5,
              max_position_pct: float = 20.0, min_score: float = 72.0) -> Dict[str, Any]:
    side = signal.get("signal")
    price = _safe_float(signal.get("price"), 0) or 0
    stop = _safe_float(signal.get("stop_loss"), 0) or 0
    score = _safe_float(signal.get("score"), 0) or 0
    reasons: List[str] = []
    ok = True
    if side != "BUY": ok = False; reasons.append("not_buy_signal")
    if score < min_score: ok = False; reasons.append("score_below_min")
    if price <= 0 or stop <= 0 or stop >= price: ok = False; reasons.append("invalid_price_or_stop")
    if _safe_float(signal.get("risk_reward"), 0) < 1.2: ok = False; reasons.append("rr_too_low")
    if _safe_float(signal.get("vol20_ann"), 0) > 0.8: ok = False; reasons.append("volatility_too_high")
    risk_cash = account_equity * (risk_per_trade_pct / 100.0)
    per_share_risk = max(price - stop, 1e-9)
    qty_by_risk = risk_cash / per_share_risk if price > 0 else 0
    qty_by_cap = (account_equity * max_position_pct / 100.0) / price if price > 0 else 0
    qty = max(0, min(qty_by_risk, qty_by_cap))
    return {
        "ok": bool(ok), "decision": "ALLOW_BUY" if ok else "BLOCK", "reasons": reasons or ["pass"],
        "risk_cash": round(risk_cash, 2), "suggested_qty": round(qty, 6),
        "suggested_notional": round(qty * price, 2), "max_position_pct": max_position_pct,
        "risk_per_trade_pct": risk_per_trade_pct
    }



def data_quality_gate(symbol: str, df: pd.DataFrame, min_bars: int = 120) -> Dict[str, Any]:
    reasons: List[str] = []
    ok = True
    if df is None or df.empty:
        return {"ok": False, "symbol": symbol.upper(), "score": 0, "reasons": ["empty_data"]}
    if len(df) < min_bars:
        ok = False; reasons.append("insufficient_history")
    required = ["Open", "High", "Low", "Close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        ok = False; reasons.append("missing_" + "_".join(missing))
    close = df.get("Close")
    nan_ratio = float(close.isna().mean()) if close is not None and len(close) else 1.0
    if nan_ratio > 0.02:
        ok = False; reasons.append("too_many_missing_closes")
    bad_prices = int((close.astype(float) <= 0).sum()) if close is not None else 1
    if bad_prices:
        ok = False; reasons.append("non_positive_prices")
    score = 100 - min(100, int(nan_ratio * 100)) - (0 if len(df) >= min_bars else 25) - (20 if missing else 0) - (20 if bad_prices else 0)
    return {"ok": bool(ok), "symbol": symbol.upper(), "score": max(0, score), "bars": int(len(df)), "missing_close_pct": round(nan_ratio*100, 2), "reasons": reasons or ["pass"]}


def market_regime(symbol: str = "SPY", period: str = "1y", interval: str = "1d") -> Dict[str, Any]:
    df = make_indicators(fetch_ohlcv(symbol, period, interval))
    if df.empty or len(df) < 80:
        return {"ok": False, "regime": "UNKNOWN", "risk_on": False, "reasons": ["no_regime_data"]}
    row = df.iloc[-1]
    price = _safe_float(row.get("Close"), 0) or 0
    ema50 = _safe_float(row.get("ema50"), price) or price
    ema200 = _safe_float(row.get("ema200"), price) or price
    vol20 = _safe_float(row.get("ret"), 0)
    realized = _safe_float(df["ret"].tail(20).std()*math.sqrt(252), 0) or 0
    dd = _safe_float(row.get("drawdown"), 0) or 0
    risk_on = price > ema200 and ema50 > ema200 and realized < 0.35 and dd > -0.12
    regime = "RISK_ON" if risk_on else ("CAUTION" if price > ema200 else "RISK_OFF")
    reasons=[]
    reasons.append("price>ema200" if price>ema200 else "price<ema200")
    reasons.append("ema50>ema200" if ema50>ema200 else "ema50<ema200")
    if realized >= 0.35: reasons.append("market_vol_high")
    if dd <= -0.12: reasons.append("market_drawdown")
    return {"ok": True, "symbol": symbol, "regime": regime, "risk_on": bool(risk_on), "price": round(price,4), "vol20_ann": round(realized,4), "drawdown_pct": round(dd*100,2), "reasons": reasons}


def portfolio_correlation_report(symbols: List[str], period: str = "1y", interval: str = "1d") -> Dict[str, Any]:
    closes = {}
    for s in symbols:
        df = fetch_ohlcv(s, period, interval)
        if not df.empty and "Close" in df:
            closes[s.upper()] = df["Close"].astype(float).pct_change().dropna()
    if len(closes) < 2:
        return {"ok": False, "error": "not_enough_symbols"}
    ret = pd.DataFrame(closes).dropna()
    corr = ret.corr().round(3)
    pairs=[]
    cols=list(corr.columns)
    for i in range(len(cols)):
        for j in range(i+1,len(cols)):
            c=float(corr.iloc[i,j])
            if c>=0.75:
                pairs.append({"a": cols[i], "b": cols[j], "corr": c, "warning": "high_correlation_do_not_overweight_together"})
    return {"ok": True, "symbols": cols, "high_corr_pairs": pairs[:20], "matrix": corr.to_dict()}


def institutional_decision(signal: Dict[str, Any], dq: Optional[Dict[str, Any]] = None, regime: Optional[Dict[str, Any]] = None, account_equity: float = 100000.0) -> Dict[str, Any]:
    gate = risk_gate(signal, account_equity=account_equity)
    reasons = list(gate.get("reasons", []))
    ok = bool(gate.get("ok"))
    if dq and not dq.get("ok"):
        ok = False; reasons.append("data_quality_block")
    if regime and regime.get("regime") == "RISK_OFF":
        ok = False; reasons.append("market_regime_risk_off")
    elif regime and regime.get("regime") == "CAUTION" and (_safe_float(signal.get("score"),0) or 0) < 82:
        ok = False; reasons.append("caution_requires_score_82")
    action = "ALLOW_BUY" if ok else "BLOCK"
    return {"ok": ok, "decision": action, "reasons": reasons or ["pass"], "risk_gate": gate, "data_quality": dq, "market_regime": regime}


def rank_signals(symbols: List[str], period: str = "1y", interval: str = "1d") -> Dict[str, Any]:
    rows = []
    regime = market_regime("SPY", period="1y", interval="1d")
    for s in symbols:
        df = fetch_ohlcv(s, period, interval)
        dq = data_quality_gate(s, df, min_bars=120 if interval == "1d" else 80)
        sig = latest_signal(s, df)
        sig["data_quality"] = dq
        sig["institutional_gate"] = institutional_decision(sig, dq, regime)
        sig["risk_gate"] = sig["institutional_gate"]["risk_gate"]
        rows.append(sig)
    rows.sort(key=lambda x: (_safe_float(x.get("rank_score"), 0) or 0), reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
        r["action"] = "BUY_NOW_ZONE" if r.get("institutional_gate", {}).get("ok") else ("WATCH" if r.get("signal") == "BUY" else r.get("signal"))
    corr = portfolio_correlation_report(symbols, period=period, interval=interval)
    return {"ok": True, "version": V35_VERSION, "market_regime": regime, "correlation": corr, "rows": rows, "top_buy": [r for r in rows if r.get("institutional_gate", {}).get("ok")][:5]}


def backtest_symbol(symbol: str, period: str = "2y", interval: str = "1d", initial_cash: float = 100000.0) -> Dict[str, Any]:
    raw = fetch_ohlcv(symbol, period, interval)
    df = make_indicators(raw)
    if df.empty or len(df) < 80:
        return {"ok": False, "symbol": symbol, "error": "not_enough_data"}
    cash, qty, entry = float(initial_cash), 0.0, 0.0
    equity_curve: List[float] = []
    trades: List[float] = []
    for i in range(60, len(df)):
        sub = df.iloc[:i+1]
        sig = latest_signal(symbol, sub)
        price = _safe_float(sub.iloc[-1].get("Close"), 0) or 0
        if price <= 0:
            continue
        if qty <= 0 and sig.get("signal") == "BUY" and sig.get("score", 0) >= 72:
            notional = cash * 0.2
            qty = notional / price
            cash -= notional
            entry = price
        elif qty > 0:
            stop = _safe_float(sig.get("stop_loss"), entry * 0.93) or entry * 0.93
            tp = _safe_float(sig.get("take_profit"), entry * 1.12) or entry * 1.12
            if price <= stop or price >= tp or sig.get("signal") == "SELL":
                pnl = (price - entry) * qty
                trades.append(pnl)
                cash += qty * price
                qty, entry = 0.0, 0.0
        equity_curve.append(cash + qty * price)
    if qty > 0:
        price = _safe_float(df.iloc[-1].get("Close"), entry) or entry
        trades.append((price - entry) * qty)
        cash += qty * price
    return performance_report(symbol, initial_cash, cash, equity_curve, trades)


def performance_report(symbol: str, initial_cash: float, final_equity: float, equity_curve: List[float], trades: List[float]) -> Dict[str, Any]:
    wins = [x for x in trades if x > 0]
    losses = [x for x in trades if x < 0]
    total = len(trades)
    win_rate = (len(wins) / total * 100) if total else 0.0
    gross_win, gross_loss = sum(wins), abs(sum(losses))
    profit_factor = gross_win / gross_loss if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0)
    eq = pd.Series(equity_curve or [initial_cash], dtype=float)
    rets = eq.pct_change().dropna()
    sharpe = (rets.mean() / rets.std() * math.sqrt(252)) if len(rets) > 2 and rets.std() > 0 else 0.0
    dd = (eq / eq.cummax() - 1.0).min() if len(eq) else 0.0
    return {"ok": True, "symbol": symbol.upper(), "initial_cash": round(initial_cash,2), "final_equity": round(final_equity,2),
            "return_pct": round((final_equity/initial_cash-1)*100,2), "trades": total, "win_rate_pct": round(win_rate,2),
            "profit_factor": round(profit_factor,2), "max_drawdown_pct": round(dd*100,2), "sharpe": round(float(sharpe),2),
            "gross_profit": round(gross_win,2), "gross_loss": round(gross_loss,2)}


def backtest_many(symbols: List[str], period: str = "2y", interval: str = "1d") -> Dict[str, Any]:
    rows = [backtest_symbol(s, period, interval) for s in symbols]
    rows.sort(key=lambda r: (r.get("ok", False), _safe_float(r.get("sharpe"), -99) or -99, _safe_float(r.get("return_pct"), -99) or -99), reverse=True)
    return {"ok": True, "version": V35_VERSION, "rows": rows}



def walk_forward_validation(symbol: str, period: str = "5y", interval: str = "1d") -> Dict[str, Any]:
    raw = fetch_ohlcv(symbol, period, interval)
    df = make_indicators(raw)
    if df.empty or len(df) < 260:
        return {"ok": False, "symbol": symbol.upper(), "error": "not_enough_data_for_walk_forward"}
    n = len(df)
    windows = []
    step = max(60, n // 5)
    initial_cash = 100000.0
    for start in range(80, n-step+1, step):
        sub = df.iloc[:start+step].copy()
        # use only the newest window for out-of-sample proxy
        oos = sub.iloc[start:start+step].copy()
        if len(oos) < 40:
            continue
        tmp_path_df = pd.concat([df.iloc[:80], oos])
        # local mini backtest without external fetch
        cash, qty, entry = initial_cash, 0.0, 0.0
        curve=[]; trades=[]
        for i in range(60, len(tmp_path_df)):
            sig = latest_signal(symbol, tmp_path_df.iloc[:i+1])
            price = _safe_float(tmp_path_df.iloc[i].get("Close"),0) or 0
            if price<=0: continue
            if qty<=0 and sig.get("signal")=="BUY" and sig.get("score",0)>=72:
                notional=cash*0.2; qty=notional/price; cash-=notional; entry=price
            elif qty>0 and (price<=sig.get("stop_loss",0) or price>=sig.get("take_profit",10**9) or sig.get("signal")=="SELL"):
                trades.append((price-entry)*qty); cash+=qty*price; qty=0; entry=0
            curve.append(cash+qty*price)
        final = curve[-1] if curve else initial_cash
        rep = performance_report(symbol, initial_cash, final, curve, trades)
        windows.append(rep)
    if not windows:
        return {"ok": False, "symbol": symbol.upper(), "error": "no_windows"}
    positive = sum(1 for w in windows if w.get("return_pct",0)>0)
    avg_sharpe = sum(_safe_float(w.get("sharpe"),0) or 0 for w in windows)/len(windows)
    stability = positive/len(windows)*100
    return {"ok": True, "symbol": symbol.upper(), "windows": windows, "positive_window_pct": round(stability,2), "avg_sharpe": round(avg_sharpe,2), "pass": stability>=60 and avg_sharpe>0.3}


def walk_forward_many(symbols: List[str], period: str = "5y", interval: str = "1d") -> Dict[str, Any]:
    rows=[walk_forward_validation(s, period, interval) for s in symbols]
    rows.sort(key=lambda r: (r.get("pass", False), _safe_float(r.get("avg_sharpe"),-99) or -99), reverse=True)
    return {"ok": True, "version": V35_VERSION, "rows": rows}

def forward_test_plan(symbols: List[str]) -> Dict[str, Any]:
    ranked = rank_signals(symbols, period="6mo", interval="1d")
    rows = []
    for r in ranked["rows"]:
        gate = r.get("risk_gate", {})
        rows.append({"symbol": r.get("symbol"), "date_signal": None, "paper_action": r.get("action"), "entry_zone": r.get("entry_zone"),
                     "stop_loss": r.get("stop_loss"), "take_profit": r.get("take_profit"), "score": r.get("score"),
                     "gate": gate.get("decision"), "qty": gate.get("suggested_qty"),
                     "rule": "Record hypothetical fills daily; do not use real money until 30-90 days of positive out-of-sample results."})
    return {"ok": True, "version": V35_VERSION, "mode": "forward_test_watchlist", "rows": rows}

# ============================================================
# V35.3 FREE ALPHA STACK
# Portfolio Optimizer, Position Sizing, Ensemble Signal,
# Monte Carlo Stress Test, Trade Journal AI (100% free/local)
# ============================================================

def _returns_from_prices(df: pd.DataFrame) -> pd.Series:
    if df is None or df.empty or 'Close' not in df:
        return pd.Series(dtype=float)
    return df['Close'].astype(float).pct_change().replace([math.inf, -math.inf], pd.NA).dropna()


def ensemble_signal(symbol: str, df: pd.DataFrame) -> Dict[str, Any]:
    ind = make_indicators(df)
    if ind.empty or len(ind) < 80:
        return {'symbol': symbol.upper(), 'signal': 'NO_DATA', 'ensemble_score': 0, 'votes': {}, 'reasons': ['not_enough_data']}
    row = ind.iloc[-1]
    price = _safe_float(row.get('Close'), 0) or 0
    ema20 = _safe_float(row.get('ema20'), price) or price
    ema50 = _safe_float(row.get('ema50'), price) or price
    rsi = _safe_float(row.get('rsi'), 50) or 50
    rvol = _safe_float(row.get('rvol'), 1) or 1
    mom20 = _safe_float(price / ind['Close'].iloc[-21] - 1, 0) if len(ind) > 22 else 0
    mom60 = _safe_float(price / ind['Close'].iloc[-61] - 1, 0) if len(ind) > 62 else 0
    mean20 = _safe_float(ind['Close'].tail(20).mean(), price) or price
    std20 = _safe_float(ind['Close'].tail(20).std(), 0) or 0
    z20 = (price - mean20) / std20 if std20 > 0 else 0
    votes = {
        'trend': 1 if price > ema20 > ema50 else (-1 if price < ema20 < ema50 else 0),
        'momentum': 1 if (mom20 or 0) > 0 and (mom60 or 0) > 0 else (-1 if (mom20 or 0) < 0 and (mom60 or 0) < 0 else 0),
        'mean_reversion': 1 if -1.8 <= z20 <= -0.4 and rsi < 55 else (-1 if z20 > 2.0 or rsi > 76 else 0),
        'volume': 1 if rvol >= 1.0 and price > ema20 else (-1 if rvol >= 1.4 and price < ema20 else 0),
    }
    weights = {'trend': 0.35, 'momentum': 0.30, 'mean_reversion': 0.20, 'volume': 0.15}
    raw = sum(votes[k] * weights[k] for k in weights)
    score = round(50 + raw * 50, 2)
    if score >= 68:
        sig = 'BUY'
    elif score <= 32:
        sig = 'SELL'
    else:
        sig = 'HOLD'
    return {
        'symbol': symbol.upper(), 'signal': sig, 'ensemble_score': score, 'votes': votes,
        'z20': round(z20, 2), 'momentum20': round(mom20 or 0, 4), 'momentum60': round(mom60 or 0, 4),
        'rvol': round(rvol, 2), 'reasons': [k + ':' + str(v) for k, v in votes.items()]
    }


def position_sizing_engine(signal: Dict[str, Any], performance: Optional[Dict[str, Any]] = None,
                           account_equity: float = 100000.0, risk_per_trade_pct: float = 0.5,
                           max_position_pct: float = 20.0, target_vol_ann: float = 0.18) -> Dict[str, Any]:
    price = _safe_float(signal.get('price'), 0) or 0
    stop = _safe_float(signal.get('stop_loss'), 0) or 0
    vol = max(_safe_float(signal.get('vol20_ann'), 0.25) or 0.25, 0.01)
    edge_wr = (_safe_float((performance or {}).get('win_rate_pct'), 50) or 50) / 100.0
    pf = _safe_float((performance or {}).get('profit_factor'), 1.0) or 1.0
    avg_win_loss_ratio = max(0.5, min(3.0, pf * (1-edge_wr) / max(edge_wr, 1e-6)))
    kelly = edge_wr - ((1-edge_wr) / avg_win_loss_ratio)
    kelly_fraction = max(0.0, min(0.25, kelly * 0.5))  # half Kelly, capped
    risk_cash = account_equity * (risk_per_trade_pct / 100.0)
    per_unit_risk = max(price - stop, price * 0.01, 1e-9)
    qty_risk = risk_cash / per_unit_risk if price > 0 else 0
    notional_kelly = account_equity * kelly_fraction
    qty_kelly = notional_kelly / price if price > 0 else 0
    vol_weight = max(0.02, min(max_position_pct/100.0, target_vol_ann / vol * 0.10))
    qty_vol = account_equity * vol_weight / price if price > 0 else 0
    qty_cap = account_equity * (max_position_pct/100.0) / price if price > 0 else 0
    qty = max(0.0, min(qty_risk, qty_kelly if qty_kelly > 0 else qty_risk, qty_vol, qty_cap))
    return {
        'ok': price > 0 and stop > 0 and qty > 0,
        'method': 'min(risk_budget, half_kelly, volatility_target, max_cap)',
        'kelly_fraction': round(kelly_fraction, 4), 'volatility_weight': round(vol_weight, 4),
        'risk_cash': round(risk_cash, 2), 'suggested_qty': round(qty, 6),
        'suggested_notional': round(qty * price, 2), 'position_pct': round((qty*price)/account_equity*100, 2),
        'guards': {'risk_per_trade_pct': risk_per_trade_pct, 'max_position_pct': max_position_pct, 'target_vol_ann': target_vol_ann}
    }


def portfolio_optimizer(symbols: List[str], period: str = '1y', interval: str = '1d', max_weight: float = 0.30) -> Dict[str, Any]:
    rows = []
    rets = {}
    for s in symbols:
        df = fetch_ohlcv(s, period, interval)
        sig = latest_signal(s, df)
        ens = ensemble_signal(s, df)
        r = _returns_from_prices(df)
        if len(r) >= 40:
            rets[s.upper()] = r
            vol = float(r.std() * math.sqrt(252)) if r.std() > 0 else 0.99
            mom = _safe_float(sig.get('momentum60'), 0) or 0
            quality = max(0, (_safe_float(sig.get('score'), 0) or 0) / 100.0)
            ens_quality = max(0, (_safe_float(ens.get('ensemble_score'), 0) or 0) / 100.0)
            raw = max(0.0, (0.55*quality + 0.45*ens_quality) * (1 + max(mom, -0.2)) / max(vol, 0.05))
            rows.append({'symbol': s.upper(), 'raw': raw, 'score': sig.get('score'), 'ensemble_score': ens.get('ensemble_score'), 'vol_ann': round(vol,4)})
    # If the user supplies too few symbols, a strict 30% cap cannot sum to 100%.
    # Use the minimum feasible cap so the optimizer always returns a fully allocated paper portfolio.
    feasible_cap = max(float(max_weight), (1.0 / max(1, len(rows))))
    total = sum(x['raw'] for x in rows)
    if total <= 0:
        n = max(1, len(rows))
        for x in rows: x['weight_pct'] = round(100/n, 2)
    else:
        capped=[]; remainder=1.0
        for x in rows:
            w = min(feasible_cap, x['raw']/total)
            capped.append(w); remainder -= w
        # redistribute leftover to uncapped rows
        for _ in range(3):
            uncapped = [i for i,w in enumerate(capped) if w < feasible_cap-1e-9]
            if not uncapped or remainder <= 1e-9: break
            raw_uncap = sum(rows[i]['raw'] for i in uncapped) or len(uncapped)
            for i in uncapped:
                add = min(feasible_cap-capped[i], remainder * (rows[i]['raw']/raw_uncap if raw_uncap else 1/len(uncapped)))
                capped[i] += add
            remainder = 1.0 - sum(capped)
        for x,w in zip(rows,capped): x['weight_pct'] = round(w*100, 2)
    rows.sort(key=lambda x: x.get('weight_pct',0), reverse=True)
    return {'ok': True, 'version': V35_VERSION, 'method': 'free_score_momentum_inverse_vol_capped', 'max_weight_pct': round(feasible_cap*100,2), 'rows': rows}


def monte_carlo_stress_test(symbol: str, period: str = '2y', interval: str = '1d', simulations: int = 2000,
                            horizon_days: int = 90, initial_cash: float = 100000.0) -> Dict[str, Any]:
    df = fetch_ohlcv(symbol, period, interval)
    ret = _returns_from_prices(df)
    if len(ret) < 60:
        return {'ok': False, 'symbol': symbol.upper(), 'error': 'not_enough_returns'}
    sims = int(max(100, min(simulations, 10000)))
    horizon = int(max(20, min(horizon_days, 252)))
    # deterministic seed for repeatable tests/reports
    try:
        import numpy as np
        rng = np.random.default_rng(abs(hash(symbol.upper())) % (2**32))
        arr = ret.to_numpy(dtype=float)
        finals=[]; maxdds=[]
        for _ in range(sims):
            sample = rng.choice(arr, size=horizon, replace=True)
            curve = initial_cash * (1 + pd.Series(sample)).cumprod()
            finals.append(float(curve.iloc[-1]))
            maxdds.append(float((curve / curve.cummax() - 1).min()))
        finals_s = pd.Series(finals)
        dd_s = pd.Series(maxdds)
        prob_loss = float((finals_s < initial_cash).mean() * 100)
        return {'ok': True, 'symbol': symbol.upper(), 'simulations': sims, 'horizon_days': horizon,
                'median_final': round(float(finals_s.median()),2), 'p05_final': round(float(finals_s.quantile(0.05)),2),
                'p95_final': round(float(finals_s.quantile(0.95)),2), 'probability_loss_pct': round(prob_loss,2),
                'worst_5pct_drawdown_pct': round(float(dd_s.quantile(0.05))*100,2),
                'pass': prob_loss < 45 and float(dd_s.quantile(0.05)) > -0.25}
    except Exception as e:
        return {'ok': False, 'symbol': symbol.upper(), 'error': str(e)}


def monte_carlo_many(symbols: List[str], period: str = '2y', interval: str = '1d', simulations: int = 2000) -> Dict[str, Any]:
    rows = [monte_carlo_stress_test(s, period, interval, simulations) for s in symbols]
    rows.sort(key=lambda r: (r.get('pass', False), -(_safe_float(r.get('probability_loss_pct'), 999) or 999)), reverse=True)
    return {'ok': True, 'version': V35_VERSION, 'rows': rows}


def trade_journal_ai(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    cleaned=[]
    for t in trades or []:
        pnl = _safe_float(t.get('pnl'), None)
        entry = _safe_float(t.get('entry'), None)
        exitp = _safe_float(t.get('exit'), None)
        if pnl is None and entry and exitp:
            qty = _safe_float(t.get('qty'), 1) or 1
            side = str(t.get('side','BUY')).upper()
            pnl = (exitp-entry)*qty if side != 'SHORT' else (entry-exitp)*qty
        cleaned.append({**t, 'pnl': pnl or 0.0})
    wins=[t for t in cleaned if t['pnl']>0]; losses=[t for t in cleaned if t['pnl']<0]
    by_symbol={}
    for t in cleaned:
        s=str(t.get('symbol','UNKNOWN')).upper(); by_symbol.setdefault(s,[]).append(t['pnl'])
    notes=[]
    if len(losses)>len(wins): notes.append('losses_more_than_wins_review_entry_filter')
    if cleaned and sum(t['pnl'] for t in cleaned)<0: notes.append('negative_total_pnl_reduce_size_until_edge_confirmed')
    weak_symbols=[s for s,p in by_symbol.items() if sum(p)<0]
    if weak_symbols: notes.append('weak_symbols:' + ','.join(weak_symbols[:5]))
    return {'ok': True, 'version': V35_VERSION, 'trades': len(cleaned), 'wins': len(wins), 'losses': len(losses),
            'win_rate_pct': round(len(wins)/len(cleaned)*100,2) if cleaned else 0,
            'total_pnl': round(sum(t['pnl'] for t in cleaned),2),
            'avg_win': round(sum(t['pnl'] for t in wins)/len(wins),2) if wins else 0,
            'avg_loss': round(sum(t['pnl'] for t in losses)/len(losses),2) if losses else 0,
            'symbol_pnl': {s: round(sum(p),2) for s,p in by_symbol.items()},
            'ai_findings': notes or ['journal_ok_keep_forward_testing']}


def alpha_stack_report(symbols: List[str], period: str = '1y', interval: str = '1d') -> Dict[str, Any]:
    ranking = rank_signals(symbols, period, interval)
    backtests = backtest_many(symbols, '2y', interval)
    perf = {r.get('symbol'): r for r in backtests.get('rows', []) if r.get('ok')}
    for r in ranking.get('rows', []):
        s = r.get('symbol')
        df = fetch_ohlcv(s, period, interval)
        r['ensemble'] = ensemble_signal(s, df)
        r['position_sizing'] = position_sizing_engine(r, perf.get(s))
    return {'ok': True, 'version': V35_VERSION, 'ranking': ranking, 'portfolio_optimizer': portfolio_optimizer(symbols, period, interval), 'backtests': backtests}
