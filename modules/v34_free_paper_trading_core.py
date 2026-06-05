"""
V34 Free Paper Trading + Broker + Kill Switch + Monitoring Core

Purpose:
- Free 100% execution simulation for paper trading.
- Broker abstraction with a deterministic mock/local broker.
- Production-style kill switch before every order.
- Monitoring report for equity, positions, trades, and risk.

This is intentionally dependency-light. It does not connect to a paid broker and
it does not guarantee profit. It is the safety layer that should run before any
real broker integration.
"""
from __future__ import annotations

import csv
import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from modules.v32_institutional_risk_core import safe_float, _max_drawdown
except Exception:  # pragma: no cover
    def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
        try:
            if value is None or value == "":
                return default
            x = float(value)
            if math.isnan(x) or math.isinf(x):
                return default
            return x
        except Exception:
            return default

    def _max_drawdown(equity_curve: List[float]) -> float:
        if not equity_curve:
            return 0.0
        peak = equity_curve[0]
        worst = 0.0
        for value in equity_curve:
            peak = max(peak, value)
            if peak > 0:
                worst = min(worst, value / peak - 1.0)
        return worst

try:
    from modules.v33_institutional_portfolio_core import drawdown_control
except Exception:  # pragma: no cover
    drawdown_control = None

V34_VERSION = "V34 Free Paper Trading + Mock Broker + Kill Switch + Monitoring"


BUY_WORDS = {"BUY", "LONG", "CALL", "ENTRY", "ENTER", "1", 1, True}
SELL_WORDS = {"SELL", "EXIT", "CLOSE", "FLAT", "0", -1, 0, False}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_signal(signal: Any) -> str:
    """Return BUY, SELL, or HOLD from common signal formats."""
    if isinstance(signal, str):
        s = signal.strip().upper()
        if s in BUY_WORDS:
            return "BUY"
        if s in SELL_WORDS:
            return "SELL"
        return "HOLD"
    if signal in BUY_WORDS:
        return "BUY"
    if signal in SELL_WORDS:
        return "SELL"
    return "HOLD"


def clean_price_series(values: Iterable[Any]) -> List[float]:
    out: List[float] = []
    for value in values or []:
        x = safe_float(value)
        if x is not None and x > 0:
            out.append(float(x))
    return out


def pct_to_decimal(value: Any, default: float = 0.0) -> float:
    x = safe_float(value, default)
    if x is None:
        return default
    return x / 100.0 if abs(x) > 1 else x


def compute_equity(cash: float, positions: Dict[str, float], last_prices: Dict[str, float]) -> float:
    equity = cash
    for symbol, qty in positions.items():
        price = safe_float(last_prices.get(symbol), 0.0) or 0.0
        equity += qty * price
    return round(equity, 6)


@dataclass
class MockBrokerState:
    cash: float = 100000.0
    positions: Dict[str, float] = field(default_factory=dict)
    avg_cost: Dict[str, float] = field(default_factory=dict)
    realized_pnl: float = 0.0
    trades: List[Dict[str, Any]] = field(default_factory=list)
    last_prices: Dict[str, float] = field(default_factory=dict)
    blocked: bool = False
    block_reason: str = ""


