class BehaviorGuard:
    def evaluate(self, context):
        warnings = []
        if context.get("after_large_loss", False):
            warnings.append("revenge_trading_risk")
        if context.get("too_many_trades_today", 0) > 10:
            warnings.append("overtrading_risk")
        if context.get("manual_override_count", 0) > 3:
            warnings.append("manual_override_risk")
        return {"ok": len(warnings) == 0, "warnings": warnings}
