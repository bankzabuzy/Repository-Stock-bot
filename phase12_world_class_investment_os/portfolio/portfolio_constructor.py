class PortfolioConstructor:
    def construct(self, alpha_scores, snapshot, max_names=5):
        ranked = sorted(alpha_scores.items(), key=lambda kv: kv[1], reverse=True)[:max_names]
        raw = {}
        for sym, score in ranked:
            liq = float(snapshot[sym].get("liquidity_score", 60))
            raw[sym] = max(1.0, score) * (liq/100)
        total = sum(raw.values()) or 1.0
        weights = {k: round(v/total, 4) for k, v in raw.items()}
        return {"selected_symbols": list(weights.keys()), "target_weights": weights}
