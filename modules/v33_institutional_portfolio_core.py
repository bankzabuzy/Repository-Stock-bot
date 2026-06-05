"""
V33 Institutional Portfolio Core

Adds the missing fund-style layer on top of single-name signals:
- Relative Strength ranking versus a benchmark.
- Portfolio allocation with volatility/risk adjustment and hard caps.
- Drawdown control / kill-switch logic.
- Walk-forward validation for allocation stability.

This module is intentionally dependency-light and deterministic so it can run in
free hosting environments and in CI. It is a research/risk engine, not a broker
execution engine and it does not guarantee profit.
"""
from __future__ import annotations

import math
from statistics import mean, pstdev
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:  # reuse V32 utilities when available
    from modules.v32_institutional_risk_core import backtest_signals, safe_float, _max_drawdown
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
            worst = min(worst, value / peak - 1.0) if peak > 0 else worst
        return worst

    def backtest_signals(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        return {"ok": False, "error": "v32_backtest_unavailable"}

V33_VERSION = "V33 Relative Strength + Portfolio Allocation + Drawdown Control + Walk-Forward"


def _clean_prices(values: Iterable[Any]) -> List[float]:
    out: List[float] = []
    for v in values or []:
        x = safe_float(v)
        if x is not None and x > 0:
            out.append(float(x))
    return out


def _simple_return(prices: List[float], lookback: int) -> Optional[float]:
    if len(prices) < max(2, lookback + 1):
        return None
    start = prices[-lookback - 1]
    end = prices[-1]
    return end / start - 1.0 if start > 0 else None


def _returns(prices: List[float]) -> List[float]:
    return [prices[i] / prices[i - 1] - 1.0 for i in range(1, len(prices)) if prices[i - 1] > 0]


def _annual_vol(prices: List[float]) -> Optional[float]:
    r = _returns(prices)
    if len(r) < 2:
        return None
    return pstdev(r) * math.sqrt(252)


def _rank_percentile(items: List[Dict[str, Any]], key: str) -> None:
    valid = [x for x in items if safe_float(x.get(key)) is not None]
    valid.sort(key=lambda x: float(x[key]), reverse=True)
    n = len(valid)
    for i, row in enumerate(valid):
        row[f"{key}_rank"] = i + 1
        row[f"{key}_percentile"] = round((n - i) / n * 100.0, 4) if n else 0.0


def relative_strength_ranking(
    assets: Dict[str, Iterable[Any]],
    benchmark: Iterable[Any],
    lookbacks: Iterable[int] = (20, 60, 120),
) -> Dict[str, Any]:
    """Rank assets by excess return versus benchmark across multiple lookbacks.

    Score interpretation:
    - >70: asset is leading its benchmark.
    - 45-70: acceptable/neutral.
    - <45: laggard; avoid overweight unless there is a separate thesis.
    """
    bench = _clean_prices(benchmark)
    lbs = [int(x) for x in lookbacks if int(x) > 1]
    if len(bench) < 3:
        return {"ok": False, "error": "not_enough_benchmark_prices"}

    rows: List[Dict[str, Any]] = []
    for symbol, raw_prices in (assets or {}).items():
        prices = _clean_prices(raw_prices)
        if len(prices) < 3:
            rows.append({"symbol": symbol, "ok": False, "error": "not_enough_asset_prices", "rs_score": 0.0})
            continue
        excess_values: List[float] = []
        detail: Dict[str, Any] = {}
        for lb in lbs:
            ar = _simple_return(prices, lb)
            br = _simple_return(bench, lb)
            if ar is None or br is None:
                continue
            excess = ar - br
            excess_values.append(excess)
            detail[f"return_{lb}d_pct"] = round(ar * 100, 4)
            detail[f"benchmark_{lb}d_pct"] = round(br * 100, 4)
            detail[f"excess_{lb}d_pct"] = round(excess * 100, 4)
        vol = _annual_vol(prices)
        avg_excess = mean(excess_values) if excess_values else 0.0
        vol_adj = avg_excess / max(vol or 0.20, 0.05)
        # bounded smooth score around 50; roughly +10% excess at 20% vol maps near 75.
        rs_score = 50.0 + max(-35.0, min(35.0, vol_adj * 50.0))
        row = {
            "symbol": str(symbol).upper(),
            "ok": True,
            "rs_score": round(rs_score, 4),
            "avg_excess_return_pct": round(avg_excess * 100, 4),
            "annual_volatility_pct": round((vol or 0.0) * 100, 4),
            "relative_state": "LEADER" if rs_score >= 70 else "LAGGARD" if rs_score < 45 else "NEUTRAL",
        }
        row.update(detail)
        rows.append(row)

    _rank_percentile(rows, "rs_score")
    rows.sort(key=lambda x: (safe_float(x.get("rs_score"), -999) or -999), reverse=True)
    return {"ok": True, "version": V33_VERSION, "benchmark_points": len(bench), "rankings": rows}


def drawdown_control(
    equity_curve: Iterable[Any],
    daily_loss_pct: float = 0.0,
    max_drawdown_limit_pct: float = -12.0,
    warning_drawdown_pct: float = -7.0,
    hard_daily_loss_pct: float = -2.0,
) -> Dict[str, Any]:
    curve = [safe_float(x) for x in equity_curve or []]
    curve = [float(x) for x in curve if x is not None and x > 0]
    if len(curve) < 2:
        return {"ok": False, "error": "not_enough_equity_curve"}
    peak = max(curve)
    current_dd = curve[-1] / peak - 1.0 if peak > 0 else 0.0
    max_dd = _max_drawdown(curve)
    daily_loss = safe_float(daily_loss_pct, 0.0) or 0.0
    if abs(daily_loss) > 1:  # caller may pass -2 instead of -0.02
        daily_loss = daily_loss / 100.0
    hard_daily = -abs(hard_daily_loss_pct / 100.0 if abs(hard_daily_loss_pct) > 1 else hard_daily_loss_pct)
    max_limit = -abs(max_drawdown_limit_pct / 100.0 if abs(max_drawdown_limit_pct) > 1 else max_drawdown_limit_pct)
    warn_limit = -abs(warning_drawdown_pct / 100.0 if abs(warning_drawdown_pct) > 1 else warning_drawdown_pct)

    reasons: List[str] = []
    multiplier = 1.0
    action = "ALLOW"
    if daily_loss <= hard_daily:
        action = "BLOCK_NEW_TRADES"
        multiplier = 0.0
        reasons.append("daily_loss_kill_switch")
    elif current_dd <= max_limit or max_dd <= max_limit:
        action = "BLOCK_NEW_TRADES"
        multiplier = 0.0
        reasons.append("max_drawdown_limit_breached")
    elif current_dd <= warn_limit or max_dd <= warn_limit:
        action = "REDUCE_RISK"
        multiplier = 0.50
        reasons.append("drawdown_warning_reduce_size")

    return {
        "ok": True,
        "version": V33_VERSION,
        "action": action,
        "risk_multiplier": multiplier,
        "current_drawdown_pct": round(current_dd * 100, 4),
        "max_drawdown_pct": round(max_dd * 100, 4),
        "daily_loss_pct": round(daily_loss * 100, 4),
        "reasons": reasons,
    }


def portfolio_allocation(
    candidates: Iterable[Dict[str, Any]],
    total_equity: float = 100000.0,
    max_weight: float = 0.25,
    min_weight: float = 0.02,
    cash_floor: float = 0.10,
    drawdown_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Allocate capital to ranked candidates with risk caps.

    Candidate fields accepted: symbol, score, probability, rs_score, annual_volatility_pct,
    max_drawdown_pct, allow/eligible.
    """
    equity = safe_float(total_equity, 100000.0) or 100000.0
    max_weight = max(0.01, min(safe_float(max_weight, 0.25) or 0.25, 1.0))
    min_weight = max(0.0, min(safe_float(min_weight, 0.02) or 0.02, max_weight))
    cash_floor = max(0.0, min(safe_float(cash_floor, 0.10) or 0.10, 0.80))
    dd = drawdown_state or {"risk_multiplier": 1.0, "action": "ALLOW"}
    risk_multiplier = max(0.0, min(safe_float(dd.get("risk_multiplier"), 1.0) or 0.0, 1.0))

    rows: List[Dict[str, Any]] = []
    for c in candidates or []:
        symbol = str(c.get("symbol", "")).upper().strip()
        if not symbol:
            continue
        if c.get("allow") is False or c.get("eligible") is False:
            continue
        score = safe_float(c.get("score"), 50.0) or 50.0
        prob = safe_float(c.get("probability"), 50.0) or 50.0
        rs = safe_float(c.get("rs_score"), 50.0) or 50.0
        vol_pct = safe_float(c.get("annual_volatility_pct"), 25.0) or 25.0
        mdd_pct = safe_float(c.get("max_drawdown_pct"), -10.0) or -10.0
        if score < 50 or prob < 50 or rs < 45:
            continue
        quality = (0.40 * score) + (0.25 * prob) + (0.35 * rs)
        vol_penalty = max(vol_pct / 20.0, 0.50)
        dd_penalty = 1.0 + min(abs(mdd_pct) / 25.0, 2.0)
        raw = max(0.0, quality - 45.0) / (vol_penalty * dd_penalty)
        rows.append({
            "symbol": symbol,
            "score": round(score, 4),
            "probability": round(prob, 4),
            "rs_score": round(rs, 4),
            "annual_volatility_pct": round(vol_pct, 4),
            "max_drawdown_pct": round(mdd_pct, 4),
            "raw_weight_score": raw,
        })

    if not rows or risk_multiplier <= 0:
        return {"ok": True, "version": V33_VERSION, "cash_weight": 1.0, "allocations": [], "notes": ["No eligible assets or risk kill-switch active"]}

    raw_sum = sum(x["raw_weight_score"] for x in rows)
    investable = (1.0 - cash_floor) * risk_multiplier
    for x in rows:
        w = (x["raw_weight_score"] / raw_sum) * investable if raw_sum > 0 else 0.0
        x["weight"] = min(max(w, min_weight), max_weight)

    # Re-normalise after caps without exceeding investable.
    capped_sum = sum(x["weight"] for x in rows)
    if capped_sum > investable and capped_sum > 0:
        scale = investable / capped_sum
        for x in rows:
            x["weight"] *= scale

    rows = [x for x in rows if x["weight"] > 0]
    rows.sort(key=lambda x: x["weight"], reverse=True)
    for x in rows:
        x["notional"] = round(x["weight"] * equity, 2)
        x["weight"] = round(x["weight"], 6)
        x["raw_weight_score"] = round(x["raw_weight_score"], 6)

    used = sum(x["weight"] for x in rows)
    return {
        "ok": True,
        "version": V33_VERSION,
        "cash_weight": round(max(0.0, 1.0 - used), 6),
        "invested_weight": round(used, 6),
        "risk_multiplier": risk_multiplier,
        "drawdown_action": dd.get("action", "ALLOW"),
        "allocations": rows,
    }


def walk_forward_validation(
    prices_by_symbol: Dict[str, Iterable[Any]],
    signals_by_symbol: Dict[str, Iterable[Any]],
    folds: int = 4,
    min_positive_fold_rate: float = 0.60,
    max_worst_drawdown_pct: float = -20.0,
    **backtest_kwargs: Any,
) -> Dict[str, Any]:
    """Run walk-forward checks per symbol and return a deploy/no-deploy verdict."""
    folds = max(2, min(int(folds or 4), 12))
    rows: List[Dict[str, Any]] = []
    for symbol, raw_prices in (prices_by_symbol or {}).items():
        px = _clean_prices(raw_prices)
        sigs = list((signals_by_symbol or {}).get(symbol, []))
        n = min(len(px), len(sigs))
        if n < 20:
            rows.append({"symbol": symbol, "ok": False, "error": "not_enough_data"})
            continue
        fold_size = n // folds
        fold_results: List[Dict[str, Any]] = []
        for k in range(folds):
            start = k * fold_size
            end = n if k == folds - 1 else (k + 1) * fold_size
            if end - start < 8:
                continue
            bt = backtest_signals(px[start:end], sigs[start:end], **backtest_kwargs)
            if bt.get("ok"):
                fold_results.append({
                    "fold": k + 1,
                    "return_pct": bt.get("total_return_pct", 0.0),
                    "max_drawdown_pct": bt.get("max_drawdown_pct", 0.0),
                    "trades": bt.get("trades", 0),
                    "win_rate_pct": bt.get("win_rate_pct", 0.0),
                })
        returns = [safe_float(x.get("return_pct"), 0.0) or 0.0 for x in fold_results]
        dds = [safe_float(x.get("max_drawdown_pct"), 0.0) or 0.0 for x in fold_results]
        positive_rate = len([x for x in returns if x > 0]) / len(returns) if returns else 0.0
        worst_dd = min(dds) if dds else 0.0
        passed = bool(fold_results) and positive_rate >= min_positive_fold_rate and worst_dd >= max_worst_drawdown_pct
        rows.append({
            "symbol": str(symbol).upper(),
            "ok": True,
            "pass": passed,
            "fold_count": len(fold_results),
            "positive_fold_rate_pct": round(positive_rate * 100, 4),
            "avg_return_pct": round(mean(returns), 4) if returns else 0.0,
            "worst_drawdown_pct": round(worst_dd, 4),
            "folds": fold_results,
        })

    valid = [x for x in rows if x.get("ok")]
    passed_count = len([x for x in valid if x.get("pass")])
    pass_rate = passed_count / len(valid) if valid else 0.0
    return {
        "ok": True,
        "version": V33_VERSION,
        "deploy_verdict": "PASS" if valid and pass_rate >= 0.70 else "WARN",
        "pass_rate_pct": round(pass_rate * 100, 4),
        "symbols_tested": len(valid),
        "results": rows,
        "warning": "Do not deploy live capital if verdict is WARN. Use paper trading until forward results are stable.",
    }


def institutional_decision_pack(payload: Dict[str, Any]) -> Dict[str, Any]:
    """One-call orchestration for the app/API."""
    assets = payload.get("assets") or {}
    benchmark = payload.get("benchmark") or []
    candidates = payload.get("candidates") or []
    equity_curve = payload.get("equity_curve") or []
    total_equity = payload.get("total_equity", 100000)

    rs = relative_strength_ranking(assets, benchmark, payload.get("lookbacks") or (20, 60, 120)) if assets and benchmark else {"ok": False, "error": "missing_rs_inputs"}
    rs_map = {x["symbol"]: x for x in rs.get("rankings", [])} if rs.get("ok") else {}
    enriched: List[Dict[str, Any]] = []
    for c in candidates:
        row = dict(c)
        sym = str(row.get("symbol", "")).upper()
        if sym in rs_map:
            row["rs_score"] = rs_map[sym].get("rs_score")
            row["annual_volatility_pct"] = row.get("annual_volatility_pct", rs_map[sym].get("annual_volatility_pct"))
        enriched.append(row)

    dd = drawdown_control(equity_curve, payload.get("daily_loss_pct", 0.0)) if equity_curve else {"ok": True, "action": "ALLOW", "risk_multiplier": 1.0}
    alloc = portfolio_allocation(enriched, total_equity=total_equity, drawdown_state=dd)
    wf = None
    if payload.get("prices_by_symbol") and payload.get("signals_by_symbol"):
        wf = walk_forward_validation(payload.get("prices_by_symbol"), payload.get("signals_by_symbol"), folds=int(payload.get("folds") or 4))

    return {"ok": True, "version": V33_VERSION, "relative_strength": rs, "drawdown_control": dd, "portfolio_allocation": alloc, "walk_forward_validation": wf}
