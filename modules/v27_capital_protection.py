from datetime import datetime, timezone

class DataQualityGuard:
    def validate_quote(self, quote):
        problems = []
        price = quote.get("price") or quote.get("close")
        prev = quote.get("previous_close")
        try:
            price = float(price)
            if price <= 0: problems.append("price <= 0")
        except Exception:
            problems.append("price missing/invalid")
        try:
            if prev and price:
                prev = float(prev)
                if prev > 0 and abs((price - prev) / prev * 100) > 25:
                    problems.append("price jump >25%")
        except Exception:
            pass
        if not str(quote.get("source", "")).strip():
            problems.append("source missing")
        return {"ok": not problems, "problems": problems, "checked_at": datetime.now(timezone.utc).isoformat()}

    def validate_indicator_set(self, data):
        problems = []
        try:
            rsi = data.get("rsi")
            if rsi is not None and not (0 <= float(rsi) <= 100): problems.append("RSI out of range")
        except Exception:
            problems.append("RSI invalid")
        try:
            rvol = data.get("rvol")
            if rvol is not None and float(rvol) < 0: problems.append("RVOL negative")
        except Exception:
            problems.append("RVOL invalid")
        try:
            atr = data.get("atr")
            if atr is not None and float(atr) < 0: problems.append("ATR negative")
        except Exception:
            problems.append("ATR invalid")
        return {"ok": not problems, "problems": problems, "checked_at": datetime.now(timezone.utc).isoformat()}

    def should_block_alert(self, quote, indicators):
        q = self.validate_quote(quote)
        i = self.validate_indicator_set(indicators)
        problems = q["problems"] + i["problems"]
        return {"block": bool(problems), "reason": "; ".join(problems) if problems else "PASS", "quality": {"quote": q, "indicators": i}}
class CapitalProtection:

    def __init__(self, max_daily_loss_pct=3.0, max_drawdown_pct=8.0):
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_drawdown_pct = max_drawdown_pct

    def check(self, daily_loss_pct=0.0, drawdown_pct=0.0):
        allowed = daily_loss_pct < self.max_daily_loss_pct and drawdown_pct < self.max_drawdown_pct
        return {
            "allowed": allowed,
            "daily_loss_pct": daily_loss_pct,
            "drawdown_pct": drawdown_pct,
            "reason": None if allowed else "capital_protection_triggered",
        }

    def allow_trade(self, daily_loss_pct=0.0, drawdown_pct=0.0):
        return self.check(daily_loss_pct, drawdown_pct)["allowed"]
