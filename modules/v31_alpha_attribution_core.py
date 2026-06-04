"""
V31 Alpha Research & Performance Attribution Core

Purpose:
- Prove which signal components actually contribute to realised return.
- Recommend adaptive component weights from observed outcomes.
- Run Monte Carlo risk-of-ruin tests from realised R-multiples.
- Rank/optimize candidate signals before sending alerts.
- Split performance by market regime.

Design:
- Dependency-light and production-safe.
- Uses the V29 Store abstraction, so PostgreSQL is used when DATABASE_URL is configured,
  with SQLite fallback for local development.
- Does not remove or rewrite V28/V29/V30 behavior. It sits above them as a research and
  capital-allocation layer.
"""
from __future__ import annotations

import json
import math
import os
import random
from datetime import datetime, timezone
from statistics import mean, pstdev
from typing import Any, Dict, Iterable, List, Optional, Tuple

from modules import v29_governance_core as v29
try:
    from modules import v30_model_validation_core as v30
except Exception:  # pragma: no cover
    v30 = None

V31_VERSION = "V31 Alpha Research & Performance Attribution Core"

V31_MIN_OBSERVATIONS = int(os.getenv("V31_MIN_OBSERVATIONS", "10"))
V31_WEIGHT_LOOKBACK = int(os.getenv("V31_WEIGHT_LOOKBACK", "500"))
V31_MONTE_CARLO_RUNS = int(os.getenv("V31_MONTE_CARLO_RUNS", "5000"))
V31_MONTE_CARLO_TRADES = int(os.getenv("V31_MONTE_CARLO_TRADES", "100"))
V31_RISK_OF_RUIN_DD_R = float(os.getenv("V31_RISK_OF_RUIN_DD_R", "-10.0"))
V31_MAX_SAME_GROUP = int(os.getenv("V31_MAX_SAME_GROUP", "2"))
V31_MIN_ALPHA_SCORE = float(os.getenv("V31_MIN_ALPHA_SCORE", "0.0"))
V31_ALPHA_GATE_MODE = os.getenv("V31_ALPHA_GATE_MODE", "observe").lower()  # observe|block

store = v29.store


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ph() -> str:
    return store.ph()


def as_json(obj: Any) -> str:
    return v29.as_json(obj)


def safe_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    return v29.safe_float(v, default)


def safe_json(v: Any, default: Optional[Any] = None) -> Any:
    if v is None:
        return {} if default is None else default
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return {} if default is None else default


def init_v31_db() -> Dict[str, Any]:
    if v30 is not None:
        try:
            v30.init_v30_db()
        except Exception:
            v29.init_v29_db()
    else:
        v29.init_v29_db()
    idcol = store.serial()
    jtype = store.json_type()
    ddl = [
        f"""
        CREATE TABLE IF NOT EXISTS v31_signal_components (
            id {idcol},
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT,
            source_signal_id TEXT,
            component_name TEXT NOT NULL,
            component_value REAL NOT NULL,
            component_direction TEXT DEFAULT 'positive',
            return_r REAL,
            outcome TEXT,
            regime TEXT,
            strategy_key TEXT,
            metadata {jtype}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS v31_attribution_runs (
            id {idcol},
            created_at TEXT NOT NULL,
            run_key TEXT NOT NULL,
            lookback INTEGER,
            min_observations INTEGER,
            components INTEGER,
            status TEXT NOT NULL,
            summary {jtype},
            result_json {jtype}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS v31_weight_recommendations (
            id {idcol},
            created_at TEXT NOT NULL,
            run_key TEXT NOT NULL,
            component_name TEXT NOT NULL,
            recommended_weight REAL NOT NULL,
            alpha_score REAL NOT NULL,
            observations INTEGER,
            avg_return_r REAL,
            hit_rate REAL,
            correlation REAL,
            status TEXT DEFAULT 'ACTIVE',
            reason TEXT,
            details {jtype}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS v31_monte_carlo_runs (
            id {idcol},
            created_at TEXT NOT NULL,
            run_key TEXT NOT NULL,
            source TEXT,
            simulations INTEGER,
            trades_per_run INTEGER,
            expected_return_r REAL,
            median_return_r REAL,
            p05_return_r REAL,
            p95_return_r REAL,
            worst_drawdown_r REAL,
            risk_of_ruin_pct REAL,
            pass_fail TEXT,
            result_json {jtype}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS v31_optimizer_runs (
            id {idcol},
            created_at TEXT NOT NULL,
            run_key TEXT NOT NULL,
            candidate_count INTEGER,
            selected_count INTEGER,
            status TEXT NOT NULL,
            selected_json {jtype},
            rejected_json {jtype},
            result_json {jtype}
        )
        """,
    ]
    for sql in ddl:
        store.execute(sql)
    return {"ok": True, "version": V31_VERSION, "database": "postgresql" if store.pg else "sqlite", "tables": 5}


