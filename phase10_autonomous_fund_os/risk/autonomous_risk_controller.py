class AutonomousRiskController:
    def __init__(self, config):
        self.config = config
        self.limits = config.get("risk_limits", {})
    def check(self, decision, account):
        blocks = []
        if float(account.get("drawdown_pct", 0)) >= self.limits.get("max_drawdown_pause_pct", 0.08):
            blocks.append("portfolio_drawdown_pause")
        if float(account.get("daily_loss_pct", 0)) >= self.limits.get("max_daily_loss_pct", 0.02):
            blocks.append("daily_loss_limit")
        if decision.get("confidence", "B") not in ["A+", "A"] and decision.get("target_mode") == "live":
            blocks.append("confidence_too_low_for_live")
        if decision.get("liquidity_score", 100) < self.limits.get("min_liquidity_score", 60):
            blocks.append("liquidity_too_low")
        return {"allowed": len(blocks) == 0, "blocks": blocks}
