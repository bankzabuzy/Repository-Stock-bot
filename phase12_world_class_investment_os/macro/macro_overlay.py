class MacroOverlay:
    def analyze(self, macro):
        cpi = float(macro.get("cpi_yoy", 2.5))
        rates = float(macro.get("policy_rate", 4.5))
        usd = float(macro.get("usd_strength", 50))
        risk = 50.0
        notes = []
        if cpi > 3.0:
            risk += 15
            notes.append("inflation_above_target")
        if rates > 5.0:
            risk += 10
            notes.append("tight_policy")
        if usd > 65:
            risk += 5
            notes.append("strong_usd_pressure")
        regime = "INFLATION_DEFENSE" if cpi > 3.0 else "NORMAL"
        return {"macro_risk_score": min(risk, 100), "macro_regime": regime, "notes": notes}
