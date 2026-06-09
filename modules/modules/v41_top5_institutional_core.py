from datetime import datetime
import math

V41_VERSION = "V41_TOP5_INSTITUTIONAL_RANKING_ENGINE"

def clamp(value, low=0, high=100):
    try:
        return max(low, min(high, float(value)))
    except Exception:
        return 0

def regime_score(regime):
    text = str(regime or "").upper()
    if "STRONG UPTREND" in text:
        return 100
    if "UPTREND" in text:
        return 85
    if "SIDEWAY" in text or "NEUTRAL" in text:
        return 55
    if "DOWNTREND" in text:
        return 20
    return 50

def signal_score(signal):
    text = str(signal or "").upper()
    if "BUY" in text:
        return 100
    if "WATCH_BUY" in text:
        return 75
    if "HOLD" in text or "NEUTRAL" in text:
        return 50
    if "SELL" in text:
        return 10
    return 50

def rsi_score(rsi):
    rsi = clamp(rsi)
    if 45 <= rsi <= 65:
        return 90
    if 35 <= rsi < 45:
        return 70
    if 65 < rsi <= 72:
        return 65
    if rsi > 75:
        return 25
    return 50

def rvol_score(rvol):
    try:
        rvol = float(rvol)
    except Exception:
        return 50
    if rvol >= 1.5:
        return 90
    if rvol >= 1.0:
        return 75
    if rvol >= 0.7:
        return 55
    return 35

def atr_risk_score(atr_pct):
    try:
        atr_pct = float(atr_pct)
    except Exception:
        return 60
    if atr_pct <= 2:
        return 90
    if atr_pct <= 4:
        return 70
    if atr_pct <= 7:
        return 45
    return 20

def calculate_v41_score(item):
    base_score = clamp(item.get("score", item.get("ai_score", 50)))
    probability = clamp(item.get("probability", item.get("probability_pct", base_score)))
    confidence = clamp(item.get("confidence", item.get("confidence_pct", probability)))

    trend = regime_score(item.get("regime", item.get("market_regime", "")))
    sig = signal_score(item.get("signal", ""))
    rsi = rsi_score(item.get("rsi14", item.get("rsi", 50)))
    rvol = rvol_score(item.get("rvol", 1))
    atr = atr_risk_score(item.get("atr_pct", 3))

    institutional_score = (
        trend * 0.25 +
        sig * 0.15 +
        base_score * 0.15 +
        probability * 0.15 +
        confidence * 0.10 +
        rsi * 0.08 +
        rvol * 0.07 +
        atr * 0.05
    )

    return round(clamp(institutional_score), 2)

def classify_pick(score):
    if score >= 85:
        return "A+ / เข้มข้นมาก"
    if score >= 75:
        return "A / น่าสนใจ"
    if score >= 65:
        return "B / เฝ้าดู"
    return "C / ยังไม่เด่น"

def build_reason(item, score):
    reasons = []
    regime = str(item.get("regime", item.get("market_regime", "")))
    signal = str(item.get("signal", ""))

    if "UPTREND" in regime.upper():
        reasons.append("แนวโน้มเป็นขาขึ้น")
    if "BUY" in signal.upper():
        reasons.append("สัญญาณฝั่งซื้อเด่น")
    if score >= 85:
        reasons.append("คะแนนรวมผ่านเกณฑ์เข้มข้น")
    if item.get("rvol"):
        reasons.append("มี Volume ประกอบ")
    if not reasons:
        reasons.append("ผ่านการจัดอันดับเชิงระบบ")

    return " / ".join(reasons)

def rank_top5_institutional(items, limit=5):
    ranked = []

    for item in items:
        symbol = item.get("symbol")
        if not symbol:
            continue

        score = calculate_v41_score(item)

        # ตัดตัวที่อ่อนมากออก
        if score < 60:
            continue

        ranked.append({
            "symbol": symbol,
            "score": score,
            "class": classify_pick(score),
            "signal": item.get("signal", "N/A"),
            "regime": item.get("regime", item.get("market_regime", "N/A")),
            "confidence": item.get("confidence", item.get("confidence_pct", item.get("probability", score))),
            "price": item.get("price"),
            "reason": build_reason(item, score),
            "raw": item
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:limit]

def format_top5_line_message(picks):
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    if not picks:
        return (
            "🏆 V41 TOP5 Institutional\n\n"
            "วันนี้ยังไม่มีหุ้นที่ผ่านเกณฑ์เข้มข้น\n"
            f"เวลาไทย: {now}"
        )

    lines = ["🏆 V41 TOP5 Institutional Picks", ""]

    for i, p in enumerate(picks, 1):
        lines.append(
            f"{i}. {p['symbol']} | {p['score']}/100\n"
            f"   Signal: {p['signal']}\n"
            f"   Regime: {p['regime']}\n"
            f"   Class: {p['class']}\n"
            f"   เหตุผล: {p['reason']}"
        )

    lines.append("")
    lines.append(f"เวลาไทย: {now}")
    lines.append("หมายเหตุ: ใช้ V41 Institutional Ranking ไม่ใช่ V8.1")
    lines.append("ใช้เป็นตัวกรอง ไม่ใช่คำสั่งซื้ออัตโนมัติ")

    return "\n".join(lines)