def recent_rows(table: str, limit: int = 100) -> List[Dict[str, Any]]:
    allowed = {
        "v31_signal_components",
        "v31_attribution_runs",
        "v31_weight_recommendations",
        "v31_monte_carlo_runs",
        "v31_optimizer_runs",
    }
    if table not in allowed:
        return []
    limit = max(1, min(int(limit or 100), 1000))
    return store.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT {limit}", fetch="all") or []


def extract_components(payload: Dict[str, Any]) -> Dict[str, float]:
    """Extract normalized numeric signal components from arbitrary analysis payload."""
    if not isinstance(payload, dict):
        return {}
    mapping = {
        "rsi": ["rsi", "RSI"],
        "ema_trend": ["ema_trend", "trend_strength", "trend"],
        "volume": ["rvol", "relative_volume", "volume_score"],
        "confidence": ["confidence", "score", "conviction"],
        "market_breadth": ["breadth", "market_breadth"],
        "regime_score": ["regime_score", "market_regime_score"],
        "risk_reward": ["risk_reward", "reward_risk", "rr", "rr_ratio"],
        "momentum": ["momentum", "momentum_score"],
        "data_quality": ["data_quality", "data_quality_score"],
    }
    components: Dict[str, float] = {}
    for cname, keys in mapping.items():
        for key in keys:
            if key in payload:
                val = safe_float(payload.get(key))
                if val is not None:
                    components[cname] = normalize_component(cname, val)
                    break
    # Nested common payload shapes.
    for nested_key in ("analysis", "signal", "features", "indicators"):
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            for k, v in extract_components(nested).items():
                components.setdefault(k, v)
    return components


def normalize_component(name: str, value: float) -> float:
    """Convert heterogeneous indicator scales to roughly 0..1 when possible."""
    x = float(value)
    if name in {"confidence", "data_quality", "regime_score", "market_breadth", "ema_trend", "momentum"}:
        return max(0.0, min(1.0, x / 100.0 if abs(x) > 1.5 else x))
    if name == "rsi":
        # 50-65 often preferred for long continuation. Too low/high is penalized.
        if x > 1.5:
            return max(0.0, min(1.0, 1.0 - abs(x - 57.5) / 57.5))
        return max(0.0, min(1.0, x))
    if name == "volume":
        return max(0.0, min(1.0, x / 3.0))
    if name == "risk_reward":
        return max(0.0, min(1.0, x / 5.0))
    return max(-1.0, min(1.0, x))


