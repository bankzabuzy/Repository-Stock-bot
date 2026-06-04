from datetime import datetime, timezone

class CapitalProtection:
    def __init__(self, max_alerts_per_day=5, max_daily_loss_r=-3.0, max_consecutive_losses=3, min_breadth_score=40.0, max_vix=30.0):
        self.max_alerts_per_day = max_alerts_per_day
        self.max_daily_loss_r = max_daily_loss_r
        self.max_consecutive_losses = max_consecutive_losses
        self.min_breadth_score = min_breadth_score
        self.max_vix = max_vix

    def evaluate(self, stats):
        reasons = []
        if int(stats.get("alerts_today", 0) or 0) >= self.max_alerts_per_day:
            reasons.append("เกินจำนวน Alert ต่อวัน")
        if float(stats.get("daily_return_r", 0) or 0) <= self.max_daily_loss_r:
            reasons.append("ขาดทุนเกิน Daily Loss Limit")
        if int(stats.get("consecutive_losses", 0) or 0) >= self.max_consecutive_losses:
            reasons.append("แพ้ติดกันเกินกำหนด")
        if float(stats.get("breadth_score", 50) or 50) < self.min_breadth_score:
            reasons.append("Market Breadth อ่อนแอมาก")
        if float(stats.get("vix", 0) or 0) > self.max_vix:
            reasons.append("VIX สูงผิดปกติ")
        return {"ok": not reasons, "action": "BLOCK" if reasons else "ALLOW", "reasons": reasons, "checked_at": datetime.now(timezone.utc).isoformat()}

    def position_size_multiplier(self, stats):
        multiplier = 1.0
        reasons = []
        if float(stats.get("breadth_score", 50) or 50) < 50:
            multiplier *= 0.5; reasons.append("ลดขนาดไม้เพราะ Breadth ต่ำ")
        if float(stats.get("vix", 0) or 0) > 25:
            multiplier *= 0.5; reasons.append("ลดขนาดไม้เพราะ VIX สูง")
        if float(stats.get("daily_return_r", 0) or 0) < 0:
            multiplier *= 0.75; reasons.append("ลดขนาดไม้เพราะวันนี้ติดลบ")
        return {"multiplier": round(multiplier, 2), "reasons": reasons or ["normal size"]}
