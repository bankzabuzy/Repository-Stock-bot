import os
import hmac
import hashlib
import base64
import time
import threading
from datetime import datetime, timedelta

import requests
from flask import Flask, request, abort

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
PORT = int(os.getenv("PORT", "3000"))

WATCHLIST = [
    x.strip().upper()
    for x in os.getenv("WATCHLIST", "NVDA,AAPL,TSLA,QQQ,SPY,GOLD,AOT,PTT,SCB").split(",")
    if x.strip()
]

ALLOWED_USERS = [
    x.strip()
    for x in os.getenv("ALLOWED_USERS", "").split(",")
    if x.strip()
]

ALERT_USER_IDS = [
    x.strip()
    for x in os.getenv("ALERT_USER_IDS", "").split(",")
    if x.strip()
]

ENABLE_AUTO_ALERTS = os.getenv("ENABLE_AUTO_ALERTS", "true").lower() == "true"
ALERT_EVERY_MINUTES = int(os.getenv("ALERT_EVERY_MINUTES", "360"))

THAI_SYMBOL_MAP = {
    "SCB": ("SCB", "SET", "THB"),
    "AOT": ("AOT", "SET", "THB"),
    "PTT": ("PTT", "SET", "THB"),
    "CPALL": ("CPALL", "SET", "THB"),
    "KBANK": ("KBANK", "SET", "THB"),
    "BBL": ("BBL", "SET", "THB"),
    "DELTA": ("DELTA", "SET", "THB"),
    "ADVANC": ("ADVANC", "SET", "THB"),
    "TRUE": ("TRUE", "SET", "THB"),
    "BDMS": ("BDMS", "SET", "THB"),
    "MINT": ("MINT", "SET", "THB"),
    "PTTEP": ("PTTEP", "SET", "THB"),
    "GULF": ("GULF", "SET", "THB"),
    "CPAXT": ("CPAXT", "SET", "THB"),
    "BEM": ("BEM", "SET", "THB"),
    "KTB": ("KTB", "SET", "THB"),
    "KTC": ("KTC", "SET", "THB"),
    "OR": ("OR", "SET", "THB"),
}

GOLD_WORDS = {"GOLD", "ทอง", "ทองคำ", "XAUUSD", "XAU/USD"}
US_INDEX_SYMBOLS = {
    "SPX": "SPY",
    "NASDAQ": "QQQ",
    "NDX": "QQQ",
    "DOW": "DIA",
    "RUSSELL": "IWM",
}


def now_text():
    return (datetime.utcnow() + timedelta(hours=7)).strftime("%d/%m/%Y %H:%M")


def safe_float(value, default=None):
    try:
        return float(value)
    except Exception:
        return default


def fmt_num(value, decimals=2):
    if value is None:
        return "N/A"
    try:
        return f"{float(value):,.{decimals}f}"
    except Exception:
        return "N/A"


def normalize_asset(user_text):
    raw = user_text.strip()
    key = raw.upper().replace(" ", "")

    if raw in GOLD_WORDS or key in GOLD_WORDS:
        return {
            "display": "ทองคำ / XAUUSD",
            "symbol": "XAU/USD",
            "exchange": None,
            "currency": "USD",
            "asset_type": "GOLD",
            "news_symbol": "XAU",
        }

    if key in US_INDEX_SYMBOLS:
        key = US_INDEX_SYMBOLS[key]

    if key.endswith(".BK"):
        key = key.replace(".BK", "")

    if key.endswith(".SET"):
        key = key.replace(".SET", "")

    if key in THAI_SYMBOL_MAP:
        symbol, exchange, currency = THAI_SYMBOL_MAP[key]
        return {
            "display": f"{symbol}.SET",
            "symbol": symbol,
            "exchange": exchange,
            "currency": currency,
            "asset_type": "THAI_STOCK",
            "news_symbol": symbol,
        }

    return {
        "display": key,
        "symbol": key,
        "exchange": None,
        "currency": "USD",
        "asset_type": "US_STOCK",
        "news_symbol": key,
    }


def td_params(asset, interval=None, outputsize=None):
    params = {
        "symbol": asset["symbol"],
        "apikey": TWELVEDATA_API_KEY,
    }

    if interval:
        params["interval"] = interval

    if outputsize:
        params["outputsize"] = outputsize

    if asset["asset_type"] == "THAI_STOCK":
        params["exchange"] = "SET"
    elif asset.get("exchange"):
        params["exchange"] = asset["exchange"]

    return params


def td_get_quote(asset):
    if not TWELVEDATA_API_KEY:
        raise RuntimeError("ยังไม่ได้ตั้งค่า TWELVEDATA_API_KEY")

    url = "https://api.twelvedata.com/quote"
    r = requests.get(url, params=td_params(asset), timeout=20)
    data = r.json()

    if data.get("status") == "error" or "close" not in data:
        msg = data.get("message", "")
        raise RuntimeError(
            f"ไม่พบข้อมูลจาก Twelve Data สำหรับ {asset['display']}\n"
            f"สาเหตุที่เป็นไปได้: symbol ไม่รองรับ / API package ไม่ครอบคลุม / ตลาดปิด / key ผิด\n"
            f"รายละเอียด: {msg}"
        )

    return data


