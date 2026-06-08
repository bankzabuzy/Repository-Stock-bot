from __future__ import annotations

import json
import math
import os
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from modules.v35_institutional_free_core import _safe_float, fetch_ohlcv, latest_signal, rank_signals, performance_report, backtest_many, walk_forward_many, monte_carlo_many
from modules.v36_institutional_free_core import (
    V36_VERSION, dynamic_stop_engine, meta_ai_filter, capital_allocation_engine,
    self_healing_monitor, execution_simulator, institutional_readiness_score,
    portfolio_heat, factor_exposure, alpha_decay_detector, v36_institutional_report
)

V37_VERSION = "V37_LIVE_SAFETY_BROKER_READY"
STATE_DIR = Path(os.getenv("STOCKBOT_STATE_DIR", "/tmp/stockbot_v37"))
STATE_DIR.mkdir(parents=True, exist_ok=True)
ORDERS_FILE = STATE_DIR / "orders.jsonl"
AUDIT_FILE = STATE_DIR / "audit_log.jsonl"
KILL_FILE = STATE_DIR / "kill_switch.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _read_jsonl(path: Path, limit: int = 500) -> List[Dict[str, Any]]:
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


def audit_log(event: str, payload: Dict[str, Any], level: str = "INFO") -> Dict[str, Any]:
    row = {"ts": _now(), "version": V37_VERSION, "level": level, "event": event, "payload": payload}
    _append_jsonl(AUDIT_FILE, row)
    return {"ok": True, "logged": row}


# ------------------------------------------------------------
# 1) Broker Adapter Layer: mock + optional Alpaca paper support
# ------------------------------------------------------------
class BrokerAdapter:
    name = "base"

    def account(self) -> Dict[str, Any]:
        raise NotImplementedError

    def submit_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    def get_order(self, order_id: str) -> Dict[str, Any]:
        raise NotImplementedError


class MockBrokerAdapter(BrokerAdapter):
    name = "mock_broker_free"

    def account(self) -> Dict[str, Any]:
        equity = float(os.getenv("V37_MOCK_EQUITY", "100000"))
        return {"ok": True, "broker": self.name, "paper": True, "equity": equity, "cash": equity, "currency": "USD"}

    def submit_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        oid = "MOCK-" + uuid.uuid4().hex[:12].upper()
        sim = execution_simulator({
            "symbol": order.get("symbol"), "side": order.get("side", "BUY"),
            "qty": order.get("qty", 0), "price": order.get("price", order.get("limit_price", 0) or 0)
        })
        status = "filled" if sim.get("filled_qty", 0) >= (_safe_float(order.get("qty"), 0) or 0) else "partially_filled"
        row = {"ok": True, "broker": self.name, "id": oid, "status": status, "paper": True,
               "submitted_order": order, "execution": sim, "created_at": _now()}
        _append_jsonl(ORDERS_FILE, row)
        audit_log("mock_order_submitted", row)
        return row

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        row = {"ok": True, "broker": self.name, "id": order_id, "status": "canceled", "paper": True, "updated_at": _now()}
        _append_jsonl(ORDERS_FILE, row)
        audit_log("mock_order_canceled", row)
        return row

    def get_order(self, order_id: str) -> Dict[str, Any]:
        for r in reversed(_read_jsonl(ORDERS_FILE, 2000)):
            if r.get("id") == order_id:
                return {"ok": True, "order": r}
        return {"ok": False, "error": "order_not_found", "id": order_id}


