class WorldClassRiskGate:
    def __init__(self, config):
        self.limits = config.get("risk_limits", {})

    def check(self, portfolio, snapshot, account, behavior):
        blocks = []
        warnings = []
        dd = float(account.get("drawdown_pct", 0))
        daily = float(account.get("daily_loss_pct", 0))
        if dd >= self.limits.get("max_drawdown_pause_pct", 0.08):
            blocks.append("max_drawdown_pause")
        if daily >= self.limits.get("max_daily_loss_pct", 0.02):
            blocks.append("daily_loss_limit")
        if behavior.get("warnings"):
            warnings.extend(behavior["warnings"])
        for sym, w in portfolio.get("target_weights", {}).items():
            if float(snapshot[sym].get("liquidity_score", 0)) < self.limits.get("min_liquidity_score", 60):
                blocks.append(f"low_liquidity:{sym}")
            if w > self.limits.get("max_sector_exposure_pct", 0.25):
                warnings.append(f"concentration_warning:{sym}")
        return {"allowed": len(blocks)==0, "blocks": blocks, "warnings": warnings}
