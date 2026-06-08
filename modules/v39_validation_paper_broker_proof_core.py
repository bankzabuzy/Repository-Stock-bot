from __future__ import annotations

import json
import math
import os
import statistics
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
    import pandas as pd
except Exception:  # pragma: no cover
    np = None
    pd = None

from modules.v35_institutional_free_core import _safe_float, fetch_ohlcv, latest_signal, performance_report
from modules.v37_live_safety_broker_ready_core import get_broker, kill_switch_status, audit_log
from modules.v38_institutional_free_core import (
    V38_VERSION, v38_pre_trade_pipeline, benchmark_comparison, ai_health_score,
    governance_layer, confidence_score, scenario_stress_test, liquidity_filter,
    multi_source_data_validation
)

V39_VERSION = "V39_VALIDATION_PAPER_BROKER_PROOF"
STATE_DIR = Path(os.getenv("STOCKBOT_V39_STATE_DIR", "/tmp/stockbot_v39"))
STATE_DIR.mkdir(parents=True, exist_ok=True)
PROOF_FILE = STATE_DIR / "paper_proof_trades.jsonl"
DAILY_FILE = STATE_DIR / "daily_validation.jsonl"
CONFIG_FILE = Path(os.getenv("STOCKBOT_CONFIG_PATH", str(STATE_DIR / "config.json")))


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _read_jsonl(path: Path, limit: int = 5000) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows[-limit:]


def _ret_stats(returns: List[float]) -> Dict[str, float]:
    clean = [float(r) for r in returns if r is not None and math.isfinite(float(r))]
    if not clean:
        return {"total_return_pct": 0.0, "sharpe": 0.0, "max_drawdown_pct": 0.0, "win_rate_pct": 0.0, "profit_factor": 0.0, "expectancy_pct": 0.0}
    total = 1.0
    curve = [1.0]
    for r in clean:
        total *= (1.0 + r)
        curve.append(total)
    peak = curve[0]
    worst = 0.0
    for v in curve:
        peak = max(peak, v)
        if peak > 0:
            worst = min(worst, v / peak - 1.0)
    mean = statistics.fmean(clean)
    stdev = statistics.pstdev(clean) if len(clean) > 1 else 0.0
    sharpe = (mean / stdev * math.sqrt(252)) if stdev > 0 else 0.0
    wins = [r for r in clean if r > 0]
    losses = [r for r in clean if r < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = gross_win / gross_loss if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)
    expectancy = (sum(clean) / len(clean)) * 100.0
    return {
        "total_return_pct": round((total - 1.0) * 100, 2),
        "sharpe": round(sharpe, 3),
        "max_drawdown_pct": round(worst * 100, 2),
        "win_rate_pct": round(len(wins) / len(clean) * 100, 2),
        "profit_factor": round(pf, 3),
        "expectancy_pct": round(expectancy, 4),
    }


def load_config() -> Dict[str, Any]:
    defaults = {
        "max_trades_per_day": 3,
        "max_risk_per_trade_pct": 2.0,
        "max_daily_drawdown_pct": 5.0,
        "min_confidence_pct": 70.0,
        "min_profit_factor": 1.5,
        "min_sharpe": 1.5,
        "max_drawdown_pct": 15.0,
        "min_win_rate_pct": 50.0,
        "forward_windows": [30, 60, 90],
        "paper_broker": "mock",
        "freeze_on_failed_validation": True,
    }
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                defaults.update(data)
        except Exception:
            pass
    return {"ok": True, "version": V39_VERSION, "path": str(CONFIG_FILE), "config": defaults}


def save_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    cfg = load_config()["config"]
    cfg.update(updates or {})
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "version": V39_VERSION, "path": str(CONFIG_FILE), "config": cfg}


# 1) Real paper broker proof: one flow that can use mock or Alpaca paper through V37 adapter.
def paper_broker_connection_check(broker_name: Optional[str] = None) -> Dict[str, Any]:
    broker = get_broker(broker_name or load_config()["config"].get("paper_broker", "mock"))
    account = broker.account()
    ready = bool(account.get("ok"))
    return {"ok": ready, "version": V39_VERSION, "broker": getattr(broker, "name", "unknown"), "account": account,
            "mode": "paper_only", "note": "No real-money order is sent by V39 validation proof."}