class AlpacaPaperAdapter(BrokerAdapter):
    name = "alpaca_paper"

    def __init__(self) -> None:
        self.key = os.getenv("ALPACA_API_KEY", "")
        self.secret = os.getenv("ALPACA_SECRET_KEY", "")
        self.base = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")

    def _headers(self) -> Dict[str, str]:
        return {"APCA-API-KEY-ID": self.key, "APCA-API-SECRET-KEY": self.secret, "Content-Type": "application/json"}

    def _ready(self) -> bool:
        return bool(self.key and self.secret)

    def account(self) -> Dict[str, Any]:
        if not self._ready():
            return {"ok": False, "broker": self.name, "error": "missing_alpaca_keys", "fallback": "mock_broker_free"}
        try:
            r = requests.get(f"{self.base}/v2/account", headers=self._headers(), timeout=10)
            return {"ok": r.ok, "broker": self.name, "status_code": r.status_code, "data": r.json()}
        except Exception as e:
            return {"ok": False, "broker": self.name, "error": str(e)}

    def submit_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        if not self._ready():
            return MockBrokerAdapter().submit_order({**order, "broker_fallback_reason": "missing_alpaca_keys"})
        payload = {
            "symbol": str(order.get("symbol", "")).upper(),
            "qty": str(order.get("qty", 0)),
            "side": str(order.get("side", "buy")).lower(),
            "type": str(order.get("type", "market")).lower(),
            "time_in_force": str(order.get("time_in_force", "day")).lower(),
        }
        if order.get("limit_price"):
            payload["limit_price"] = str(order.get("limit_price")); payload["type"] = "limit"
        try:
            r = requests.post(f"{self.base}/v2/orders", headers=self._headers(), json=payload, timeout=10)
            data = r.json() if r.text else {}
            row = {"ok": r.ok, "broker": self.name, "status_code": r.status_code, "data": data, "submitted_order": payload, "created_at": _now()}
            _append_jsonl(ORDERS_FILE, row); audit_log("alpaca_order_submitted", row, "INFO" if r.ok else "ERROR")
            return row
        except Exception as e:
            return {"ok": False, "broker": self.name, "error": str(e)}

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        if not self._ready():
            return MockBrokerAdapter().cancel_order(order_id)
        try:
            r = requests.delete(f"{self.base}/v2/orders/{order_id}", headers=self._headers(), timeout=10)
            row = {"ok": r.ok, "broker": self.name, "status_code": r.status_code, "id": order_id, "updated_at": _now()}
            _append_jsonl(ORDERS_FILE, row); audit_log("alpaca_order_canceled", row)
            return row
        except Exception as e:
            return {"ok": False, "broker": self.name, "error": str(e)}

    def get_order(self, order_id: str) -> Dict[str, Any]:
        if not self._ready():
            return MockBrokerAdapter().get_order(order_id)
        try:
            r = requests.get(f"{self.base}/v2/orders/{order_id}", headers=self._headers(), timeout=10)
            return {"ok": r.ok, "broker": self.name, "status_code": r.status_code, "data": r.json() if r.text else {}}
        except Exception as e:
            return {"ok": False, "broker": self.name, "error": str(e)}


def get_broker(name: Optional[str] = None) -> BrokerAdapter:
    broker = (name or os.getenv("V37_BROKER", "mock")).lower()
    if broker in {"alpaca", "alpaca_paper"}:
        return AlpacaPaperAdapter()
    return MockBrokerAdapter()


# ------------------------------------------------------------
# 2) OMS + 3) Kill Switch + 4) Capital Protection
# ------------------------------------------------------------
def kill_switch_status(today_pnl_pct: float = 0.0, consecutive_losses: int = 0,
                       max_daily_dd_pct: float = 5.0, max_consecutive_losses: int = 4) -> Dict[str, Any]:
    manual = {}
    if KILL_FILE.exists():
        try:
            manual = json.loads(KILL_FILE.read_text(encoding="utf-8"))
        except Exception:
            manual = {}
    reasons: List[str] = []
    active = bool(manual.get("active", False))
    if today_pnl_pct <= -abs(max_daily_dd_pct):
        active = True; reasons.append("daily_drawdown_limit_hit")
    if consecutive_losses >= max_consecutive_losses:
        active = True; reasons.append("consecutive_loss_limit_hit")
    if manual.get("active"):
        reasons.append("manual_kill_switch_active")
    return {"ok": True, "active": active, "decision": "BLOCK_ALL_NEW_ORDERS" if active else "ALLOW",
            "reasons": reasons or ["pass"], "manual": manual, "checked_at": _now()}


def set_kill_switch(active: bool, reason: str = "manual") -> Dict[str, Any]:
    row = {"active": bool(active), "reason": reason, "updated_at": _now()}
    KILL_FILE.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    audit_log("kill_switch_updated", row, "WARNING" if active else "INFO")
    return {"ok": True, **row}


