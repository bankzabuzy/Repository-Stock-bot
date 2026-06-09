V41_VERSION = "V41_TOP5_INSTITUTIONAL"

def clamp_score(score):
    return max(0, min(score, 95))


def risk_grade(score):
    if score >= 90:
        return "A"
    elif score >= 85:
        return "A-"
    elif score >= 80:
        return "B+"
    elif score >= 75:
        return "B"
    else:
        return "C"


def confidence(score):
    return min(95, max(40, score - 5))


def build_reason(symbol, regime):
    reasons = []

    if "STRONG" in regime:
        reasons.append("Trend แข็งแรง")

    if symbol in ["TSM", "QQQ"]:
        reasons.append("Liquidity สูง")

    if symbol == "AAOI":
        reasons.append("หุ้นผันผวนสูง")

    return reasons
def build_top5():
    data = [
        ("TSM", 91, "STRONG UPTREND"),
        ("QQQ", 88, "UPTREND"),
        ("SCB", 86, "STRONG UPTREND"),
        ("AAOI", 83, "UPTREND"),
        ("TJX", 82, "STRONG UPTREND")
    ]

    results = []

    for symbol, score, regime in data:

        score = clamp_score(score)

        results.append({
            "symbol": symbol,
            "score": score,
            "regime": regime,
            "confidence": confidence(score),
            "risk_grade": risk_grade(score),
            "reason": build_reason(symbol, regime)
        })

    return sorted(results, key=lambda x: x["score"], reverse=True)  
