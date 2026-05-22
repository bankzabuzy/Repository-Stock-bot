import os
import hmac
import hashlib
import base64
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path

import requests
from flask import Flask, request, abort, send_from_directory
import matplotlib.pyplot as plt
import pandas as pd

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_USER_ID = os.getenv("LINE_USER_ID", "")
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
WATCHLIST = os.getenv("WATCHLIST", "NVDA,AAPL,TSLA,GOLD").split(",")
PORT = int(os.getenv("PORT", "3000"))

REPORT_DIR = Path("reports")
REPORT_DIR.mkdir(exist_ok=True)

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
}

GOLD_WORDS = {"GOLD", "ทอง", "ทองคำ", "XAUUSD", "XAU/USD"}

last_alerts = {}


def now_text():
    thai_time = datetime.utcnow() + timedelta(hours=7)
    return thai_time.strftime("%d/%m/%Y %H:%M")


@app.route("/health")
def health():
    return "OK"


@app.route("/test-alert")
def test_alert():
    push_line(LINE_USER_ID, "✅ ทดสอบแจ้งเตือน LINE สำเร็จ")
    return "OK"


@app.route("/reports/<path:filename>")
def report_file(filename):
    return send_from_directory(REPORT_DIR, filename)

def push_line(to, text):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("LINE_CHANNEL_ACCESS_TOKEN missing")
        return

    r = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        },
        json={
            "to": to,
            "messages": [{"type": "text", "text": text[:4900]}]
        },
        timeout=20
    )

    print("PUSH STATUS:", r.status_code)
    print("PUSH RESPONSE:", r.text)
@app.route("/line/webhook", methods=["POST"])
def line_webhook():
    verify_line_signature()
    body = request.get_json(force=True, silent=True) or {}
    events = body.get("events", [])

    for event in events:
        if event.get("type") != "message":
            continue

        message = event.get("message", {})
        if message.get("type") != "text":
            continue

        reply_token = event.get("replyToken")
        user_text = message.get("text", "").strip()
        if user_text in ["ทองคำ", "ทอง", "gold", "GOLD"]:
            user_text = "XAU/USD"
        try:
            result = analyze_asset(user_text)
            push_line(LINE_USER_ID, result["text"])

        except Exception as e:
            print("ERROR:", repr(e))
            push_line(
    LINE_USER_ID,
    f"ระบบยังอ่านคำสั่งนี้ไม่ได้ครับ\nลองพิมพ์ เช่น NVDA, AAPL, SCB, AOT, ทองคำ, GOLD\n\nError: {e}"
)

    return "OK"


def verify_line_signature():
    if not LINE_CHANNEL_SECRET:
        print("WARNING: LINE_CHANNEL_SECRET not set; signature verification skipped")
        return

    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data()
    hash_value = hmac.new(
        LINE_CHANNEL_SECRET.encode("utf-8"),
        body,
        hashlib.sha256
    ).digest()
    expected = base64.b64encode(hash_value).decode("utf-8")

    if not hmac.compare_digest(signature, expected):
        abort(400)


def normalize_asset(user_text):
    raw = user_text.strip()
    key = raw.upper().replace(" ", "")

    if raw in GOLD_WORDS or key in GOLD_WORDS:
        return {
            "display": "ทองคำ / XAUUSD",
            "symbol": "XAU/USD",
            "exchange": None,
            "currency": "THB",
            "asset_type": "GOLD"
        }

    if key in THAI_SYMBOL_MAP:
        symbol, exchange, currency = THAI_SYMBOL_MAP[key]
        return {
            "display": f"{symbol}.SET",
            "symbol": symbol,
            "exchange": exchange,
            "currency": currency,
            "asset_type": "THAI_STOCK"
        }

    if key.endswith(".BK"):
        symbol = key.replace(".BK", "")
        return {
            "display": f"{symbol}.SET",
            "symbol": symbol,
            "exchange": "SET",
            "currency": "THB",
            "asset_type": "THAI_STOCK"
        }

    return {
        "display": key,
        "symbol": key,
        "exchange": None,
        "currency": "USD",
        "asset_type": "US_STOCK"
    }


def td_get_quote(asset):
    if not TWELVEDATA_API_KEY:
        raise RuntimeError("ยังไม่ได้ตั้งค่า TWELVEDATA_API_KEY")

    params = {
        "symbol": asset["symbol"],
        "apikey": TWELVEDATA_API_KEY
    }

    if asset.get("exchange"):
        params["exchange"] = asset["exchange"]

    r = requests.get("https://api.twelvedata.com/quote", params=params, timeout=20)
    data = r.json()

    if data.get("status") == "error" or "close" not in data:
        raise RuntimeError(f"ไม่พบข้อมูลจาก Twelve Data สำหรับ {asset['display']}")

    return data


def td_get_series(asset):
    params = {
        "symbol": asset["symbol"],
        "interval": "15min",
        "outputsize": 120,
        "apikey": TWELVEDATA_API_KEY
    }

    if asset.get("exchange"):
        params["exchange"] = asset["exchange"]

    r = requests.get("https://api.twelvedata.com/time_series", params=params, timeout=20)
    data = r.json()

    if data.get("status") == "error" or "values" not in data:
        return [], []

    values = list(reversed(data["values"]))
    closes, volumes = [], []

    for v in values:
        try:
            closes.append(float(v["close"]))
            volumes.append(float(v.get("volume", 0) or 0))
        except Exception:
            pass

    
        
    return closes, volumes