def capital_protection_mode(performance: Optional[Dict[str, Any]] = None, base_risk_pct: float = 0.5) -> Dict[str, Any]:
    perf = performance or {}
    dd = _safe_float(perf.get("max_drawdown_pct"), 0) or 0
    pf = _safe_float(perf.get("profit_factor"), 1.0) or 1.0
    losses = int(_safe_float(perf.get("consecutive_losses"), 0) or 0)
    multiplier = 1.0
    reasons = []
    if dd <= -10: multiplier *= 0.5; reasons.append("drawdown_reduce_risk")
    if pf < 1.2: multiplier *= 0.7; reasons.append("profit_factor_weak")
    if losses >= 3: multiplier *= 0.5; reasons.append("loss_streak_reduce_risk")
    if dd <= -15 or losses >= 5:
        multiplier = 0.0; reasons.append("capital_protection_pause")
    return {"ok": True, "base_risk_pct": base_risk_pct, "risk_multiplier": round(multiplier, 3),
            "effective_risk_pct": round(base_risk_pct * multiplier, 4), "mode": "PAUSE" if multiplier == 0 else ("REDUCED" if multiplier < 1 else "NORMAL"),
            "reasons": reasons or ["pass"]}


def oms_submit_order(order: Dict[str, Any], broker_name: Optional[str] = None, dry_run: Optional[bool] = None) -> Dict[str, Any]:
    if dry_run is None:
        dry_run = os.getenv("V37_DRY_RUN", "true").lower() == "true"
    kill = kill_switch_status(float(order.get("today_pnl_pct", 0) or 0), int(order.get("consecutive_losses", 0) or 0))
    if kill.get("active"):
        audit_log("order_blocked_by_kill_switch", {"order": order, "kill": kill}, "WARNING")
        return {"ok": False, "status": "blocked", "reason": "kill_switch_active", "kill_switch": kill}
    required = ["symbol", "side", "qty"]
    missing = [k for k in required if not order.get(k)]
    if missing:
        return {"ok": False, "status": "rejected", "reason": "missing_fields", "missing": missing}
    if (_safe_float(order.get("qty"), 0) or 0) <= 0:
        return {"ok": False, "status": "rejected", "reason": "qty_must_be_positive"}
    order = {**order, "client_order_id": order.get("client_order_id") or "V37-" + uuid.uuid4().hex[:12].upper(), "created_at": _now()}
    if dry_run:
        sim = execution_simulator(order)
        row = {"ok": True, "status": "dry_run_simulated", "paper": True, "order": order, "execution": sim}
        _append_jsonl(ORDERS_FILE, row); audit_log("dry_run_order_simulated", row)
        return row
    broker = get_broker(broker_name)
    return broker.submit_order(order)


def oms_cancel_order(order_id: str, broker_name: Optional[str] = None) -> Dict[str, Any]:
    return get_broker(broker_name).cancel_order(order_id)


def oms_order_history(limit: int = 100) -> Dict[str, Any]:
    return {"ok": True, "version": V37_VERSION, "rows": _read_jsonl(ORDERS_FILE, limit)}


# ------------------------------------------------------------
# 5) News/Event Risk, 6) Slippage, 7) Drift, 8) Audit, 9) Health, 10) Recovery
# ------------------------------------------------------------
def news_event_risk_filter(symbol: str = "SPY", dt: Optional[str] = None) -> Dict[str, Any]:
    day = dt or date.today().isoformat()
    # Free/offline-safe defaults. Users can add dates through V37_EVENT_DATES=YYYY-MM-DD:FOMC,YYYY-MM-DD:CPI
    events = {}
    for item in os.getenv("V37_EVENT_DATES", "").split(','):
        if ':' in item:
            d, label = item.split(':', 1); events.setdefault(d.strip(), []).append(label.strip())
    labels = events.get(day, [])
    symbol = symbol.upper()
    if symbol in {"SPY", "QQQ", "DIA", "IWM", "GC=F", "GOLD"} and labels:
        decision = "BLOCK_NEW_TRADES"
    elif labels:
        decision = "REDUCE_SIZE"
    else:
        decision = "ALLOW"
    return {"ok": True, "symbol": symbol, "date": day, "decision": decision, "events": labels or [],
            "note": "Offline free calendar. Add events via V37_EVENT_DATES env for CPI/FOMC/NFP/earnings."}