def td_get_series(asset, interval="15min", outputsize=160):
    url = "https://api.twelvedata.com/time_series"
    r = requests.get(
        url,
        params=td_params(asset, interval=interval, outputsize=outputsize),
        timeout=20,
    )
    data = r.json()

    if data.get("status") == "error" or "values" not in data:
        return [], [], [], [], []

    values = list(reversed(data["values"]))
    closes, highs, lows, opens, volumes = [], [], [], [], []

    for v in values:
        close = safe_float(v.get("close"))
        high = safe_float(v.get("high"))
        low = safe_float(v.get("low"))
        open_ = safe_float(v.get("open"))
        volume = safe_float(v.get("volume"), 0)

        if close is not None and high is not None and low is not None and open_ is not None:
            closes.append(close)
            highs.append(high)
            lows.append(low)
            opens.append(open_)
            volumes.append(volume or 0)

    return closes, highs, lows, opens, volumes


def ema(values, period):
    if len(values) < period:
        return None

    k = 2 / (period + 1)
    result = values[0]

    for price in values[1:]:
        result = price * k + result * (1 - k)

    return result


def calc_rsi(values, period=14):
    if len(values) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(-period, 0):
        diff = values[i] - values[i - 1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_atr(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return None

    true_ranges = []

    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return None

    return sum(true_ranges[-period:]) / period


def analyze_signal(asset, quote, closes, highs, lows, opens, volumes):
    price = safe_float(quote.get("close"))
    previous_close = safe_float(quote.get("previous_close"))
    change = safe_float(quote.get("change"))
    percent_change = safe_float(quote.get("percent_change"))

    ema6 = ema(closes, 6)
    ema12 = ema(closes, 12)
    ema50 = ema(closes, 50)
    rsi = calc_rsi(closes)
    atr = calc_atr(highs, lows, closes)

    score = 50
    reasons = []

    if price and ema6 and ema12:
        if price > ema6 > ema12:
            score += 15
            reasons.append("ราคาอยู่เหนือ EMA6 และ EMA12")
        elif price < ema6 < ema12:
            score -= 15
            reasons.append("ราคาอยู่ใต้ EMA6 และ EMA12")

    if ema12 and ema50:
        if ema12 > ema50:
            score += 10
            reasons.append("แนวโน้มกลางยังเป็นบวก")
        elif ema12 < ema50:
            score -= 10
            reasons.append("แนวโน้มกลางยังเป็นลบ")

    if rsi is not None:
        if rsi >= 70:
            score -= 8
            reasons.append("RSI สูง ระวังพักตัว")
        elif rsi <= 30:
            score += 8
            reasons.append("RSI ต่ำ มีโอกาสรีบาวด์")
        elif 45 <= rsi <= 60:
            score += 5
            reasons.append("RSI อยู่ในโซนสมดุล")

    if percent_change is not None:
        if percent_change > 1:
            score += 8
            reasons.append("โมเมนตัมวันล่าสุดเป็นบวก")
        elif percent_change < -1:
            score -= 8
            reasons.append("โมเมนตัมวันล่าสุดเป็นลบ")

    score = max(0, min(100, score))

    if score >= 70:
        bias = "BULLISH / ฝั่งซื้อได้เปรียบ"
    elif score <= 40:
        bias = "BEARISH / ฝั่งขายได้เปรียบ"
    else:
        bias = "NEUTRAL / รอดูจังหวะ"

    if price and atr:
        support = price - atr
        resistance = price + atr
        stop_loss = price - atr * 1.2
        take_profit = price + atr * 1.8
    else:
        support = resistance = stop_loss = take_profit = None

    return {
        "price": price,
        "previous_close": previous_close,
        "change": change,
        "percent_change": percent_change,
        "ema6": ema6,
        "ema12": ema12,
        "ema50": ema50,
        "rsi": rsi,
        "atr": atr,
        "score": score,
        "bias": bias,
        "support": support,
        "resistance": resistance,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "reasons": reasons,
    }


def fetch_news(asset):
    if not FINNHUB_API_KEY:
        return "ยังไม่ได้ตั้งค่า FINNHUB_API_KEY จึงยังไม่ดึงข่าว", 0

    if asset["asset_type"] == "THAI_STOCK":
        return "ข่าวหุ้นไทยยังไม่ได้เชื่อม API ข่าวเฉพาะ SET", 0

    if asset["asset_type"] == "GOLD":
        return "ทองคำควรดูร่วมกับ USD, Bond Yield, เงินเฟ้อ, FED และดอลลาร์สหรัฐ", 0

    try:
        today = datetime.utcnow().date()
        week_ago = today - timedelta(days=7)

        url = "https://finnhub.io/api/v1/company-news"
        r = requests.get(
            url,
            params={
                "symbol": asset["news_symbol"],
                "from": week_ago.isoformat(),
                "to": today.isoformat(),
                "token": FINNHUB_API_KEY,
            },
            timeout=20,
        )

        items = r.json()
        if not isinstance(items, list) or not items:
            return "ไม่พบข่าวล่าสุดจาก Finnhub", 0

        headlines = []
 
