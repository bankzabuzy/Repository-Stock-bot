class AlphaDiscoveryPlus:
    def score(self, snapshot, macro_view, crowd_view):
        scores = {}
        for sym, d in snapshot.items():
            trend = float(d.get("trend_score", 50))
            liquidity = float(d.get("liquidity_score", 50))
            vol = float(d.get("volatility_score", 50))
            crowd = float(crowd_view.get("crowd_score", 50))
            macro_penalty = max(float(macro_view.get("macro_risk_score", 50))-50, 0) * 0.15
            score = trend*0.35 + liquidity*0.25 + (100-vol)*0.20 + crowd*0.20 - macro_penalty
            if macro_view.get("macro_regime") == "INFLATION_DEFENSE" and sym in {"GLD", "XAUUSD"}:
                score += 8
            scores[sym] = round(max(0, min(100, score)), 2)
        return scores
