
"""
V27.1 Integration Pipeline
เชื่อมทุกโมดูลสำคัญเข้ากับ Alert Workflow จริง

Alert Flow:
Data Quality Guard
→ Capital Protection
→ Conviction Gate
→ Adaptive Weight
→ Forward Test
→ Send LINE / Block + Log Reason

ออกแบบให้ใช้ได้แม้บางโมดูลยังไม่มีข้อมูลจริง โดย fallback เป็น safe mode
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

try:
    from modules.v27_data_quality_guard import DataQualityGuard
except Exception:
    DataQualityGuard = None

try:
    from modules.v27_capital_protection import CapitalProtection
except Exception:
    CapitalProtection = None

try:
    from modules.v27_forward_test_engine import ForwardTestEngine
except Exception:
    ForwardTestEngine = None

try:
    from modules.v26_adaptive_weight_engine import AdaptiveWeightEngine
except Exception:
    AdaptiveWeightEngine = None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _grade_rank(grade: str) -> int:
    g = str(grade or "").upper().strip()
    order = {
        "INSTITUTIONAL": 5,
        "A+": 5,
        "A": 4,
        "B+": 3,
        "B": 2,
        "C": 1,
        "D": 0,
        "LOW": 0,
        "MEDIUM": 1,
        "HIGH": 3,
    }
    return order.get(g, 0)


class AlertIntegrationPipeline:
    def __init__(
        self,
        min_score: float = 85.0,
        min_adaptive_score: float = 85.0,
        min_conviction_score: float = 75.0,
        min_conviction_grade: str = "HIGH",
        min_rvol: float = 1.3,
        forward_test_days: int = 30,
    ):
        self.min_score = min_score
        self.min_adaptive_score = min_adaptive_score
        self.min_conviction_score = min_conviction_score
        self.min_conviction_grade = min_conviction_grade
        self.min_rvol = min_rvol
        self.forward_test_days = forward_test_days

    def evaluate(self, signal: Dict[str, Any], market_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        market_state = market_state or {}
        decision_log: List[Dict[str, Any]] = []
        blocked_reasons: List[str] = []

        symbol = str(signal.get("symbol", "")).upper()
        base_score = _safe_float(signal.get("score") or signal.get("technical_score"), 0)
        rvol = _safe_float(signal.get("rvol"), 0)
        conviction_score = _safe_float(signal.get("conviction_score"), _safe_float(signal.get("trade_quality_score"), 0))
        conviction_grade = str(signal.get("conviction_grade") or signal.get("conviction") or "").upper()

        # 1) Data Quality
        if DataQualityGuard:
            q = {
                "price": signal.get("price") or signal.get("entry"),
                "close": signal.get("price") or signal.get("entry"),
                "previous_close": signal.get("previous_close"),
                "source": signal.get("source", "pipeline"),
            }
            indicators = {
                "rsi": signal.get("rsi"),
                "rvol": signal.get("rvol"),
                "atr": signal.get("atr"),
            }
            dq = DataQualityGuard().should_block_alert(q, indicators)
        else:
            dq = {"block": False, "reason": "DataQualityGuard unavailable: safe pass"}

        decision_log.append({"step": "data_quality", "result": dq})
        if dq.get("block"):
            blocked_reasons.append("DATA_QUALITY: " + str(dq.get("reason")))

        # 2) Capital Protection
        if CapitalProtection:
            cap_payload = {
                "alerts_today": market_state.get("alerts_today", signal.get("alerts_today", 0)),
                "daily_return_r": market_state.get("daily_return_r", signal.get("daily_return_r", 0)),
                "consecutive_losses": market_state.get("consecutive_losses", signal.get("consecutive_losses", 0)),
                "breadth_score": market_state.get("breadth_score", signal.get("breadth_score", 50)),
                "vix": market_state.get("vix", signal.get("vix", 0)),
            }
            cp = CapitalProtection().evaluate(cap_payload)
            size = CapitalProtection().position_size_multiplier(cap_payload)
        else:
            cp = {"ok": True, "action": "ALLOW", "reasons": ["CapitalProtection unavailable: safe pass"]}
            size = {"multiplier": 1.0, "reasons": ["normal size"]}

        decision_log.append({"step": "capital_protection", "result": cp})
        decision_log.append({"step": "position_multiplier", "result": size})
        if not cp.get("ok", True):
            blocked_reasons.append("CAPITAL_PROTECTION: " + ", ".join(cp.get("reasons", [])))

        # 3) Basic strict gates
        if base_score < self.min_score:
            blocked_reasons.append(f"SCORE_LOW: {base_score} < {self.min_score}")

        if rvol and rvol < self.min_rvol:
            blocked_reasons.append(f"RVOL_LOW: {rvol} < {self.min_rvol}")

        if conviction_score and conviction_score < self.min_conviction_score:
            blocked_reasons.append(f"CONVICTION_SCORE_LOW: {conviction_score} < {self.min_conviction_score}")

        if conviction_grade and _grade_rank(conviction_grade) < _grade_rank(self.min_conviction_grade):
            blocked_reasons.append(f"CONVICTION_GRADE_LOW: {conviction_grade} < {self.min_conviction_grade}")

        # 4) Adaptive Weight
        adaptive_result = None
        if AdaptiveWeightEngine:
            factor_scores = {
                "rsi": _safe_float(signal.get("rsi_score"), 50),
                "rvol": _safe_float(signal.get("rvol_score"), min(100, max(0, rvol * 35 if rvol else 50))),
                "option_flow": _safe_float(signal.get("option_flow_score"), 50),
                "news_sentiment": _safe_float(signal.get("news_sentiment_score"), 50),
                "market_breadth": _safe_float(signal.get("breadth_score"), market_state.get("breadth_score", 50)),
                "sector_rotation": _safe_float(signal.get("sector_rotation_score"), 50),
            }
            try:
                adaptive_result = AdaptiveWeightEngine().apply_to_score(factor_scores, base_score=base_score)
            except Exception as e:
                adaptive_result = {"error": str(e), "final_score": base_score}
        else:
            adaptive_result = {"final_score": base_score, "reason": "AdaptiveWeightEngine unavailable"}

        adaptive_score = _safe_float(adaptive_result.get("final_score"), base_score)
        decision_log.append({"step": "adaptive_weight", "result": adaptive_result})

        if adaptive_score < self.min_adaptive_score:
            blocked_reasons.append(f"ADAPTIVE_SCORE_LOW: {adaptive_score} < {self.min_adaptive_score}")

        # 5) Forward Test record
        forward_record = None
        if ForwardTestEngine:
            try:
                forward_record = ForwardTestEngine().create_signal({
                    "symbol": symbol,
                    "side": signal.get("side", "CALL"),
                    "entry": signal.get("entry") or signal.get("price"),
                    "tp1": signal.get("tp1"),
                    "tp2": signal.get("tp2"),
                    "tp3": signal.get("tp3"),
                    "sl": signal.get("sl"),
                    "score": adaptive_score,
                    "conviction": conviction_grade or conviction_score,
                    "strategy": signal.get("strategy", "UNKNOWN"),
                    "regime": signal.get("regime", "UNKNOWN"),
                })
            except Exception as e:
                forward_record = {"ok": False, "error": str(e)}
        else:
            forward_record = {"ok": False, "reason": "ForwardTestEngine unavailable"}

        decision_log.append({"step": "forward_test", "result": forward_record})

        allow = len(blocked_reasons) == 0
        return {
            "ok": True,
            "symbol": symbol,
            "allow_send": allow,
            "action": "SEND_LINE" if allow else "BLOCK",
            "base_score": round(base_score, 2),
            "adaptive_score": round(adaptive_score, 2),
            "position_size_multiplier": size.get("multiplier", 1.0),
            "blocked_reasons": blocked_reasons,
            "decision_log": decision_log,
            "forward_test_days": self.forward_test_days,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }


def demo_signal() -> Dict[str, Any]:
    return {
        "symbol": "NVDA",
        "side": "CALL",
        "price": 214.2,
        "entry": 214.2,
        "tp1": 216.0,
        "tp2": 218.5,
        "tp3": 221.0,
        "sl": 212.8,
        "score": 91,
        "rsi": 62,
        "rvol": 2.4,
        "atr": 3.1,
        "option_flow_score": 88,
        "news_sentiment_score": 70,
        "breadth_score": 76,
        "sector_rotation_score": 84,
        "conviction_score": 82,
        "conviction_grade": "HIGH",
        "strategy": "VWAP_RECLAIM",
        "regime": "UPTREND",
        "source": "demo",
    }
