from datetime import datetime, timezone

class OutcomeTracker:
    def evaluate_price(self, signal, current_price):
        side = str(signal.get("side", "CALL")).upper()
        entry = float(signal.get("entry", 0) or 0)
        tp1 = float(signal.get("tp1", 0) or 0)
        tp2 = float(signal.get("tp2", 0) or 0)
        tp3 = float(signal.get("tp3", 0) or 0)
        sl = float(signal.get("sl", 0) or 0)
        price = float(current_price or 0)
        outcome = "OPEN"
        return_r = 0.0

        if side in {"CALL", "LONG", "BUY"}:
            if tp3 and price >= tp3: outcome, return_r = "TP3", 3.0
            elif tp2 and price >= tp2: outcome, return_r = "TP2", 2.0
            elif tp1 and price >= tp1: outcome, return_r = "TP1", 1.0
            elif sl and price <= sl: outcome, return_r = "SL", -1.0
            elif entry and sl: return_r = round((price - entry) / max(entry - sl, 0.0001), 2)
        else:
            if tp3 and price <= tp3: outcome, return_r = "TP3", 3.0
            elif tp2 and price <= tp2: outcome, return_r = "TP2", 2.0
            elif tp1 and price <= tp1: outcome, return_r = "TP1", 1.0
            elif sl and price >= sl: outcome, return_r = "SL", -1.0
            elif entry and sl: return_r = round((entry - price) / max(sl - entry, 0.0001), 2)

        return {
            "ok": True,
            "symbol": signal.get("symbol"),
            "current_price": price,
            "outcome": outcome,
            "return_r": return_r,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def time_stop_check(self, age_minutes, max_minutes=240):
        return {
            "time_stop": age_minutes >= max_minutes,
            "reason": "หมดเวลา signal" if age_minutes >= max_minutes else "ยังไม่หมดเวลา",
        }
class DataQualityGuard:

    def __init__(self):
        self.errors = []

    def check_price(self, symbol, price):
        ok = price is not None and price > 0
        return {
            "symbol": symbol,
            "ok": ok,
            "reason": None if ok else "invalid_price",
        }

    def check_series(self, symbol, closes):
        ok = bool(closes) and len(closes) >= 20
        return {
            "symbol": symbol,
            "ok": ok,
            "reason": None if ok else "not_enough_data",
        }

    def validate(self, symbol, price=None, closes=None):
        price_check = self.check_price(symbol, price)
        series_check = self.check_series(symbol, closes or [])
        ok = price_check["ok"] and series_check["ok"]
        return {
            "symbol": symbol,
            "ok": ok,
            "checks": {
                "price": price_check,
                "series": series_check,
            },
        }
