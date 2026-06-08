from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import numpy as np
    import pandas as pd
except Exception:  # pragma: no cover
    np = None
    pd = None

from modules.v35_institutional_free_core import _safe_float, fetch_ohlcv, latest_signal
from modules.v36_institutional_free_core import dynamic_stop_engine
from modules.v37_live_safety_broker_ready_core import audit_log
from modules.v38_institutional_free_core import (
    multi_source_data_validation, liquidity_filter, confidence_score,
    governance_layer, explainable_ai_engine, v38_pre_trade_pipeline
)
from modules.v39_validation_paper_broker_proof_core import trade_freeze_mode, load_config

V40_VERSION = "V40_ADAPTIVE_MULTI_AGENT_INSTITUTIONAL"
RUNTIME_DIR = Path(__file__).resolve().parents[1] / "runtime_v40"
RUNTIME_DIR.mkdir(exist_ok=True)
TRADE_MEMORY_FILE = RUNTIME_DIR / "trade_memory.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path, limit: int = 1000) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    rows: List[Dict[str, Any]] = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _last_close(df: Any) -> float:
    try:
        return float(df["Close"].dropna().iloc[-1])
    except Exception:
        return 0.0


def _series(df: Any, col: str = "Close") -> Any:
    try:
        return df[col].dropna()
    except Exception:
        return []


def _rsi(close: Any, period: int = 14) -> float:
    if pd is None or len(close) < period + 2:
        return 50.0
    delta = close.diff().dropna()
    up = delta.clip(lower=0).rolling(period).mean()
    down = (-delta.clip(upper=0)).rolling(period).mean()
    rs = up / down.replace(0, np.nan)
    val = 100 - (100 / (1 + rs.iloc[-1])) if not math.isnan(float(rs.iloc[-1])) else 50
    return float(max(0, min(100, val)))


