from dataclasses import dataclass
from typing import Dict

@dataclass
class MarketState:
    regime: str
    risk_score: float
    volatility_score: float
    liquidity_score: float
    trend_score: float
    macro_score: float
    notes: str = ""

class MarketAnalyzer:
    def analyze(self, features: Dict) -> MarketState:
        vol = float(features.get("volatility_score", 50))
        trend = float(features.get("trend_score", 50))
        liquidity = float(features.get("liquidity_score", 70))
        macro = float(features.get("macro_score", 50))
        risk = max(0, min(100, (trend * 0.35 + liquidity * 0.25 + macro * 0.25 + (100-vol) * 0.15)))
        if risk >= 65 and vol < 70:
            regime = "RISK_ON"
        elif risk <= 40 or vol >= 80:
            regime = "RISK_OFF"
        else:
            regime = "NEUTRAL"
        return MarketState(regime, risk, vol, liquidity, trend, macro, "deterministic safe analyzer")