def paper_order_proof(symbol: str = "SPY", side: str = "BUY", qty: float = 1.0, price: float = 100.0,
                      broker_name: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
    s = str(symbol).upper().strip()
    cfg = load_config()["config"]
    pre = v38_pre_trade_pipeline(s, context={"trades_today": 0, "risk_per_trade_pct": min(1.0, cfg["max_risk_per_trade_pct"]), "daily_pnl_pct": 0}, dry_run=True)
    if pre.get("final_decision") in {"BLOCK", "BLOCKED"}:
        row = {"ok": False, "version": V39_VERSION, "stage": "pre_trade", "symbol": s, "pre_trade": pre, "created_at": _now()}
        _append_jsonl(PROOF_FILE, row); audit_log("v39_paper_order_blocked", row, "WARNING")
        return row
    order = {"symbol": s, "side": str(side).upper(), "qty": float(qty), "type": "market", "time_in_force": "day", "price": float(price), "dry_run": bool(dry_run)}
    if dry_run:
        result = {"ok": True, "paper": True, "status": "dry_run_not_submitted", "submitted_order": order}
    else:
        broker = get_broker(broker_name or cfg.get("paper_broker", "mock"))
        result = broker.submit_order(order)
    row = {"ok": bool(result.get("ok")), "version": V39_VERSION, "symbol": s, "pre_trade": pre, "order_result": result, "created_at": _now()}
    _append_jsonl(PROOF_FILE, row); audit_log("v39_paper_order_proof", row, "INFO" if row["ok"] else "ERROR")
    return row


# 2) 30/60/90 day forward proof dashboard data from recorded proof trades or synthetic daily returns.
def record_forward_day(day_return_pct: float, trades: int = 0, notes: str = "") -> Dict[str, Any]:
    row = {"ts": _now(), "date": date.today().isoformat(), "version": V39_VERSION, "day_return_pct": float(day_return_pct), "trades": int(trades), "notes": notes}
    _append_jsonl(DAILY_FILE, row)
    return {"ok": True, "row": row}


def forward_validation_dashboard(windows: Optional[List[int]] = None) -> Dict[str, Any]:
    cfg = load_config()["config"]
    w = windows or cfg.get("forward_windows", [30, 60, 90])
    rows = _read_jsonl(DAILY_FILE, 1000)
    returns = [(_safe_float(r.get("day_return_pct"), 0) or 0) / 100.0 for r in rows]
    out = []
    for n in w:
        stats = _ret_stats(returns[-int(n):])
        passed = (stats["win_rate_pct"] >= cfg["min_win_rate_pct"] and stats["profit_factor"] >= cfg["min_profit_factor"] and stats["sharpe"] >= cfg["min_sharpe"] and abs(stats["max_drawdown_pct"]) <= cfg["max_drawdown_pct"] and stats["expectancy_pct"] > 0)
        out.append({"window_days": int(n), "sample_days": min(len(returns), int(n)), "passed": passed, **stats})
    overall = "PASS" if any(r["window_days"] >= 90 and r["sample_days"] >= 90 and r["passed"] for r in out) else "NOT_PROVEN_YET"
    return {"ok": True, "version": V39_VERSION, "overall_edge_status": overall, "criteria": {k: cfg[k] for k in ["min_win_rate_pct","min_profit_factor","min_sharpe","max_drawdown_pct"]}, "rows": out, "total_recorded_days": len(rows)}


# 3) Edge proof: strategy versus benchmark, not just absolute profit.
def edge_proof_report(symbols: Optional[List[str]] = None, benchmarks: Optional[List[str]] = None, period: str = "1y", interval: str = "1d") -> Dict[str, Any]:
    syms = symbols or ["NVDA", "AAPL", "SPY"]
    bench = benchmarks or ["SPY", "QQQ"]
    comp = benchmark_comparison(syms, bench, period, interval)
    fwd = forward_validation_dashboard()
    health = ai_health_score({
        "sharpe": fwd["rows"][-1]["sharpe"] if fwd["rows"] else 0,
        "profit_factor": fwd["rows"][-1]["profit_factor"] if fwd["rows"] else 0,
        "win_rate_pct": fwd["rows"][-1]["win_rate_pct"] if fwd["rows"] else 0,
        "max_drawdown_pct": fwd["rows"][-1]["max_drawdown_pct"] if fwd["rows"] else 0,
    })
    alpha_pass = bool(comp.get("decision") in {"OUTPERFORM", "ALLOW", "PASS"} or comp.get("alpha_vs_benchmark_pct", 0) > 0)
    proven = fwd.get("overall_edge_status") == "PASS" and alpha_pass and health.get("status") in {"HEALTHY", "WATCH"}
    return {"ok": True, "version": V39_VERSION, "edge_proven": proven, "decision": "PAPER_EDGE_PROVEN" if proven else "KEEP_TESTING", "benchmark_comparison": comp, "forward_validation": fwd, "ai_health": health}


# 4) Trade freeze mode combines V37 kill switch + validation failure.
def trade_freeze_mode(context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = load_config()["config"]
    ctx = context or {}
    ks = kill_switch_status(today_pnl_pct=float(ctx.get("daily_pnl_pct", 0)), consecutive_losses=int(ctx.get("consecutive_losses", 0)), max_daily_dd_pct=float(cfg["max_daily_drawdown_pct"]))
    fwd = forward_validation_dashboard()
    freeze = bool(ks.get("active"))
    reasons = list(ks.get("reasons", [])) if freeze else []
    if cfg.get("freeze_on_failed_validation") and fwd.get("total_recorded_days", 0) >= 30:
        last = fwd["rows"][0]
        if not last.get("passed"):
            freeze = True; reasons.append("30_day_validation_failed")
    return {"ok": True, "version": V39_VERSION, "freeze_active": freeze, "decision": "FREEZE_NEW_TRADES" if freeze else "ALLOW", "reasons": reasons or ["pass"], "kill_switch": ks, "forward_validation": fwd}


# 5) Auto daily report: human readable evidence log.
def auto_daily_report(symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    syms = symbols or ["NVDA", "AAPL", "TSLA", "QQQ", "SPY"]
    rows = []
    for s in syms:
        sig = latest_signal(s)
        val = {
            "data": multi_source_data_validation(s),
            "liquidity": liquidity_filter(s, intended_notional=10000),
            "governance": governance_layer({"trades_today": 0, "risk_per_trade_pct": 1, "daily_pnl_pct": 0}),
        }
        conf = confidence_score({"symbol": s, "signal": sig.get("signal", "HOLD"), "score": sig.get("score", 50), "price": sig.get("price", 0)}, val)
        rows.append({"symbol": s, "signal": sig, "confidence": conf.get("confidence_pct"), "decision": "TRADE_CANDIDATE" if conf.get("confidence_pct", 0) >= load_config()["config"]["min_confidence_pct"] else "WATCH"})
    fwd = forward_validation_dashboard()
    freeze = trade_freeze_mode()
    report = {"ok": True, "version": V39_VERSION, "generated_at": _now(), "symbols": rows, "forward_validation": fwd, "trade_freeze": freeze}
    _append_jsonl(DAILY_FILE, {"ts": _now(), "date": date.today().isoformat(), "version": V39_VERSION, "report_only": True, "report": report})
    return report


def v39_full_validation_report(symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    syms = symbols or ["NVDA", "AAPL", "TSLA", "QQQ", "SPY"]
    return {
        "ok": True,
        "version": V39_VERSION,
        "purpose": "Validation & Paper Broker Proof; proves readiness with recorded forward data, broker paper checks, governance and benchmark comparison.",
        "config": load_config(),
        "paper_broker": paper_broker_connection_check(),
        "edge_proof": edge_proof_report(syms),
        "trade_freeze": trade_freeze_mode(),
        "scenario_stress": scenario_stress_test([{"symbol": s, "qty": 1, "price": 100} for s in syms], 100000),
        "next_required_evidence": ["record at least 90 forward days", "paper broker order proof", "benchmark outperformance", "no failed freeze/gov gates"],
    }