def record_signal_components(
    symbol: str,
    side: str,
    components: Dict[str, Any],
    return_r: Optional[float] = None,
    outcome: Optional[str] = None,
    regime: Optional[str] = None,
    strategy_key: Optional[str] = None,
    source_signal_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    init_v31_db()
    symbol = str(symbol or "").upper().strip()
    if not symbol:
        return {"ok": False, "error": "symbol required"}
    if not components:
        return {"ok": False, "error": "components required"}
    inserted = 0
    marker = ph()
    for cname, raw_val in components.items():
        val = safe_float(raw_val)
        if val is None:
            continue
        store.execute(
            f"INSERT INTO v31_signal_components(created_at,symbol,side,source_signal_id,component_name,component_value,return_r,outcome,regime,strategy_key,metadata) VALUES({','.join([marker]*11)})",
            (now_iso(), symbol, str(side or "").upper(), source_signal_id, str(cname), float(val), safe_float(return_r), outcome, regime, strategy_key, as_json(metadata or {})),
        )
        inserted += 1
    return {"ok": inserted > 0, "version": V31_VERSION, "inserted": inserted, "symbol": symbol}


def sync_from_v28_outcomes(limit: int = 500) -> Dict[str, Any]:
    """Best-effort import from V28 audit/outcome tables into V31 components.

    Works even when older rows have sparse payloads. If raw_payload contains indicators,
    V31 will use them; otherwise it falls back to available scalar columns.
    """
    init_v31_db()
    limit = max(1, min(int(limit or 500), 5000))
    rows: List[Dict[str, Any]] = []
    try:
        rows = store.execute(
            f"""
            SELECT a.id AS audit_id, a.created_at, a.symbol, a.side, a.score, a.confidence,
                   a.trend_strength, a.rvol, a.regime, a.raw_payload,
                   o.return_r, o.outcome, o.status
            FROM v28_signal_audit a
            LEFT JOIN v28_open_signals o ON o.audit_id = a.id
            ORDER BY a.id DESC
            LIMIT {limit}
            """,
            fetch="all",
        ) or []
    except Exception:
        rows = []
    inserted = 0
    skipped = 0
    for r in rows:
        payload = safe_json(r.get("raw_payload"), {})
        if not isinstance(payload, dict):
            payload = {}
        payload.setdefault("score", r.get("score"))
        payload.setdefault("confidence", r.get("confidence"))
        payload.setdefault("trend_strength", r.get("trend_strength"))
        payload.setdefault("rvol", r.get("rvol"))
        comps = extract_components(payload)
        if not comps:
            skipped += 1
            continue
        res = record_signal_components(
            symbol=r.get("symbol"),
            side=r.get("side"),
            components=comps,
            return_r=safe_float(r.get("return_r")),
            outcome=r.get("outcome") or r.get("status"),
            regime=r.get("regime"),
            strategy_key="V28_LIVE_SIGNAL",
            source_signal_id=str(r.get("audit_id")),
            metadata={"source": "v28_sync"},
        )
        inserted += int(res.get("inserted") or 0)
    return {"ok": True, "version": V31_VERSION, "source_rows": len(rows), "inserted_components": inserted, "skipped": skipped}


def _component_rows(lookback: int = V31_WEIGHT_LOOKBACK) -> List[Dict[str, Any]]:
    init_v31_db()
    lookback = max(1, min(int(lookback or V31_WEIGHT_LOOKBACK), 10000))
    return store.execute(
        f"SELECT * FROM v31_signal_components WHERE return_r IS NOT NULL ORDER BY id DESC LIMIT {lookback}",
        fetch="all",
    ) or []


def pearson(xs: List[float], ys: List[float]) -> float:
    if len(xs) < 2 or len(xs) != len(ys):
        return 0.0
    mx, my = mean(xs), mean(ys)
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return 0.0
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return cov / math.sqrt(vx * vy)


def component_attribution(lookback: int = V31_WEIGHT_LOOKBACK, min_observations: int = V31_MIN_OBSERVATIONS) -> Dict[str, Any]:
    init_v31_db()
    rows = _component_rows(lookback)
    grouped: Dict[str, List[Tuple[float, float]]] = {}
    for r in rows:
        val = safe_float(r.get("component_value"))
        ret = safe_float(r.get("return_r"))
        if val is None or ret is None:
            continue
        grouped.setdefault(str(r.get("component_name")), []).append((val, ret))

    components: List[Dict[str, Any]] = []
    for name, vals in sorted(grouped.items()):
        if len(vals) < min_observations:
            status = "INSUFFICIENT_DATA"
        else:
            status = "VALID"
        xs = [x for x, _ in vals]
        rs = [r for _, r in vals]
        avg_ret = mean(rs) if rs else 0.0
        hit_rate = len([r for r in rs if r > 0]) / len(rs) * 100 if rs else 0.0
        corr = pearson(xs, rs)
        # Alpha score balances magnitude, consistency, and relationship to outcome.
        confidence_adj = min(1.0, math.log(len(rs) + 1) / math.log(max(min_observations * 4, 2))) if rs else 0.0
        alpha_score = (avg_ret * 0.55) + ((hit_rate - 50.0) / 100.0 * 0.25) + (corr * 0.20)
        alpha_score *= confidence_adj
        components.append({
            "component_name": name,
            "observations": len(rs),
            "avg_return_r": round(avg_ret, 4),
            "median_return_r": round(sorted(rs)[len(rs)//2], 4) if rs else 0.0,
            "hit_rate": round(hit_rate, 2),
            "correlation": round(corr, 4),
            "alpha_score": round(alpha_score, 5),
            "status": status,
        })

    valid = [c for c in components if c["status"] == "VALID"]
    valid.sort(key=lambda x: x["alpha_score"], reverse=True)
    run_key = f"V31_ATTR_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    summary = {
        "rows": len(rows),
        "valid_components": len(valid),
        "best_component": valid[0]["component_name"] if valid else None,
        "warning": None if valid else "insufficient realised signal components; run forward test or sync outcomes first",
    }
    marker = ph()
    store.execute(
        f"INSERT INTO v31_attribution_runs(created_at,run_key,lookback,min_observations,components,status,summary,result_json) VALUES({','.join([marker]*8)})",
        (now_iso(), run_key, lookback, min_observations, len(components), "OK" if valid else "INSUFFICIENT_DATA", as_json(summary), as_json(components)),
    )
    return {"ok": True, "version": V31_VERSION, "run_key": run_key, "summary": summary, "components": components}


def recommend_weights(lookback: int = V31_WEIGHT_LOOKBACK, min_observations: int = V31_MIN_OBSERVATIONS) -> Dict[str, Any]:
    attr = component_attribution(lookback, min_observations)
    run_key = attr["run_key"].replace("ATTR", "WEIGHT")
    valid = [c for c in attr.get("components", []) if c.get("status") == "VALID"]
    # Positive-only allocation. Negative scores get zero weight but are still reported.
    positives = [max(0.0, float(c.get("alpha_score") or 0.0)) for c in valid]
    total = sum(positives)
    recs: List[Dict[str, Any]] = []
    marker = ph()
    for c, pos in zip(valid, positives):
        weight = (pos / total) if total > 0 else (1.0 / len(valid) if valid else 0.0)
        reason = "positive alpha contribution" if pos > 0 else "no positive contribution; keep at zero until more evidence"
        rec = {
            "component_name": c["component_name"],
            "recommended_weight": round(weight, 4),
            "alpha_score": c["alpha_score"],
            "observations": c["observations"],
            "avg_return_r": c["avg_return_r"],
            "hit_rate": c["hit_rate"],
            "correlation": c["correlation"],
            "reason": reason,
        }
        recs.append(rec)
        store.execute(
            f"INSERT INTO v31_weight_recommendations(created_at,run_key,component_name,recommended_weight,alpha_score,observations,avg_return_r,hit_rate,correlation,reason,details) VALUES({','.join([marker]*11)})",
            (now_iso(), run_key, rec["component_name"], rec["recommended_weight"], rec["alpha_score"], rec["observations"], rec["avg_return_r"], rec["hit_rate"], rec["correlation"], rec["reason"], as_json(c)),
        )
    return {"ok": True, "version": V31_VERSION, "run_key": run_key, "recommendations": recs, "summary": attr.get("summary")}


def realised_returns(lookback: int = V31_WEIGHT_LOOKBACK) -> List[float]:
    rows = _component_rows(lookback)
    # Deduplicate approximate signal rows by source id when available.
    seen = set()
    returns: List[float] = []
    for r in rows:
        key = r.get("source_signal_id") or f"{r.get('symbol')}:{r.get('created_at')}:{r.get('return_r')}"
        if key in seen:
            continue
        seen.add(key)
        ret = safe_float(r.get("return_r"))
        if ret is not None:
            returns.append(float(ret))
    if not returns:
        try:
            rows2 = store.execute(f"SELECT return_r FROM v28_open_signals WHERE return_r IS NOT NULL ORDER BY id DESC LIMIT {max(1, int(lookback))}", fetch="all") or []
            returns = [float(r["return_r"]) for r in rows2 if safe_float(r.get("return_r")) is not None]
        except Exception:
            returns = []
    return returns


def monte_carlo_risk(returns: Optional[List[float]] = None, simulations: int = V31_MONTE_CARLO_RUNS, trades_per_run: int = V31_MONTE_CARLO_TRADES, ruin_dd_r: float = V31_RISK_OF_RUIN_DD_R) -> Dict[str, Any]:
    init_v31_db()
    returns = [float(x) for x in (returns if returns is not None else realised_returns()) if safe_float(x) is not None]
    simulations = max(100, min(int(simulations or V31_MONTE_CARLO_RUNS), 100000))
    trades_per_run = max(5, min(int(trades_per_run or V31_MONTE_CARLO_TRADES), 2000))
    if len(returns) < 5:
        return {"ok": False, "version": V31_VERSION, "error": "insufficient realised returns for Monte Carlo", "returns": len(returns)}

    totals: List[float] = []
    worst_dds: List[float] = []
    ruin_count = 0
    for _ in range(simulations):
        equity_r = 0.0
        peak = 0.0
        worst_dd = 0.0
        for _j in range(trades_per_run):
            equity_r += random.choice(returns)
            peak = max(peak, equity_r)
            dd = equity_r - peak
            worst_dd = min(worst_dd, dd)
        totals.append(equity_r)
        worst_dds.append(worst_dd)
        if worst_dd <= ruin_dd_r:
            ruin_count += 1
    totals_sorted = sorted(totals)
    p05 = totals_sorted[max(0, int(0.05 * len(totals_sorted)) - 1)]
    p95 = totals_sorted[min(len(totals_sorted)-1, int(0.95 * len(totals_sorted)))]
    median = totals_sorted[len(totals_sorted)//2]
    risk_ruin = ruin_count / simulations * 100.0
    expected = mean(totals)
    pass_fail = "PASS" if expected > 0 and risk_ruin < 10.0 else "FAIL"
    run_key = f"V31_MC_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    result = {
        "ok": True,
        "version": V31_VERSION,
        "run_key": run_key,
        "source_returns": len(returns),
        "simulations": simulations,
        "trades_per_run": trades_per_run,
        "expected_return_r": round(expected, 3),
        "median_return_r": round(median, 3),
        "p05_return_r": round(p05, 3),
        "p95_return_r": round(p95, 3),
        "worst_drawdown_r": round(min(worst_dds), 3),
        "avg_worst_drawdown_r": round(mean(worst_dds), 3),
        "risk_of_ruin_pct": round(risk_ruin, 2),
        "pass_fail": pass_fail,
    }
    marker = ph()
    store.execute(
        f"INSERT INTO v31_monte_carlo_runs(created_at,run_key,source,simulations,trades_per_run,expected_return_r,median_return_r,p05_return_r,p95_return_r,worst_drawdown_r,risk_of_ruin_pct,pass_fail,result_json) VALUES({','.join([marker]*13)})",
        (now_iso(), run_key, "realised_return_r", simulations, trades_per_run, result["expected_return_r"], result["median_return_r"], result["p05_return_r"], result["p95_return_r"], result["worst_drawdown_r"], result["risk_of_ruin_pct"], pass_fail, as_json(result)),
    )
    return result


def regime_attribution(lookback: int = V31_WEIGHT_LOOKBACK) -> Dict[str, Any]:
    rows = _component_rows(lookback)
    seen = set()
    grouped: Dict[str, List[float]] = {}
    for r in rows:
        key = r.get("source_signal_id") or f"{r.get('symbol')}:{r.get('created_at')}:{r.get('return_r')}"
        if key in seen:
            continue
        seen.add(key)
        regime = str(r.get("regime") or safe_json(r.get("metadata"), {}).get("regime") or "UNKNOWN").upper()
        ret = safe_float(r.get("return_r"))
        if ret is not None:
            grouped.setdefault(regime, []).append(float(ret))
    regimes = []
    for regime, rs in grouped.items():
        regimes.append({
            "regime": regime,
            "trades": len(rs),
            "avg_return_r": round(mean(rs), 4),
            "hit_rate": round(len([r for r in rs if r > 0]) / len(rs) * 100, 2) if rs else 0.0,
            "stdev_r": round(pstdev(rs), 4) if len(rs) > 1 else 0.0,
            "status": "VALID" if len(rs) >= V31_MIN_OBSERVATIONS else "INSUFFICIENT_DATA",
        })
    regimes.sort(key=lambda x: (x["status"] == "VALID", x["avg_return_r"]), reverse=True)
    return {"ok": True, "version": V31_VERSION, "regimes": regimes, "total_regimes": len(regimes)}


def score_candidate(candidate: Dict[str, Any], weights: Dict[str, float]) -> float:
    components = candidate.get("components") or extract_components(candidate)
    base = 0.0
    for cname, weight in weights.items():
        base += float(weight) * float(components.get(cname, 0.0) or 0.0)
    confidence = safe_float(candidate.get("confidence"), 50.0) or 50.0
    if confidence > 1.5:
        confidence = confidence / 100.0
    rr = safe_float(candidate.get("reward_risk") or candidate.get("risk_reward"), 1.0) or 1.0
    return round(base * 0.65 + max(0.0, min(1.0, confidence)) * 0.20 + max(0.0, min(1.0, rr / 5.0)) * 0.15, 5)


def load_latest_weights() -> Dict[str, float]:
    try:
        rows = store.execute("SELECT component_name,recommended_weight FROM v31_weight_recommendations WHERE status='ACTIVE' ORDER BY id DESC LIMIT 50", fetch="all") or []
    except Exception:
        rows = []
    weights: Dict[str, float] = {}
    # Latest rows first; keep first per component.
    for r in rows:
        name = str(r.get("component_name"))
        if name not in weights:
            weights[name] = float(safe_float(r.get("recommended_weight"), 0.0) or 0.0)
    if not weights:
        weights = {"confidence": 0.25, "ema_trend": 0.20, "volume": 0.15, "risk_reward": 0.20, "momentum": 0.10, "data_quality": 0.10}
    # Normalize.
    total = sum(max(0.0, v) for v in weights.values())
    return {k: (max(0.0, v) / total if total > 0 else 0.0) for k, v in weights.items()}


def optimize_portfolio_candidates(candidates: List[Dict[str, Any]], max_selected: int = 5, max_same_group: int = V31_MAX_SAME_GROUP) -> Dict[str, Any]:
    init_v31_db()
    if not isinstance(candidates, list):
        return {"ok": False, "error": "candidates must be a list"}
    max_selected = max(1, min(int(max_selected or 5), 50))
    weights = load_latest_weights()
    enriched: List[Dict[str, Any]] = []
    for c in candidates:
        if not isinstance(c, dict):
            continue
        item = dict(c)
        item["symbol"] = str(item.get("symbol") or "").upper()
        item["group"] = str(item.get("group") or item.get("sector") or item.get("asset_type") or "UNKNOWN").upper()
        item["alpha_score"] = score_candidate(item, weights)
        enriched.append(item)
    enriched.sort(key=lambda x: x.get("alpha_score", 0.0), reverse=True)

    selected: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    group_count: Dict[str, int] = {}
    for item in enriched:
        reason = None
        if not item.get("symbol"):
            reason = "missing symbol"
        elif item.get("alpha_score", 0.0) < V31_MIN_ALPHA_SCORE:
            reason = "alpha score below threshold"
        elif len(selected) >= max_selected:
            reason = "portfolio selection full"
        elif group_count.get(item["group"], 0) >= max_same_group:
            reason = f"group exposure limit reached: {item['group']}"
        if reason:
            bad = dict(item)
            bad["reject_reason"] = reason
            rejected.append(bad)
        else:
            selected.append(item)
            group_count[item["group"]] = group_count.get(item["group"], 0) + 1

    run_key = f"V31_OPT_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    result = {"ok": True, "version": V31_VERSION, "run_key": run_key, "weights_used": weights, "selected": selected, "rejected": rejected}
    marker = ph()
    store.execute(
        f"INSERT INTO v31_optimizer_runs(created_at,run_key,candidate_count,selected_count,status,selected_json,rejected_json,result_json) VALUES({','.join([marker]*8)})",
        (now_iso(), run_key, len(candidates), len(selected), "OK", as_json(selected), as_json(rejected), as_json(result)),
    )
    return result


def alpha_gate(signal_payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """Optional pre-alert gate. It scores a signal using latest V31 weights.

    By default this should be used as observe/advisory unless the operator explicitly
    enables hard blocking in the calling layer.
    """
    weights = load_latest_weights()
    score = score_candidate(signal_payload, weights)
    passed = score >= V31_MIN_ALPHA_SCORE
    detail = {"version": V31_VERSION, "alpha_score": score, "threshold": V31_MIN_ALPHA_SCORE, "weights_used": weights, "pass": passed}
    return passed, detail


def dashboard_payload() -> Dict[str, Any]:
    init_v31_db()
    latest_attr = recent_rows("v31_attribution_runs", 1)
    latest_mc = recent_rows("v31_monte_carlo_runs", 1)
    latest_weights = recent_rows("v31_weight_recommendations", 20)
    latest_opt = recent_rows("v31_optimizer_runs", 1)
    return {
        "ok": True,
        "version": V31_VERSION,
        "database": "postgresql" if store.pg else "sqlite",
        "latest_attribution": latest_attr[0] if latest_attr else None,
        "latest_monte_carlo": latest_mc[0] if latest_mc else None,
        "latest_weights": latest_weights,
        "latest_optimizer": latest_opt[0] if latest_opt else None,
        "regime_attribution": regime_attribution(),
    }


def dashboard_html() -> str:
    payload = dashboard_payload()
    weights = payload.get("latest_weights") or []
    mc = payload.get("latest_monte_carlo") or {}
    attr = payload.get("latest_attribution") or {}
    rows = "".join(
        f"<tr><td>{w.get('component_name')}</td><td>{w.get('recommended_weight')}</td><td>{w.get('alpha_score')}</td><td>{w.get('observations')}</td><td>{w.get('hit_rate')}</td><td>{w.get('reason','')}</td></tr>"
        for w in weights[:20]
    )
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><title>V31 Alpha Attribution</title>
<style>body{{font-family:Arial,sans-serif;margin:28px;background:#f6f7fb;color:#18202a}}.card{{background:white;border-radius:14px;padding:18px;margin:14px 0;box-shadow:0 2px 10px #0001}}table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #eee;padding:8px;text-align:left}}.ok{{color:#0a7a38}}.bad{{color:#b00020}}</style></head>
<body><h1>V31 Alpha Research & Performance Attribution Core</h1>
<div class='card'><b>Database:</b> {payload.get('database')}<br><b>Latest Attribution:</b> {attr.get('status','NONE')} | {attr.get('created_at','-')}</div>
<div class='card'><h2>Monte Carlo</h2><pre>{json.dumps(mc, ensure_ascii=False, indent=2, default=str)}</pre></div>
<div class='card'><h2>Recommended Component Weights</h2><table><tr><th>Component</th><th>Weight</th><th>Alpha</th><th>Obs</th><th>Hit %</th><th>Reason</th></tr>{rows}</table></div>
<div class='card'><h2>Regime Attribution</h2><pre>{json.dumps(payload.get('regime_attribution'), ensure_ascii=False, indent=2, default=str)}</pre></div>
</body></html>"""
