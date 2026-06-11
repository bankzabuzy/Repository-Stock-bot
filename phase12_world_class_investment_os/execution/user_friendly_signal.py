class UserFriendlySignal:
    def build(self, portfolio, alpha_scores, xai, risk):
        lines = []
        for sym in portfolio.get("selected_symbols", []):
            score = alpha_scores.get(sym, 0)
            action = "WATCH"
            if score >= 75 and risk.get("allowed"):
                action = "BUY_ZONE"
            elif score >= 60:
                action = "WAIT_CONFIRM"
            lines.append({"symbol": sym, "action": action, "score": score})
        return {
            "signals": lines,
            "summary": xai.get("plain_thai_summary", ""),
            "risk_allowed": risk.get("allowed", False),
            "risk_blocks": risk.get("blocks", []),
            "risk_warnings": risk.get("warnings", [])
        }
