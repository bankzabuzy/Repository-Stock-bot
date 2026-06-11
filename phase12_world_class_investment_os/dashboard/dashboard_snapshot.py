class DashboardSnapshot:
    def build(self, decision):
        return {
            "version": "V1200",
            "mode": decision.get("mode", "shadow"),
            "selected_symbols": decision.get("selected_symbols", []),
            "target_weights": decision.get("target_weights", {}),
            "risk_allowed": decision.get("risk", {}).get("allowed", False),
            "alpha_scores": decision.get("alpha_scores", {}),
            "explanation": decision.get("explanation", {})
        }