class MockBroker:
    """Free local broker simulation.

    It supports market orders only and applies fee/slippage assumptions. This is
    good for paper trading discipline, not for real execution quality.
    """

    def __init__(self, initial_cash: float = 100000.0, fee_bps: float = 1.0, slippage_bps: float = 2.0):
        self.state = MockBrokerState(cash=float(safe_float(initial_cash, 100000.0) or 100000.0))
        self.fee_bps = max(0.0, float(safe_float(fee_bps, 1.0) or 0.0))
        self.slippage_bps = max(0.0, float(safe_float(slippage_bps, 2.0) or 0.0))

    def update_price(self, symbol: str, price: Any) -> None:
        px = safe_float(price)
        if px is not None and px > 0:
            self.state.last_prices[str(symbol).upper()] = float(px)

    def snapshot(self) -> Dict[str, Any]:
        equity = compute_equity(self.state.cash, self.state.positions, self.state.last_prices)
        return {
            "cash": round(self.state.cash, 6),
            "equity": equity,
            "positions": {k: round(v, 8) for k, v in sorted(self.state.positions.items()) if abs(v) > 1e-10},
            "avg_cost": {k: round(v, 6) for k, v in sorted(self.state.avg_cost.items()) if k in self.state.positions},
            "last_prices": dict(sorted(self.state.last_prices.items())),
            "realized_pnl": round(self.state.realized_pnl, 6),
            "trade_count": len(self.state.trades),
            "blocked": self.state.blocked,
            "block_reason": self.state.block_reason,
        }

    def block(self, reason: str) -> None:
        self.state.blocked = True
        self.state.block_reason = reason or "blocked"

    def unblock(self) -> None:
        self.state.blocked = False
        self.state.block_reason = ""

    def place_order(self, symbol: str, side: str, quantity: Any = None, notional: Any = None, price: Any = None, timestamp: str = "") -> Dict[str, Any]:
        symbol = str(symbol).upper().strip()
        side = str(side).upper().strip()
        px = safe_float(price, self.state.last_prices.get(symbol))
        qty = safe_float(quantity)
        notional_value = safe_float(notional)
        if not symbol:
            return {"ok": False, "error": "missing_symbol"}
        if side not in {"BUY", "SELL"}:
            return {"ok": False, "error": "invalid_side"}
        if self.state.blocked:
            return {"ok": False, "error": "broker_blocked", "reason": self.state.block_reason}
        if px is None or px <= 0:
            return {"ok": False, "error": "invalid_price"}

        slip = self.slippage_bps / 10000.0
        exec_price = px * (1 + slip if side == "BUY" else 1 - slip)
        if qty is None:
            if notional_value is None or notional_value <= 0:
                return {"ok": False, "error": "missing_quantity_or_notional"}
            qty = notional_value / exec_price
        qty = float(qty)
        if qty <= 0:
            return {"ok": False, "error": "invalid_quantity"}

        gross = exec_price * qty
        fee = gross * self.fee_bps / 10000.0
        if side == "BUY":
            total_cost = gross + fee
            if total_cost > self.state.cash + 1e-8:
                return {"ok": False, "error": "insufficient_cash", "required": round(total_cost, 6), "cash": round(self.state.cash, 6)}
            old_qty = self.state.positions.get(symbol, 0.0)
            old_cost = self.state.avg_cost.get(symbol, exec_price)
            new_qty = old_qty + qty
            new_avg = ((old_qty * old_cost) + gross) / new_qty if new_qty > 0 else 0.0
            self.state.cash -= total_cost
            self.state.positions[symbol] = new_qty
            self.state.avg_cost[symbol] = new_avg
            realized = 0.0
        else:
            held = self.state.positions.get(symbol, 0.0)
            if qty > held + 1e-8:
                return {"ok": False, "error": "insufficient_position", "requested": round(qty, 8), "held": round(held, 8)}
            avg = self.state.avg_cost.get(symbol, exec_price)
            proceeds = gross - fee
            realized = (exec_price - avg) * qty - fee
            self.state.cash += proceeds
            remaining = held - qty
            if remaining <= 1e-8:
                self.state.positions.pop(symbol, None)
                self.state.avg_cost.pop(symbol, None)
            else:
                self.state.positions[symbol] = remaining
            self.state.realized_pnl += realized

        self.update_price(symbol, px)
        equity = compute_equity(self.state.cash, self.state.positions, self.state.last_prices)
        trade = {
            "timestamp": timestamp or utc_now_iso(),
            "symbol": symbol,
            "side": side,
            "quantity": round(qty, 8),
            "price": round(exec_price, 6),
            "raw_price": round(px, 6),
            "gross": round(gross, 6),
            "fee": round(fee, 6),
            "realized_pnl": round(realized, 6),
            "cash_after": round(self.state.cash, 6),
            "equity_after": equity,
        }
        self.state.trades.append(trade)
        return {"ok": True, "trade": trade, "snapshot": self.snapshot()}