def live_slippage_monitor(expected_price: float, actual_price: float, side: str = "BUY", max_slippage_bps: float = 35.0) -> Dict[str, Any]:
    expected = _safe_float(expected_price, 0) or 0
    actual = _safe_float(actual_price, 0) or 0
    if expected <= 0 or actual <= 0:
        return {"ok": False, "error": "invalid_price"}
    raw = (actual / expected - 1.0) * 10000.0
    bps = raw if str(side).upper() == "BUY" else -raw
    status = "OK" if bps <= max_slippage_bps else "HIGH_SLIPPAGE"
    return {"ok": True, "side": side.upper(), "expected_price": expected, "actual_price": actual,
            "slippage_bps": round(bps, 2), "max_slippage_bps": max_slippage_bps, "status": status,
            "decision": "ALLOW" if status == "OK" else "PAUSE_OR_REDUCE_EXECUTION"}


def model_drift_detector(current_metrics: Dict[str, Any], baseline_metrics: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    base = baseline_metrics or {"sharpe": 1.5, "profit_factor": 1.5, "win_rate_pct": 50, "max_drawdown_pct": -15}
    cur_sh = _safe_float(current_metrics.get("sharpe"), 0) or 0
    base_sh = _safe_float(base.get("sharpe"), 1.5) or 1.5
    cur_pf = _safe_float(current_metrics.get("profit_factor"), 0) or 0
    base_pf = _safe_float(base.get("profit_factor"), 1.5) or 1.5
    cur_wr = _safe_float(current_metrics.get("win_rate_pct"), 0) or 0
    base_wr = _safe_float(base.get("win_rate_pct"), 50) or 50
    drift_score = 0
    reasons = []
    if cur_sh < base_sh * 0.7: drift_score += 35; reasons.append("sharpe_drift")
    if cur_pf < base_pf * 0.8: drift_score += 30; reasons.append("profit_factor_drift")
    if cur_wr < base_wr - 8: drift_score += 20; reasons.append("win_rate_drift")
    if (_safe_float(current_metrics.get("max_drawdown_pct"), 0) or 0) < (_safe_float(base.get("max_drawdown_pct"), -15) or -15):
        drift_score += 15; reasons.append("drawdown_worse_than_baseline")
    status = "DRIFT_RISK" if drift_score >= 50 else ("WATCH" if drift_score >= 25 else "STABLE")
    return {"ok": True, "drift_score": min(100, drift_score), "status": status, "reasons": reasons or ["pass"],
            "decision": "BLOCK_OR_RETRAIN" if status == "DRIFT_RISK" else ("REDUCE_SIZE" if status == "WATCH" else "ALLOW")}


def health_check_dashboard(symbols: List[str], period: str = "6mo", interval: str = "1d") -> Dict[str, Any]:
    healing = self_healing_monitor(symbols, period, interval)
    kill = kill_switch_status()
    broker = get_broker().account()
    orders = oms_order_history(20)
    problems = []
    if healing.get("status") != "OK": problems.append("data_or_pipeline_degraded")
    if kill.get("active"): problems.append("kill_switch_active")
    if not broker.get("ok"): problems.append("broker_not_ready")
    status = "OK" if not problems else "DEGRADED_SAFE_MODE"
    return {"ok": True, "version": V37_VERSION, "status": status, "problems": problems or ["none"],
            "self_healing": healing, "kill_switch": kill, "broker": broker, "recent_orders": orders.get("rows", [])}


def recovery_manager(symbols: List[str], force_safe_mode: bool = False) -> Dict[str, Any]:
    health = health_check_dashboard(symbols)
    actions = []
    if force_safe_mode or health.get("status") != "OK":
        set_kill_switch(True, "recovery_manager_safe_mode")
        actions.append("kill_switch_enabled")
    if any("broker" in p for p in health.get("problems", [])):
        actions.append("fallback_to_mock_broker")
    if any("data" in p for p in health.get("problems", [])):
        actions.append("skip_new_signals_until_data_quality_recovers")
    audit_log("recovery_manager_run", {"health_status": health.get("status"), "actions": actions})
    return {"ok": True, "version": V37_VERSION, "health_status": health.get("status"), "actions": actions or ["none"], "health": health}


# ------------------------------------------------------------
# Integrated Live Readiness and Pipeline
# ------------------------------------------------------------
def live_readiness_score(symbols: List[str], period: str = "1y", interval: str = "1d", account_equity: float = 100000.0) -> Dict[str, Any]:
    bt = backtest_many(symbols, "2y", interval)
    wf = walk_forward_many(symbols, "5y", interval)
    mc = monte_carlo_many(symbols, "2y", interval, 1000)
    base = institutional_readiness_score(bt, wf, mc)
    health = health_check_dashboard(symbols, "6mo", interval)
    decay = alpha_decay_detector(bt.get("rows", []))
    points = float(base.get("readiness_score_pct", 0))
    if health.get("status") == "OK": points += 8
    if not any(r.get("status") == "DECAY_RISK" for r in decay.get("rows", [])): points += 7
    if get_broker().account().get("ok"): points += 5
    score = max(0, min(100, round(points, 2)))
    decision = "PAPER_BROKER_READY" if score >= 85 else ("PAPER_RESEARCH_ONLY" if score >= 70 else "NOT_READY")
    return {"ok": True, "version": V37_VERSION, "live_safety_score_pct": score, "decision": decision,
            "base_readiness": base, "health": health, "alpha_decay": decay,
            "note": "Broker-ready means paper/dry-run ready unless real broker keys and explicit dry_run=false are configured."}


def v37_pre_trade_pipeline(symbol: str, account_equity: float = 100000.0, broker: str = "mock", dry_run: bool = True) -> Dict[str, Any]:
    df = fetch_ohlcv(symbol, "1y", "1d")
    sig = latest_signal(symbol, df)
    stop = dynamic_stop_engine(symbol, df=df, entry_price=sig.get("price"))
    signal_for_meta = {**sig, "stop_loss": stop.get("recommended_stop", sig.get("stop_loss"))}
    bt = backtest_many([symbol], "2y", "1d").get("rows", [{}])[0]
    wf = walk_forward_many([symbol], "5y", "1d").get("rows", [{}])[0]
    mc = monte_carlo_many([symbol], "2y", "1d", 1000).get("rows", [{}])[0]
    meta = meta_ai_filter(signal_for_meta, bt, wf, mc)
    event = news_event_risk_filter(symbol)
    drift = model_drift_detector(bt)
    protect = capital_protection_mode(bt)
    kill = kill_switch_status()
    allowed = sig.get("signal") == "BUY" and meta.get("decision") == "ALLOW" and event.get("decision") != "BLOCK_NEW_TRADES" and drift.get("decision") != "BLOCK_OR_RETRAIN" and protect.get("mode") != "PAUSE" and not kill.get("active")
    qty = 0.0
    if allowed:
        risk_cash = account_equity * (protect.get("effective_risk_pct", 0.0) / 100.0)
        price = _safe_float(sig.get("price"), 0) or 0
        st = _safe_float(stop.get("recommended_stop"), sig.get("stop_loss")) or 0
        qty = max(0.0, risk_cash / max(price - st, 1e-9)) if price > 0 and st > 0 and st < price else 0.0
    order = None
    if allowed and qty > 0:
        order = oms_submit_order({"symbol": symbol.upper(), "side": "BUY", "qty": round(qty, 6), "price": sig.get("price"), "type": "market"}, broker, dry_run)
    result = {"ok": True, "version": V37_VERSION, "symbol": symbol.upper(), "allowed": allowed,
              "signal": sig, "dynamic_stop": stop, "meta_ai": meta, "event_filter": event,
              "model_drift": drift, "capital_protection": protect, "kill_switch": kill,
              "order_result": order, "decision": "ORDER_SIMULATED_OR_SENT" if order else ("ALLOW_BUT_ZERO_QTY" if allowed else "BLOCK")}
    audit_log("pre_trade_pipeline", result, "INFO" if allowed else "WARNING")
    return result


def v37_live_safety_report(symbols: List[str], account_equity: float = 100000.0, period: str = "1y", interval: str = "1d") -> Dict[str, Any]:
    v36 = v36_institutional_report(symbols, period, interval, account_equity)
    readiness = live_readiness_score(symbols, period, interval, account_equity)
    health = health_check_dashboard(symbols, "6mo", interval)
    allocation = capital_allocation_engine(symbols, account_equity, period=period, interval=interval)
    events = [news_event_risk_filter(s) for s in symbols]
    return {"ok": True, "version": V37_VERSION, "mode": "free_100_percent_live_safety_paper_broker_ready",
            "v36_base": {"version": V36_VERSION, "ok": v36.get("ok"), "readiness": v36.get("readiness")},
            "live_readiness": readiness, "health": health, "capital_allocation": allocation,
            "event_risk": events, "recent_orders": oms_order_history(25),
            "safety_notice": "Default is dry-run/mock broker. Real orders require broker keys, V37_DRY_RUN=false, and your own compliance/risk approval."}
