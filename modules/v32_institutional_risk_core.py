"""
V32 Institutional Risk & Backtest Core

Purpose:
- Convert raw signals into auditable, fund-style decisions.
- Add realistic backtest accounting: fees, slippage, stop-loss, take-profit,
  position sizing, max drawdown and walk-forward validation.
- Stay dependency-light: pure Python, no broker execution, no profit guarantees.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Any, Dict, Iterable, List, Optional, Tuple

V32_VERSION = "V32 Institutional Risk & Backtest Core"

V32_DEFAULT_EQUITY = float(os.getenv("V32_DEFAULT_EQUITY", "100000"))
V32_RISK_PER_TRADE = float(os.getenv("V32_RISK_PER_TRADE", "0.005"))  # 0.5% equity
V32_MAX_POSITION_PCT = float(os.getenv("V32_MAX_POSITION_PCT", "0.20"))
V32_MAX_PORTFOLIO_HEAT = float(os.getenv("V32_MAX_PORTFOLIO_HEAT", "0.03"))
V32_MIN_REWARD_RISK = float(os.getenv("V32_MIN_REWARD_RISK", "1.8"))
V32_MIN_CONFIDENCE = float(os.getenv("V32_MIN_CONFIDENCE", "72"))
V32_MAX_DAILY_LOSS_PCT = float(os.getenv("V32_MAX_DAILY_LOSS_PCT", "0.02"))
V32_DEFAULT_FEE_BPS = float(os.getenv("V32_DEFAULT_FEE_BPS", "2.0"))
V32_DEFAULT_SLIPPAGE_BPS = float(os.getenv("V32_DEFAULT_SLIPPAGE_BPS", "5.0"))


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


def _percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * pct
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return values[int(k)]
    return values[lo] * (hi - k) + values[hi] * (k - lo)


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


def _normalise_side(side: Any) -> str:
    s = str(side or "").upper().strip()
    if s in {"BUY", "LONG", "CALL"}:
        return "LONG"
    if s in {"SELL", "SHORT", "PUT"}:
        return "SHORT"
    return "FLAT"


def position_sizing(
    equity: float,
    entry: float,
    stop: float,
    risk_per_trade: float = V32_RISK_PER_TRADE,
    max_position_pct: float = V32_MAX_POSITION_PCT,
) -> Dict[str, Any]:
    """Return conservative position size based on stop distance and max exposure cap."""
    equity = safe_float(equity, V32_DEFAULT_EQUITY) or V32_DEFAULT_EQUITY
    entry = safe_float(entry)
    stop = safe_float(stop)
    risk_per_trade = max(0.0, min(safe_float(risk_per_trade, V32_RISK_PER_TRADE) or V32_RISK_PER_TRADE, 0.10))
    max_position_pct = max(0.0, min(safe_float(max_position_pct, V32_MAX_POSITION_PCT) or V32_MAX_POSITION_PCT, 1.0))

    if entry is None or stop is None or entry <= 0 or stop <= 0 or entry == stop:
        return {"ok": False, "error": "invalid_entry_or_stop", "shares": 0, "notional": 0.0, "risk_amount": 0.0}

    risk_amount = equity * risk_per_trade
    risk_per_share = abs(entry - stop)
    shares_by_risk = math.floor(risk_amount / risk_per_share)
    shares_by_exposure = math.floor((equity * max_position_pct) / entry)
    shares = max(0, min(shares_by_risk, shares_by_exposure))
    notional = shares * entry
    actual_risk = shares * risk_per_share
    return {
        "ok": shares > 0,
        "shares": shares,
        "notional": round(notional, 4),
        "risk_amount": round(actual_risk, 4),
        "risk_pct_equity": round(actual_risk / equity, 6) if equity else 0.0,
        "position_pct_equity": round(notional / equity, 6) if equity else 0.0,
        "risk_per_share": round(risk_per_share, 4),
        "capped_by": "exposure" if shares_by_exposure < shares_by_risk else "risk",
    }


def pretrade_risk_gate(signal: Dict[str, Any], portfolio: Optional[Dict[str, Any]] = None) -> Tuple[bool, Dict[str, Any]]:
    """Fund-style guardrail before a signal can become an order/alert."""
    portfolio = portfolio or {}
    side = _normalise_side(signal.get("side") or signal.get("signal"))
    entry = safe_float(signal.get("entry") or signal.get("price"))
    stop = safe_float(signal.get("stop") or signal.get("stop_loss"))
    target = safe_float(signal.get("target") or signal.get("take_profit"))
    confidence = safe_float(signal.get("confidence") or signal.get("score"), 0.0) or 0.0
    reward_risk = safe_float(signal.get("reward_risk") or signal.get("risk_reward") or signal.get("rr"))
    equity = safe_float(portfolio.get("equity"), V32_DEFAULT_EQUITY) or V32_DEFAULT_EQUITY
    open_heat = safe_float(portfolio.get("open_heat_pct"), 0.0) or 0.0
    daily_loss_pct = safe_float(portfolio.get("daily_loss_pct"), 0.0) or 0.0

    reasons: List[str] = []
    if side == "FLAT":
        reasons.append("invalid_side")
    if entry is None or entry <= 0:
        reasons.append("invalid_entry")
    if stop is None or stop <= 0:
        reasons.append("missing_stop_loss")
    if confidence < V32_MIN_CONFIDENCE:
        reasons.append("confidence_below_threshold")
    if daily_loss_pct <= -abs(V32_MAX_DAILY_LOSS_PCT):
        reasons.append("daily_loss_circuit_breaker")
    if open_heat >= V32_MAX_PORTFOLIO_HEAT:
        reasons.append("portfolio_heat_limit")

    if reward_risk is None and entry and stop and target:
        risk = abs(entry - stop)
        reward = abs(target - entry)
        reward_risk = reward / risk if risk > 0 else None
    if reward_risk is None or reward_risk < V32_MIN_REWARD_RISK:
        reasons.append("reward_risk_too_low")

    sizing = position_sizing(equity, entry or 0, stop or 0)
    if not sizing.get("ok"):
        reasons.append("position_size_zero")
    projected_heat = open_heat + float(sizing.get("risk_pct_equity") or 0.0)
    if projected_heat > V32_MAX_PORTFOLIO_HEAT:
        reasons.append("projected_heat_limit")

    ok = len(reasons) == 0
    return ok, {
        "ok": ok,
        "version": V32_VERSION,
        "decision": "ALLOW" if ok else "BLOCK",
        "reasons": reasons,
        "side": side,
        "confidence": confidence,
        "reward_risk": reward_risk,
        "sizing": sizing,
        "portfolio_heat_pct": round(open_heat, 6),
        "projected_heat_pct": round(projected_heat, 6),
    }


def backtest_signals(
    prices: Iterable[float],
    signals: Iterable[Any],
    initial_equity: float = V32_DEFAULT_EQUITY,
    fee_bps: float = V32_DEFAULT_FEE_BPS,
    slippage_bps: float = V32_DEFAULT_SLIPPAGE_BPS,
    stop_loss_pct: float = 0.03,
    take_profit_pct: float = 0.06,
    risk_per_trade: float = V32_RISK_PER_TRADE,
) -> Dict[str, Any]:
    """Simple next-bar execution backtest with one position at a time.

    signals accepts values: 1/BUY/LONG, -1/SELL/SHORT, 0/None.
    Exit occurs on opposite signal, stop-loss, take-profit, or final bar.
    """
    px = [safe_float(p) for p in prices]
    px = [p for p in px if p is not None and p > 0]
    sigs = list(signals)
    if len(px) < 3:
        return {"ok": False, "error": "not_enough_prices"}
    if len(sigs) < len(px):
        sigs = sigs + [0] * (len(px) - len(sigs))
    sigs = sigs[:len(px)]

    equity = safe_float(initial_equity, V32_DEFAULT_EQUITY) or V32_DEFAULT_EQUITY
    cash = equity
    position = 0
    entry_price = 0.0
    stop_price = 0.0
    target_price = 0.0
    shares = 0
    trades: List[Dict[str, Any]] = []
    equity_curve: List[float] = [equity]
    fee_rate = max(0.0, fee_bps) / 10000.0
    slip_rate = max(0.0, slippage_bps) / 10000.0

    def signal_to_dir(v: Any) -> int:
        s = str(v).upper().strip()
        if s in {"1", "BUY", "LONG", "CALL"}:
            return 1
        if s in {"-1", "SELL", "SHORT", "PUT"}:
            return -1
        return 0

    for i in range(1, len(px)):
        price = px[i]
        direction = signal_to_dir(sigs[i - 1])  # next-bar execution
        mark_equity = cash + (shares * price * position if position else 0.0)

        exit_reason = None
        if position:
            if position == 1:
                if price <= stop_price:
                    exit_reason = "stop_loss"
                elif price >= target_price:
                    exit_reason = "take_profit"
                elif direction == -1:
                    exit_reason = "opposite_signal"
            else:
                if price >= stop_price:
                    exit_reason = "stop_loss"
                elif price <= target_price:
                    exit_reason = "take_profit"
                elif direction == 1:
                    exit_reason = "opposite_signal"
            if i == len(px) - 1:
                exit_reason = exit_reason or "final_bar"

        if position and exit_reason:
            exit_price = price * (1 - slip_rate if position == 1 else 1 + slip_rate)
            gross = (exit_price - entry_price) * shares * position
            fees = (abs(exit_price * shares) + abs(entry_price * shares)) * fee_rate
            pnl = gross - fees
            cash += shares * exit_price * position + pnl - gross  # keeps cash accounting stable long/short-light
            # For this simplified model, reset cash to marked equity plus realised pnl.
            cash = equity_curve[-1] + pnl
            r_multiple = pnl / max(1e-9, abs(entry_price - stop_price) * shares)
            trades.append({
                "entry_index": i,
                "exit_index": i,
                "side": "LONG" if position == 1 else "SHORT",
                "entry": round(entry_price, 4),
                "exit": round(exit_price, 4),
                "shares": shares,
                "pnl": round(pnl, 4),
                "return_pct": round(pnl / max(1e-9, equity_curve[-1]), 6),
                "r_multiple": round(r_multiple, 4),
                "exit_reason": exit_reason,
            })
            position = 0
            shares = 0
            entry_price = stop_price = target_price = 0.0
            mark_equity = cash

        if not position and direction != 0:
            raw_entry = price * (1 + slip_rate if direction == 1 else 1 - slip_rate)
            raw_stop = raw_entry * (1 - stop_loss_pct if direction == 1 else 1 + stop_loss_pct)
            sizing = position_sizing(mark_equity, raw_entry, raw_stop, risk_per_trade=risk_per_trade)
            if sizing.get("ok"):
                position = direction
                shares = int(sizing["shares"])
                entry_price = raw_entry
                stop_price = raw_stop
                target_price = raw_entry * (1 + take_profit_pct if direction == 1 else 1 - take_profit_pct)
                cash = mark_equity - shares * raw_entry * direction
                mark_equity = cash + shares * price * direction

        if position:
            mark_equity = cash + shares * price * position
        else:
            mark_equity = cash
        equity_curve.append(mark_equity)

    closed = len(trades)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    pnl_values = [float(t["pnl"]) for t in trades]
    r_values = [float(t["r_multiple"]) for t in trades]
    final_equity = equity_curve[-1]
    total_return = final_equity / equity - 1.0 if equity else 0.0
    return {
        "ok": True,
        "version": V32_VERSION,
        "initial_equity": round(equity, 4),
        "final_equity": round(final_equity, 4),
        "total_return_pct": round(total_return * 100, 4),
        "max_drawdown_pct": round(_max_drawdown(equity_curve) * 100, 4),
        "trades": closed,
        "win_rate_pct": round((len(wins) / closed * 100) if closed else 0.0, 4),
        "avg_trade_pnl": round(mean(pnl_values), 4) if pnl_values else 0.0,
        "avg_r": round(mean(r_values), 4) if r_values else 0.0,
        "profit_factor": round(sum(t["pnl"] for t in wins) / abs(sum(t["pnl"] for t in losses)), 4) if losses else None,
        "p05_r": round(_percentile(r_values, 0.05), 4) if r_values else None,
        "p95_r": round(_percentile(r_values, 0.95), 4) if r_values else None,
        "equity_curve": [round(x, 4) for x in equity_curve],
        "trade_log": trades[-200:],
        "assumptions": {
            "fee_bps": fee_bps,
            "slippage_bps": slippage_bps,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            "risk_per_trade": risk_per_trade,
            "execution": "signal_on_bar_t_exec_next_bar",
        },
    }


def walk_forward_report(
    prices: Iterable[float],
    signals: Iterable[Any],
    folds: int = 4,
    **kwargs: Any,
) -> Dict[str, Any]:
    px = list(prices)
    sigs = list(signals)
    n = min(len(px), len(sigs))
    if n < 20:
        return {"ok": False, "error": "not_enough_data_for_walk_forward"}
    folds = max(2, min(int(folds or 4), 12))
    fold_size = n // folds
    results: List[Dict[str, Any]] = []
    for k in range(folds):
        start = k * fold_size
        end = n if k == folds - 1 else (k + 1) * fold_size
        if end - start < 5:
            continue
        r = backtest_signals(px[start:end], sigs[start:end], **kwargs)
        if r.get("ok"):
            results.append({
                "fold": k + 1,
                "start_index": start,
                "end_index": end - 1,
                "total_return_pct": r["total_return_pct"],
                "max_drawdown_pct": r["max_drawdown_pct"],
                "trades": r["trades"],
                "win_rate_pct": r["win_rate_pct"],
                "avg_r": r["avg_r"],
            })
    returns = [x["total_return_pct"] for x in results]
    dds = [x["max_drawdown_pct"] for x in results]
    pass_folds = [x for x in results if x["total_return_pct"] > 0 and x["max_drawdown_pct"] > -15]
    return {
        "ok": True,
        "version": V32_VERSION,
        "folds": results,
        "fold_count": len(results),
        "positive_fold_rate_pct": round(len([r for r in returns if r > 0]) / len(returns) * 100, 4) if returns else 0.0,
        "avg_return_pct": round(mean(returns), 4) if returns else 0.0,
        "worst_drawdown_pct": round(min(dds), 4) if dds else 0.0,
        "stability_status": "PASS" if results and len(pass_folds) / len(results) >= 0.70 else "WARN",
        "warning": "If walk-forward fails, the model is probably overfit even if the full backtest looks good.",
    }