def evaluate_kill_switch(
    equity_curve: Iterable[Any],
    daily_loss_pct: float = 0.0,
    max_drawdown_limit_pct: float = -12.0,
    warning_drawdown_pct: float = -7.0,
    hard_daily_loss_pct: float = -2.0,
    consecutive_loss_limit: int = 4,
    realized_pnls: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    curve = [safe_float(x) for x in equity_curve or []]
    curve = [float(x) for x in curve if x is not None and x > 0]
    if len(curve) < 2:
        return {"ok": False, "action": "ALLOW", "risk_multiplier": 1.0, "error": "not_enough_equity_curve"}

    if drawdown_control is not None:
        dd = drawdown_control(curve, daily_loss_pct, max_drawdown_limit_pct, warning_drawdown_pct, hard_daily_loss_pct)
    else:  # pragma: no cover
        max_dd = _max_drawdown(curve)
        dd = {"ok": True, "action": "ALLOW", "risk_multiplier": 1.0, "max_drawdown_pct": max_dd * 100, "reasons": []}

    reasons = list(dd.get("reasons") or [])
    action = dd.get("action", "ALLOW")
    multiplier = safe_float(dd.get("risk_multiplier"), 1.0) or 0.0

    pnls = [safe_float(x, 0.0) or 0.0 for x in realized_pnls or []]
    loss_streak = 0
    for pnl in reversed(pnls):
        if pnl < 0:
            loss_streak += 1
        elif pnl > 0:
            break
    if consecutive_loss_limit > 0 and loss_streak >= consecutive_loss_limit:
        action = "BLOCK_NEW_TRADES"
        multiplier = 0.0
        reasons.append("consecutive_loss_limit_breached")

    return {
        "ok": True,
        "version": V34_VERSION,
        "action": action,
        "risk_multiplier": round(max(0.0, min(multiplier, 1.0)), 4),
        "kill_active": action == "BLOCK_NEW_TRADES",
        "loss_streak": loss_streak,
        "reasons": reasons,
        "drawdown_state": dd,
    }


def paper_trade_from_signals(
    prices_by_symbol: Dict[str, Iterable[Any]],
    signals_by_symbol: Dict[str, Iterable[Any]],
    initial_cash: float = 100000.0,
    allocation_weights: Optional[Dict[str, float]] = None,
    fee_bps: float = 1.0,
    slippage_bps: float = 2.0,
    max_position_weight: float = 0.25,
    min_cash_weight: float = 0.05,
    max_drawdown_limit_pct: float = -12.0,
    warning_drawdown_pct: float = -7.0,
    hard_daily_loss_pct: float = -2.0,
) -> Dict[str, Any]:
    """Run free local paper trading across aligned price/signal series."""
    symbols = sorted([str(s).upper() for s in (prices_by_symbol or {}).keys()])
    if not symbols:
        return {"ok": False, "error": "missing_prices"}

    prices = {s: clean_price_series(prices_by_symbol.get(s, [])) for s in symbols}
    signals = {s: list((signals_by_symbol or {}).get(s, [])) for s in symbols}
    n = min([len(prices[s]) for s in symbols] + [len(signals.get(s, [])) for s in symbols if signals.get(s)])
    if n < 2:
        return {"ok": False, "error": "not_enough_aligned_data"}

    broker = MockBroker(initial_cash=initial_cash, fee_bps=fee_bps, slippage_bps=slippage_bps)
    equity_curve: List[float] = []
    daily_returns: List[float] = []
    blocked_orders: List[Dict[str, Any]] = []

    weights = {str(k).upper(): max(0.0, pct_to_decimal(v, 0.0)) for k, v in (allocation_weights or {}).items()}
    if not weights:
        equal = min(max_position_weight, max(0.0, (1.0 - min_cash_weight) / max(len(symbols), 1)))
        weights = {s: equal for s in symbols}

    max_position_weight = max(0.01, min(pct_to_decimal(max_position_weight, 0.25), 1.0))
    min_cash_weight = max(0.0, min(pct_to_decimal(min_cash_weight, 0.05), 0.95))

    for i in range(n):
        for s in symbols:
            broker.update_price(s, prices[s][i])
        snapshot_before = broker.snapshot()
        equity_before = snapshot_before["equity"]
        if equity_curve:
            daily_ret = equity_before / equity_curve[-1] - 1.0 if equity_curve[-1] > 0 else 0.0
        else:
            daily_ret = 0.0
        daily_returns.append(daily_ret)
        realized_pnls = [t.get("realized_pnl", 0.0) for t in broker.state.trades if t.get("side") == "SELL"]
        kill = evaluate_kill_switch(
            equity_curve + [equity_before],
            daily_loss_pct=daily_ret,
            max_drawdown_limit_pct=max_drawdown_limit_pct,
            warning_drawdown_pct=warning_drawdown_pct,
            hard_daily_loss_pct=hard_daily_loss_pct,
            realized_pnls=realized_pnls,
        ) if equity_curve else {"ok": True, "action": "ALLOW", "risk_multiplier": 1.0, "kill_active": False, "reasons": []}
        if kill.get("kill_active"):
            broker.block(",".join(kill.get("reasons") or ["kill_switch_active"]))
        else:
            broker.unblock()

        for s in symbols:
            sig = normalize_signal(signals.get(s, ["HOLD"] * n)[i] if i < len(signals.get(s, [])) else "HOLD")
            price = prices[s][i]
            held_qty = broker.state.positions.get(s, 0.0)
            if sig == "BUY" and held_qty <= 1e-10:
                target_weight = min(weights.get(s, 0.0), max_position_weight)
                available_equity = broker.snapshot()["equity"]
                max_cash_to_use = max(0.0, broker.state.cash - available_equity * min_cash_weight)
                notional = min(available_equity * target_weight * (safe_float(kill.get("risk_multiplier"), 1.0) or 0.0), max_cash_to_use)
                if notional > 0:
                    result = broker.place_order(s, "BUY", notional=notional, price=price, timestamp=f"bar_{i}")
                    if not result.get("ok"):
                        blocked_orders.append({"bar": i, "symbol": s, "side": "BUY", "error": result})
            elif sig == "SELL" and held_qty > 1e-10:
                result = broker.place_order(s, "SELL", quantity=held_qty, price=price, timestamp=f"bar_{i}")
                if not result.get("ok"):
                    blocked_orders.append({"bar": i, "symbol": s, "side": "SELL", "error": result})

        equity_curve.append(broker.snapshot()["equity"])

    report = monitoring_report(broker.snapshot(), equity_curve, broker.state.trades, blocked_orders=blocked_orders)
    return {
        "ok": True,
        "version": V34_VERSION,
        "initial_cash": round(float(initial_cash), 6),
        "final_snapshot": broker.snapshot(),
        "equity_curve": equity_curve,
        "trades": broker.state.trades,
        "blocked_orders": blocked_orders,
        "monitoring": report,
    }


def trade_statistics(trades: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    sells = [t for t in trades or [] if str(t.get("side", "")).upper() == "SELL"]
    pnls = [safe_float(t.get("realized_pnl"), 0.0) or 0.0 for t in sells]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    return {
        "closed_trades": len(sells),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate_pct": round(len(wins) / len(pnls) * 100.0, 4) if pnls else 0.0,
        "gross_profit": round(gross_profit, 6),
        "gross_loss": round(gross_loss, 6),
        "net_realized_pnl": round(sum(pnls), 6),
        "profit_factor": round(profit_factor, 6),
    }


def monitoring_report(
    broker_snapshot: Dict[str, Any],
    equity_curve: Iterable[Any],
    trades: Iterable[Dict[str, Any]],
    blocked_orders: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    curve = [safe_float(x) for x in equity_curve or []]
    curve = [float(x) for x in curve if x is not None and x > 0]
    initial = curve[0] if curve else safe_float(broker_snapshot.get("equity"), 0.0) or 0.0
    final = curve[-1] if curve else initial
    total_return = final / initial - 1.0 if initial > 0 else 0.0
    max_dd = _max_drawdown(curve) if curve else 0.0
    positions = broker_snapshot.get("positions") or {}
    equity = safe_float(broker_snapshot.get("equity"), final) or final
    exposure = 0.0
    for symbol, qty in positions.items():
        px = safe_float((broker_snapshot.get("last_prices") or {}).get(symbol), 0.0) or 0.0
        exposure += abs((safe_float(qty, 0.0) or 0.0) * px)
    exposure_weight = exposure / equity if equity > 0 else 0.0
    stats = trade_statistics(trades)
    alerts: List[str] = []
    if max_dd <= -0.12:
        alerts.append("MAX_DRAWDOWN_OVER_12_PERCENT")
    if exposure_weight > 0.95:
        alerts.append("EXPOSURE_TOO_HIGH")
    if broker_snapshot.get("blocked"):
        alerts.append("BROKER_BLOCKED")
    if len(list(blocked_orders or [])) > 0:
        alerts.append("ORDERS_BLOCKED_OR_REJECTED")

    return {
        "ok": True,
        "version": V34_VERSION,
        "timestamp_utc": utc_now_iso(),
        "equity": round(equity, 6),
        "cash": round(safe_float(broker_snapshot.get("cash"), 0.0) or 0.0, 6),
        "total_return_pct": round(total_return * 100.0, 4),
        "max_drawdown_pct": round(max_dd * 100.0, 4),
        "exposure_weight_pct": round(exposure_weight * 100.0, 4),
        "open_positions": positions,
        "trade_stats": stats,
        "alerts": alerts,
        "status": "HALTED" if broker_snapshot.get("blocked") else "RUNNING",
    }


def save_trades_csv(trades: Iterable[Dict[str, Any]], path: str) -> Dict[str, Any]:
    rows = list(trades or [])
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fieldnames = ["timestamp", "symbol", "side", "quantity", "price", "raw_price", "gross", "fee", "realized_pnl", "cash_after", "equity_after"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    return {"ok": True, "path": path, "rows": len(rows)}


def save_monitoring_json(report: Dict[str, Any], path: str) -> Dict[str, Any]:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return {"ok": True, "path": path}


def v34_decision_pack(payload: Dict[str, Any]) -> Dict[str, Any]:
    prices = payload.get("prices_by_symbol") or payload.get("prices") or {}
    signals = payload.get("signals_by_symbol") or payload.get("signals") or {}
    result = paper_trade_from_signals(
        prices_by_symbol=prices,
        signals_by_symbol=signals,
        initial_cash=payload.get("initial_cash", payload.get("total_equity", 100000)),
        allocation_weights=payload.get("allocation_weights") or payload.get("weights") or None,
        fee_bps=payload.get("fee_bps", 1.0),
        slippage_bps=payload.get("slippage_bps", 2.0),
        max_position_weight=payload.get("max_position_weight", 0.25),
        min_cash_weight=payload.get("min_cash_weight", 0.05),
        max_drawdown_limit_pct=payload.get("max_drawdown_limit_pct", -12.0),
        warning_drawdown_pct=payload.get("warning_drawdown_pct", -7.0),
        hard_daily_loss_pct=payload.get("hard_daily_loss_pct", -2.0),
    )
    if not result.get("ok"):
        return result
    return {
        "ok": True,
        "version": V34_VERSION,
        "paper_trading": result,
        "monitoring": result.get("monitoring"),
        "next_step": "Use this in paper mode for 30-90 trading days before any real broker execution.",
    }
