
"""
V26.9 Adaptive Weight Engine
ปรับน้ำหนักสัญญาณจากผลลัพธ์จริง แทนค่าน้ำหนักคงที่

Factors:
- RSI
- RVOL
- Option Flow
- News Sentiment
- Market Breadth
- Sector Rotation
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone


DEFAULT_WEIGHTS: Dict[str, float] = {
    "rsi": 1.00,
    "rvol": 1.00,
    "option_flow": 1.00,
    "news_sentiment": 1.00,
    "market_breadth": 1.00,
    "sector_rotation": 1.00,
}

MIN_WEIGHT = 0.50
MAX_WEIGHT = 1.75
MIN_SAMPLE_SIZE = 20


@dataclass
class AdaptiveWeightResult:
    factor: str
    old_weight: float
    new_weight: float
    sample_size: int
    win_rate: float
    avg_return_r: float
    avg_drawdown_r: float
    reason: str


def clamp(value: float, low: float = MIN_WEIGHT, high: float = MAX_WEIGHT) -> float:
    return max(low, min(high, value))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def normalize_outcome(row: Dict[str, Any]) -> int:
    outcome = str(row.get("outcome") or row.get("result") or "").upper()
    if outcome in {"TP", "TP1", "TP2", "TP3", "WIN", "PROFIT", "HIT_TP"}:
        return 1
    if safe_float(row.get("return_r"), 0) > 0:
        return 1
    return 0


def factor_bucket_pass(row: Dict[str, Any], factor: str) -> bool:
    if factor == "rsi":
        rsi = safe_float(row.get("rsi"), 50)
        return 50 <= rsi <= 68
    if factor == "rvol":
        return safe_float(row.get("rvol"), 0) >= 1.3
    if factor == "option_flow":
        return safe_float(row.get("option_flow_score"), 0) >= 75
    if factor == "news_sentiment":
        return safe_float(row.get("news_sentiment_score"), 50) >= 60
    if factor == "market_breadth":
        return safe_float(row.get("breadth_score"), 50) >= 55
    if factor == "sector_rotation":
        return safe_float(row.get("sector_rotation_score"), 50) >= 60
    return False


def compute_factor_stats(rows: List[Dict[str, Any]], factor: str) -> Dict[str, float]:
    selected = [r for r in rows if factor_bucket_pass(r, factor)]
    n = len(selected)
    if n == 0:
        return {"sample_size": 0, "win_rate": 0.0, "avg_return_r": 0.0, "avg_drawdown_r": 0.0}

    wins = sum(normalize_outcome(r) for r in selected)
    returns = [safe_float(r.get("return_r"), 0.0) for r in selected]
    drawdowns = [abs(safe_float(r.get("drawdown_r"), 0.0)) for r in selected]

    return {
        "sample_size": n,
        "win_rate": wins / n,
        "avg_return_r": sum(returns) / n if returns else 0.0,
        "avg_drawdown_r": sum(drawdowns) / n if drawdowns else 0.0,
    }


def update_single_weight(old_weight: float, stats: Dict[str, float], baseline_win_rate: float = 0.50, baseline_return_r: float = 0.0) -> AdaptiveWeightResult:
    factor = stats.get("factor", "unknown")
    n = int(stats.get("sample_size", 0))
    win_rate = safe_float(stats.get("win_rate"), 0.0)
    avg_return = safe_float(stats.get("avg_return_r"), 0.0)
    avg_dd = safe_float(stats.get("avg_drawdown_r"), 0.0)

    if n < MIN_SAMPLE_SIZE:
        return AdaptiveWeightResult(
            factor=factor,
            old_weight=old_weight,
            new_weight=old_weight,
            sample_size=n,
            win_rate=win_rate,
            avg_return_r=avg_return,
            avg_drawdown_r=avg_dd,
            reason=f"sample size ต่ำกว่า {MIN_SAMPLE_SIZE} จึงยังไม่ปรับน้ำหนัก",
        )

    adjustment = 0.0

    if win_rate >= baseline_win_rate + 0.12:
        adjustment += 0.15
    elif win_rate >= baseline_win_rate + 0.06:
        adjustment += 0.08
    elif win_rate <= baseline_win_rate - 0.12:
        adjustment -= 0.15
    elif win_rate <= baseline_win_rate - 0.06:
        adjustment -= 0.08

    if avg_return >= baseline_return_r + 0.50:
        adjustment += 0.10
    elif avg_return >= baseline_return_r + 0.20:
        adjustment += 0.05
    elif avg_return <= baseline_return_r - 0.30:
        adjustment -= 0.10

    if avg_dd >= 1.50:
        adjustment -= 0.12
    elif avg_dd >= 1.00:
        adjustment -= 0.06

    new_weight = clamp(old_weight + adjustment)

    if adjustment > 0:
        reason = "เพิ่มน้ำหนัก เพราะ win rate/expectancy ดีกว่าค่าเฉลี่ย"
    elif adjustment < 0:
        reason = "ลดน้ำหนัก เพราะผลลัพธ์หรือ drawdown แย่กว่าค่าเฉลี่ย"
    else:
        reason = "คงน้ำหนักเดิม เพราะผลลัพธ์ใกล้ baseline"

    return AdaptiveWeightResult(
        factor=factor,
        old_weight=old_weight,
        new_weight=new_weight,
        sample_size=n,
        win_rate=win_rate,
        avg_return_r=avg_return,
        avg_drawdown_r=avg_dd,
        reason=reason,
    )


class AdaptiveWeightEngine:
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = dict(DEFAULT_WEIGHTS)
        if weights:
            for k, v in weights.items():
                if k in self.weights:
                    self.weights[k] = clamp(safe_float(v, self.weights[k]))

    def learn_from_rows(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        outcomes = [normalize_outcome(r) for r in rows]
        baseline_win_rate = sum(outcomes) / len(outcomes) if outcomes else 0.50
        baseline_return_r = sum(safe_float(r.get("return_r"), 0.0) for r in rows) / len(rows) if rows else 0.0

        results: List[AdaptiveWeightResult] = []
        for factor in DEFAULT_WEIGHTS:
            stats = compute_factor_stats(rows, factor)
            stats["factor"] = factor
            result = update_single_weight(
                old_weight=self.weights.get(factor, 1.0),
                stats=stats,
                baseline_win_rate=baseline_win_rate,
                baseline_return_r=baseline_return_r,
            )
            self.weights[factor] = result.new_weight
            results.append(result)

        return {
            "ok": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "baseline_win_rate": round(baseline_win_rate, 4),
            "baseline_return_r": round(baseline_return_r, 4),
            "weights": {k: round(v, 4) for k, v in self.weights.items()},
            "results": [asdict(r) for r in results],
        }

    def apply_to_score(self, factor_scores: Dict[str, float], base_score: float = 50.0) -> Dict[str, Any]:
        total_weight = 0.0
        weighted_sum = 0.0

        for factor, weight in self.weights.items():
            value = safe_float(factor_scores.get(factor), 50.0)
            weighted_sum += value * weight
            total_weight += weight

        adaptive_score = weighted_sum / total_weight if total_weight else base_score
        final_score = (base_score * 0.45) + (adaptive_score * 0.55)

        return {
            "base_score": round(base_score, 2),
            "adaptive_factor_score": round(adaptive_score, 2),
            "final_score": round(final_score, 2),
            "weights": {k: round(v, 4) for k, v in self.weights.items()},
        }


def demo_rows() -> List[Dict[str, Any]]:
    return [
        {"rsi": 58, "rvol": 2.1, "option_flow_score": 86, "news_sentiment_score": 70, "breadth_score": 65, "sector_rotation_score": 82, "outcome": "TP2", "return_r": 2.1, "drawdown_r": 0.5},
        {"rsi": 64, "rvol": 1.8, "option_flow_score": 78, "news_sentiment_score": 62, "breadth_score": 70, "sector_rotation_score": 75, "outcome": "WIN", "return_r": 1.4, "drawdown_r": 0.4},
        {"rsi": 74, "rvol": 0.7, "option_flow_score": 35, "news_sentiment_score": 42, "breadth_score": 38, "sector_rotation_score": 40, "outcome": "SL", "return_r": -1.0, "drawdown_r": 1.2},
    ] * 10
