class ExplainabilityEngine:
    def explain(self, decision):
        reasons = []
        regime = decision.get("market_regime")
        if regime:
            reasons.append(f"Market regime = {regime}")
        if decision.get("macro_regime") == "INFLATION_DEFENSE":
            reasons.append("Inflation defense active: prefer gold/quality/cash buffer")
        selected = decision.get("selected_symbols", [])
        if selected:
            reasons.append("Selected assets: " + ", ".join(selected))
        if decision.get("risk_blocks"):
            reasons.append("Risk blocks: " + ", ".join(decision["risk_blocks"]))
        if not reasons:
            reasons.append("Decision generated from alpha, macro, risk, and behavioral checks")
        return {"plain_thai_summary": " | ".join(reasons), "reasons": reasons}