def _atr(df: Any, period: int = 14) -> float:
    if pd is None or len(df) < period + 2:
        return 0.0
    high, low, close = df["High"], df["Low"], df["Close"]
    tr = pd.concat([(high-low), (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def _trend_agent(symbol: str, df: Any) -> Dict[str, Any]:
    close = _series(df)
    if pd is None or len(close) < 60:
        return {"agent": "TREND", "vote": "HOLD", "score": 50, "reason": "insufficient_trend_data"}
    ema20 = float(close.ewm(span=20).mean().iloc[-1])
    ema50 = float(close.ewm(span=50).mean().iloc[-1])
    price = float(close.iloc[-1])
    slope = (float(close.iloc[-1]) / float(close.iloc[-20]) - 1) * 100
    score = 50 + (18 if price > ema20 > ema50 else -18 if price < ema20 < ema50 else 0) + max(-12, min(12, slope))
    vote = "BUY" if score >= 62 else "SELL" if score <= 38 else "HOLD"
    return {"agent": "TREND", "vote": vote, "score": round(score, 2), "reason": f"price={price:.2f}, ema20={ema20:.2f}, ema50={ema50:.2f}, slope20={slope:.2f}%"}


def _structure_agent(symbol: str, df: Any) -> Dict[str, Any]:
    close = _series(df)
    if pd is None or len(close) < 40:
        return {"agent": "STRUCTURE", "vote": "HOLD", "score": 50, "reason": "insufficient_structure_data"}
    price = float(close.iloc[-1])
    resistance = float(close.tail(40).max())
    support = float(close.tail(40).min())
    rng = max(1e-9, resistance - support)
    loc = (price - support) / rng
    score = 50 + (loc - 0.5) * 40
    vote = "BUY" if loc > 0.62 else "SELL" if loc < 0.28 else "HOLD"
    return {"agent": "STRUCTURE", "vote": vote, "score": round(score, 2), "reason": f"range_location={loc:.2f}, support={support:.2f}, resistance={resistance:.2f}"}


def _counter_trend_agent(symbol: str, df: Any) -> Dict[str, Any]:
    close = _series(df)
    rsi = _rsi(close)
    score = 50
    vote = "HOLD"
    if rsi <= 32:
        score, vote = 68, "BUY"
    elif rsi >= 72:
        score, vote = 32, "SELL"
    return {"agent": "COUNTER_TREND", "vote": vote, "score": round(score, 2), "reason": f"rsi14={rsi:.2f}"}


def _macro_agent(symbol: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ctx = context or {}
    risk_on = str(ctx.get("market_regime", ctx.get("risk_regime", "neutral"))).lower()
    fear_greed = _safe_float(ctx.get("fear_greed", 50), 50) or 50
    score = 50
    if "risk_on" in risk_on or "bull" in risk_on:
        score += 12
    if "risk_off" in risk_on or "bear" in risk_on:
        score -= 12
    score += max(-10, min(10, (fear_greed - 50) / 5))
    vote = "BUY" if score >= 60 else "SELL" if score <= 40 else "HOLD"
    return {"agent": "MACRO", "vote": vote, "score": round(score, 2), "reason": f"regime={risk_on}, fear_greed={fear_greed}"}


def _liquidity_agent(symbol: str, df: Any, intended_notional: float = 10000) -> Dict[str, Any]:
    liq = liquidity_filter(symbol, intended_notional=intended_notional)
    decision = liq.get("decision", "ALLOW")
    score = 70 if decision == "ALLOW" else 35
    return {"agent": "LIQUIDITY", "vote": "BUY" if decision == "ALLOW" else "HOLD", "score": score, "reason": f"liquidity_decision={decision}", "details": liq}


def adaptive_agent_ensemble(symbol: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    s = symbol.upper().strip()
    df = fetch_ohlcv(s, period="1y", interval="1d")
    ctx = context or {}
    agents = [
        _trend_agent(s, df),
        _structure_agent(s, df),
        _counter_trend_agent(s, df),
        _macro_agent(s, ctx),
        _liquidity_agent(s, df, float(ctx.get("intended_notional", 10000))),
    ]
    weights = {"TREND": 0.30, "STRUCTURE": 0.25, "COUNTER_TREND": 0.15, "MACRO": 0.15, "LIQUIDITY": 0.15}
    weighted_score = sum(float(a["score"]) * weights.get(a["agent"], 0.2) for a in agents)
    buy_votes = sum(1 for a in agents if a["vote"] == "BUY")
    sell_votes = sum(1 for a in agents if a["vote"] == "SELL")
    if weighted_score >= 62 and buy_votes >= 2:
        signal = "BUY"
    elif weighted_score <= 38 and sell_votes >= 2:
        signal = "SELL"
    else:
        signal = "HOLD"
    disagreement = len(set(a["vote"] for a in agents)) - 1
    confidence = max(0, min(100, abs(weighted_score - 50) * 2 + 55 - disagreement * 8))
    return {"ok": True, "version": V40_VERSION, "symbol": s, "signal": signal, "weighted_score": round(weighted_score, 2), "confidence_pct": round(confidence, 2), "buy_votes": buy_votes, "sell_votes": sell_votes, "agents": agents, "price": _last_close(df)}


def chief_risk_officer_ai(symbol: str, ensemble: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ctx = context or {}
    freeze = trade_freeze_mode(ctx)
    gov = governance_layer({
        "trades_today": int(ctx.get("trades_today", 0)),
        "risk_per_trade_pct": float(ctx.get("risk_per_trade_pct", 1.0)),
        "daily_pnl_pct": float(ctx.get("daily_pnl_pct", 0.0)),
    })
    data = multi_source_data_validation(symbol)
    liq = liquidity_filter(symbol, intended_notional=float(ctx.get("intended_notional", 10000)))
    veto_reasons: List[str] = []
    if freeze.get("freeze_active"):
        veto_reasons.append("trade_freeze_active")
    if gov.get("decision") != "ALLOW":
        veto_reasons.append("governance_block")
    if data.get("decision") in {"BLOCK", "FAIL"}:
        veto_reasons.append("data_quality_block")
    if liq.get("decision") == "BLOCK":
        veto_reasons.append("liquidity_block")
    if float(ensemble.get("confidence_pct", 0)) < float(ctx.get("min_confidence_pct", 62)):
        veto_reasons.append("low_agent_confidence")
    action = "VETO" if veto_reasons else "APPROVE"
    size_multiplier = 0.0 if action == "VETO" else (0.5 if float(ensemble.get("confidence_pct", 0)) < 75 else 1.0)
    return {"ok": True, "version": V40_VERSION, "symbol": symbol.upper(), "action": action, "size_multiplier": size_multiplier, "veto_reasons": veto_reasons or ["pass"], "governance": gov, "data_quality": data, "liquidity": liq, "freeze": freeze}


def pyramid_tp_engine(entry_price: float, side: str = "BUY", atr: Optional[float] = None, risk_r: float = 1.0) -> Dict[str, Any]:
    entry = float(entry_price)
    direction = 1 if side.upper() == "BUY" else -1
    base_risk = float(atr or max(entry * 0.01, 0.01)) * float(risk_r)
    stop = entry - direction * base_risk
    tp1 = entry + direction * base_risk * 1.0
    tp2 = entry + direction * base_risk * 2.0
    tp3 = entry + direction * base_risk * 3.5
    plan = [
        {"level": "TP1", "price": round(tp1, 4), "close_pct": 25, "after_fill": "move_stop_to_break_even"},
        {"level": "TP2", "price": round(tp2, 4), "close_pct": 25, "after_fill": "trail_by_1_ATR"},
        {"level": "TP3", "price": round(tp3, 4), "close_pct": 50, "after_fill": "exit_runner"},
    ]
    return {"ok": True, "version": V40_VERSION, "entry_price": entry, "side": side.upper(), "initial_stop": round(stop, 4), "break_even_price": round(entry, 4), "risk_per_share": round(base_risk, 4), "tp_plan": plan}


def news_context_layer(symbol: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ctx = context or {}
    events = ctx.get("events", []) or []
    keywords = {"FOMC", "CPI", "NFP", "NONFARM", "EARNINGS", "RATE", "FED"}
    hits = []
    for e in events:
        text = str(e).upper()
        if any(k in text for k in keywords):
            hits.append(str(e))
    severity = "HIGH" if any("FOMC" in h.upper() or "CPI" in h.upper() for h in hits) else "MEDIUM" if hits else "LOW"
    score_penalty = 20 if severity == "HIGH" else 10 if severity == "MEDIUM" else 0
    decision = "REDUCE_SIZE" if severity == "HIGH" else "ALLOW"
    return {"ok": True, "version": V40_VERSION, "symbol": symbol.upper(), "decision": decision, "severity": severity, "score_penalty": score_penalty, "events_detected": hits}


def record_trade_memory(symbol: str, setup: str, result_pct: float, holding_minutes: int = 0, notes: str = "") -> Dict[str, Any]:
    row = {"ts": _now(), "version": V40_VERSION, "symbol": symbol.upper(), "setup": setup, "result_pct": float(result_pct), "holding_minutes": int(holding_minutes), "notes": notes}
    _append_jsonl(TRADE_MEMORY_FILE, row)
    try:
        audit_log("v40_trade_memory_recorded", row, "INFO")
    except Exception:
        pass
    return {"ok": True, "row": row}


def trade_memory_engine(symbol: Optional[str] = None, setup: Optional[str] = None) -> Dict[str, Any]:
    rows = _read_jsonl(TRADE_MEMORY_FILE, 5000)
    if symbol:
        rows = [r for r in rows if r.get("symbol") == symbol.upper()]
    if setup:
        rows = [r for r in rows if str(r.get("setup", "")).lower() == setup.lower()]
    if not rows:
        return {"ok": True, "version": V40_VERSION, "sample_trades": 0, "insight": "no_trade_memory_yet", "win_rate_pct": 0, "avg_result_pct": 0}
    results = [float(r.get("result_pct", 0)) for r in rows]
    wins = [x for x in results if x > 0]
    losses = [x for x in results if x <= 0]
    by_setup: Dict[str, List[float]] = {}
    for r in rows:
        by_setup.setdefault(str(r.get("setup", "unknown")), []).append(float(r.get("result_pct", 0)))
    setup_summary = {k: {"trades": len(v), "avg_result_pct": round(sum(v)/len(v), 3), "win_rate_pct": round(sum(1 for x in v if x > 0)/len(v)*100, 2)} for k, v in by_setup.items()}
    best_setup = max(setup_summary.items(), key=lambda kv: kv[1]["avg_result_pct"])[0]
    return {"ok": True, "version": V40_VERSION, "sample_trades": len(rows), "win_rate_pct": round(len(wins)/len(rows)*100, 2), "avg_result_pct": round(sum(results)/len(results), 3), "best_setup": best_setup, "setup_summary": setup_summary}


def v40_pre_trade_pipeline(symbol: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    s = symbol.upper().strip()
    ctx = context or {}
    ensemble = adaptive_agent_ensemble(s, ctx)
    news = news_context_layer(s, ctx)
    if news["score_penalty"]:
        ensemble["weighted_score_after_news"] = round(max(0, ensemble["weighted_score"] - news["score_penalty"]), 2)
        ensemble["confidence_pct"] = round(max(0, ensemble["confidence_pct"] - news["score_penalty"]), 2)
        if ensemble["confidence_pct"] < 62:
            ensemble["signal"] = "HOLD"
    cro = chief_risk_officer_ai(s, ensemble, ctx)
    price = float(ensemble.get("price") or latest_signal(s).get("price") or 100)
    try:
        df = fetch_ohlcv(s, period="1y", interval="1d")
        atr = _atr(df)
    except Exception:
        atr = price * 0.01
    tp = pyramid_tp_engine(price, ensemble.get("signal", "BUY") if ensemble.get("signal") in {"BUY", "SELL"} else "BUY", atr=atr)
    xai = explainable_ai_engine({"symbol": s, "signal": ensemble.get("signal"), "score": ensemble.get("weighted_score"), "price": price}, {"governance": cro.get("governance"), "liquidity": cro.get("liquidity"), "data_quality": cro.get("data_quality")})
    final_decision = "BLOCK" if cro["action"] == "VETO" else ("TRADE_READY" if ensemble.get("signal") in {"BUY", "SELL"} else "WATCH")
    return {"ok": True, "version": V40_VERSION, "symbol": s, "final_decision": final_decision, "ensemble": ensemble, "chief_risk_officer": cro, "news_context": news, "pyramid_tp": tp, "explainability": xai, "trade_memory": trade_memory_engine(s)}


def v40_full_report(symbols: Optional[List[str]] = None, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    syms = symbols or ["NVDA", "AAPL", "TSLA", "QQQ", "SPY"]
    rows = [v40_pre_trade_pipeline(s, context or {}) for s in syms]
    ready = [r for r in rows if r.get("final_decision") == "TRADE_READY"]
    watch = [r for r in rows if r.get("final_decision") == "WATCH"]
    blocked = [r for r in rows if r.get("final_decision") == "BLOCK"]
    return {"ok": True, "version": V40_VERSION, "summary": {"trade_ready": len(ready), "watch": len(watch), "blocked": len(blocked), "symbols": len(rows)}, "rows": rows, "generated_at": _now()}