def usd_to_thb():
    try:
        r = requests.get(
            "https://api.twelvedata.com/exchange_rate",
            params={
                "symbol": "USD/THB",
                "apikey": TWELVEDATA_API_KEY
            },
            timeout=10
        )
        data = r.json()
        return float(data.get("rate", 36))
    except Exception:
        return 36


def ema(values, period):
    if len(values) < period:
        return None

    k = 2 / (period + 1)
    val = sum(values[:period]) / period

    for price in values[period:]:
        val = price * k + val * (1 - k)

    return val


def sma(values, period):
    if len(values) < period:
        return None

    return sum(values[-period:]) / period


def rsi(values, period=14):
    if len(values) <= period:
        return None

    gains, losses = [], []

    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def fmt(value, unit):
    if value is None:
        return "N/A"

    return f"{unit}{value:,.2f}"


def ai_trend_analysis(price, ema6, ema12, sma20, rsi14):
    if ema6 and ema12 and sma20 and rsi14:
        if price > sma20 and ema6 > ema12 and 45 <= rsi14 <= 70:
            return "Bullish / แนวโน้มขาขึ้น"
        elif price < sma20 and ema6 < ema12 and rsi14 < 50:
            return "Bearish / แนวโน้มขาลง"
        else:
            return "Sideway / แกว่งตัว รอเลือกทาง"

    return "Sideway / ข้อมูลยังไม่พอ"


def analyze_asset(user_text):
    asset = normalize_asset(user_text)
    quote = td_get_quote(asset)
    closes, volumes = td_get_series(asset)

    price = float(quote.get("close") or quote.get("previous_close") or 0)
    high = float(quote.get("high") or price)
    low = float(quote.get("low") or price)
    prev_close = float(quote.get("previous_close") or price)

    if asset["asset_type"] == "GOLD":
        rate = usd_to_thb()
        price *= rate
        high *= rate
        low *= rate
        prev_close *= rate

    change = price - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0

    ema6 = ema(closes, 6) if closes else None
    ema12 = ema(closes, 12) if closes else None
    sma20 = sma(closes, 20) if closes else None
    rsi14 = rsi(closes, 14) if closes else None

    ai_view = ai_trend_analysis(price, ema6, ema12, sma20, rsi14)

    buy1 = round(price * 0.99, 2)
    buy2 = round(price * 0.97, 2)
    buy3 = round(price * 0.95, 2)
    sell1 = round(price * 1.03, 2)
    sell2 = round(price * 1.06, 2)
    sell3 = round(price * 1.10, 2)
    stop_loss = round(price * 0.93, 2)

    status = "รอสังเกตการณ์"

    if ema6 and ema12 and ema6 > ema12 and (rsi14 is None or rsi14 < 70):
        status = "โมเมนตัมบวก / รอย่อซื้อ"
    elif rsi14 and rsi14 >= 70:
        status = "ร้อนแรงเกินไป / ระวังไล่ราคา"
    elif ema6 and ema12 and ema6 < ema12:
        status = "โมเมนตัมอ่อน / รอฐานชัด"

    unit = "฿" if asset["currency"] == "THB" else "$"
    rsi_text = f"{rsi14:.1f}" if rsi14 is not None else "N/A"

    gold_note = ""
    gold_baht_price = price / 31.1035 * 15.244 if asset["asset_type"] == "GOLD" else 0
    gold_factor = 15.244 / 31.1035 if asset["asset_type"] == "GOLD" else 1
if asset["asset_type"] == "GOLD":
    gold_note = "\nหมายเหตุทองคำ: ราคา Spot แสดงเป็นเงินบาทต่อ 1 ออนซ์ ส่วนราคาทองไทยเป็นราคาประมาณต่อ 1 บาททองคำ"
    text = f"""[{asset['display']}] รายงานราคาปัจจุบัน

ราคา: {unit}{price:,.2f}
ราคาทองไทยประมาณ: ฿{gold_baht_price:,.2f} / บาททองคำ
เปลี่ยนแปลง: {change_pct:+.2f}%
สูงสุด/ต่ำสุด: {unit}{high:,.2f} / {unit}{low:,.2f}

TECHNICAL 15m
EMA 6: {fmt(ema6, unit)}
EMA 12: {fmt(ema12, unit)}
SMA 20: {fmt(sma20, unit)}
RSI 14: {rsi_text}

จุดเข้าซื้อ 3 ไม้
ไม้ 1: {unit}{buy1 * gold_factor:,.2f}
ไม้ 2: {unit}{buy2 * gold_factor:,.2f}
ไม้ 3: {unit}{buy3 * gold_factor:,.2f}

จุดขายออก 3 ไม้
ขาย 1: {unit}{sell1 * gold_factor:,.2f}
ขาย 2: {unit}{sell2 * gold_factor:,.2f}
ขาย 3: {unit}{sell3 * gold_factor:,.2f}

จุดคุมความเสี่ยง: ต่ำกว่า {unit}{stop_loss * gold_factor:,.2f}

สรุป: {status}
AI วิเคราะห์: {ai_view}
อัปเดต: {now_text()}
{gold_note}

หมายเหตุ: เป็นข้อมูลเชิงระบบ ไม่ใช่คำแนะนำการลงทุนเฉพาะบุคคล"""
    return {
            "asset": asset,
            "price": price,
            "change_pct": change_pct,
            "high": high,
            "low": low,
            "ema6": ema6,
            "ema12": ema12,
            "sma20": sma20,
            "rsi14": rsi14,
            "status": status,
            "unit": unit,
            "text": text
    }
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
