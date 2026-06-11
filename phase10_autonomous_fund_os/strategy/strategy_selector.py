class StrategySelector:
    def select(self, market_state, alpha_scores):
        alpha_scores = alpha_scores or {}
        if market_state.regime == "RISK_ON":
            preferred = ["momentum", "ai_theme", "semiconductor_theme", "trend"]
        elif market_state.regime == "RISK_OFF":
            preferred = ["gold_hedge", "cash", "low_volatility", "mean_reversion"]
        else:
            preferred = ["quality", "relative_strength", "mean_reversion"]
        ranked = sorted(preferred, key=lambda k: alpha_scores.get(k, 50), reverse=True)
        return {"regime": market_state.regime, "selected": ranked[:3], "weights": self._weights(ranked[:3], alpha_scores)}

    def _weights(self, selected, scores):
        if not selected:
            return {}
        raw = {s: max(1.0, float(scores.get(s, 50))) for s in selected}
        total = sum(raw.values())
        return {k: round(v/total, 4) for k, v in raw.items()}
