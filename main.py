import os
import hmac
import hashlib
import base64
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from flask import Flask, request, abort, send_from_directory
import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
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

GOLD_WORDS = {"GOLD", "ทอง", "XAUUSD", "XAU/USD"}
def now_text():
    thai_time = datetime.utcnow() + timedelta(hours=7)
    return thai_time.strftime("%d/%m/%Y %H:%M")
def create_chart(symbol, prices):
    plt.figure(figsize=(8,4))

    df = pd.DataFrame(prices, columns=["price"])

    plt.plot(df["price"])

    plt.title(f"{symbol} Price Chart")
    plt.xlabel("Time")
    plt.ylabel("Price")

    filename = f"reports/{symbol}.png"

    plt.savefig(filename)
    plt.close()

    return filename
@app.route("/health")
def health():
    return "OK"

@app.route("/reports/<path:filename>")
def report_file(filename):
    return send_from_directory(REPORT_DIR, filename)

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

        try:
            result = analyze_asset(user_text)

            prices, _ = td_get_series(result["asset"])

            chart_file = create_chart(user_text.upper(), prices)

            image_path = Path(chart_file)

            image_url = f"{PUBLIC_BASE_URL}/reports/{image_path.name}" if PUBLIC_BASE_URL else None

            reply_line(reply_token, result["text"], image_url)

        except Exception as e:
            print("ERROR:", repr(e))
            reply_line(
                reply_token,
                f"ระบบยังอ่านคำสั่งนี้ไม่ได้ครับ\nลองพิมพ์ เช่น NVDA, AAPL, SCB, AOT, GOLD\n\nError: {e}",
                None
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
        return {"display": "GOLD / XAUUSD", "symbol": "XAU/USD", "exchange": None, "currency": "USD", "asset_type": "GOLD"}

    if key in THAI_SYMBOL_MAP:
        symbol, exchange, currency = THAI_SYMBOL_MAP[key]
        return {"display": f"{symbol}.SET", "symbol": symbol, "exchange": exchange, "currency": currency, "asset_type": "THAI_STOCK"}

    if key.endswith(".BK"):
        symbol = key.replace(".BK", "")
        return {"display": f"{symbol}.SET", "symbol": symbol, "exchange": "SET", "currency": "THB", "asset_type": "THAI_STOCK"}

    return {"display": key, "symbol": key, "exchange": None, "currency": "USD", "asset_type": "US_STOCK"}

def td_get_quote(asset):
    if not TWELVEDATA_API_KEY:
        raise RuntimeError("ยังไม่ได้ตั้งค่า TWELVEDATA_API_KEY")

    params = {"symbol": asset["symbol"], "apikey": TWELVEDATA_API_KEY}
    if asset.get("exchange"):
        params["exchange"] = asset["exchange"]

    r = requests.get("https://api.twelvedata.com/quote", params=params, timeout=20)
    data = r.json()

    if data.get("status") == "error" or "close" not in data:
        raise RuntimeError(f"ไม่พบข้อมูลจาก Twelve Data สำหรับ {asset['display']}")
    return data

def td_get_series(asset):
    params = {"symbol": asset["symbol"], "interval": "15min", "outputsize": 80, "apikey": TWELVEDATA_API_KEY}
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

def analyze_asset(user_text):
    asset = normalize_asset(user_text)
    quote = td_get_quote(asset)
    closes, volumes = td_get_series(asset)

    price = float(quote.get("close") or quote.get("previous_close") or 0)
    high = float(quote.get("high") or price)
    low = float(quote.get("low") or price)
    prev_close = float(quote.get("previous_close") or price)

    change = price - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0

    ema6 = ema(closes, 6) if closes else None
    ema12 = ema(closes, 12) if closes else None
    sma20 = sma(closes, 20) if closes else None
    rsi14 = rsi(closes, 14) if closes else None

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

    unit = "$" if asset["currency"] == "USD" else "฿"
    rsi_text = f"{rsi14:.1f}" if rsi14 is not None else "N/A"

    text = f"""[{asset['display']}] รายงานราคาปัจจุบัน

ราคา: {unit}{price:,.2f}
เปลี่ยนแปลง: {change_pct:+.2f}%
สูงสุด/ต่ำสุด: {unit}{high:,.2f} / {unit}{low:,.2f}

TECHNICAL 15m
EMA 6: {fmt(ema6, unit)}
EMA 12: {fmt(ema12, unit)}
SMA 20: {fmt(sma20, unit)}
RSI 14: {rsi_text}

จุดเข้าซื้อ 3 ไม้
ไม้ 1: {unit}{buy1:,.2f}
ไม้ 2: {unit}{buy2:,.2f}
ไม้ 3: {unit}{buy3:,.2f}

จุดขายออก 3 ไม้
ขาย 1: {unit}{sell1:,.2f}
ขาย 2: {unit}{sell2:,.2f}
ขาย 3: {unit}{sell3:,.2f}

จุดคุมความเสี่ยง: ต่ำกว่า {unit}{stop_loss:,.2f}

สรุป: {status}
อัปเดต: {now_text()}

หมายเหตุ: เป็นข้อมูลเชิงระบบ ไม่ใช่คำแนะนำการลงทุนเฉพาะบุคคล"""

    return {"asset": asset, "price": price, "change_pct": change_pct, "high": high, "low": low, "ema6": ema6, "ema12": ema12, "sma20": sma20, "rsi14": rsi14, "buy": [buy1, buy2, buy3], "sell": [sell1, sell2, sell3], "stop_loss": stop_loss, "status": status, "unit": unit, "text": text}

def reply_line(reply_token, text, image_url=None):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("LINE_CHANNEL_ACCESS_TOKEN is missing")
        return

    messages = []
    if image_url:
        messages.append({"type": "image", "originalContentUrl": image_url, "previewImageUrl": image_url})
    messages.append({"type": "text", "text": text[:4900]})

    r = requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers={"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}", "Content-Type": "application/json"},
        json={"replyToken": reply_token, "messages": messages[:5]},
        timeout=20
    )
    print("LINE reply:", r.status_code, r.text)

def load_font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansThai-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for c in candidates:
        if os.path.exists(c):
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()

def create_report_image(result):
    W, H = 1080, 1500
    img = Image.new("RGB", (W, H), (8, 12, 22))
    d = ImageDraw.Draw(img)

    title_font = load_font(70, True)
    h_font = load_font(34, True)
    body_font = load_font(30, False)
    small_font = load_font(24, False)

    green = (66, 220, 139)
    red = (255, 95, 95)
    yellow = (255, 194, 80)
    white = (235, 240, 250)
    muted = (145, 156, 175)
    panel = (20, 28, 45)

    d.text((70, 55), "AI INVESTOR TERMINAL", font=h_font, fill=yellow)
    d.text((70, 105), result["asset"]["display"], font=title_font, fill=white)

    ch_color = green if result["change_pct"] >= 0 else red
    d.text((70, 205), f"ราคา {result['unit']}{result['price']:,.2f}", font=h_font, fill=white)
    d.text((70, 255), f"เปลี่ยนแปลง {result['change_pct']:+.2f}%", font=h_font, fill=ch_color)

    d.rounded_rectangle((60, 330, 1020, 570), radius=28, fill=panel)
    d.text((95, 355), "TECHNICAL STATUS", font=h_font, fill=yellow)
    techs = [("EMA6", fmt(result["ema6"], result["unit"])), ("EMA12", fmt(result["ema12"], result["unit"])), ("SMA20", fmt(result["sma20"], result["unit"])), ("RSI14", f"{result['rsi14']:.1f}" if result["rsi14"] is not None else "N/A")]
    y = 415
    for name, val in techs:
        d.text((95, y), name, font=body_font, fill=muted)
        d.text((760, y), val, font=body_font, fill=white)
        y += 42

    d.rounded_rectangle((60, 610, 1020, 890), radius=28, fill=panel)
    d.text((95, 635), "จุดเข้าซื้อ 3 ไม้", font=h_font, fill=green)
    y = 695
    for i, v in enumerate(result["buy"], 1):
        d.text((115, y), f"ไม้ {i}", font=body_font, fill=white)
        d.text((760, y), f"{result['unit']}{v:,.2f}", font=body_font, fill=green)
        y += 55

    d.rounded_rectangle((60, 930, 1020, 1210), radius=28, fill=panel)
    d.text((95, 955), "จุดขายออก 3 ไม้", font=h_font, fill=yellow)
    y = 1015
    for i, v in enumerate(result["sell"], 1):
        d.text((115, y), f"ขาย {i}", font=body_font, fill=white)
        d.text((760, y), f"{result['unit']}{v:,.2f}", font=body_font, fill=yellow)
        y += 55

    d.rounded_rectangle((60, 1250, 1020, 1410), radius=28, fill=(24, 20, 34))
    d.text((95, 1275), "BOTTOM LINE", font=h_font, fill=yellow)
    d.text((95, 1330), result["status"], font=body_font, fill=white)
    d.text((95, 1375), f"Stop risk: ต่ำกว่า {result['unit']}{result['stop_loss']:,.2f}", font=small_font, fill=red)

    filename = f"{result['asset']['display'].replace('/', '').replace('.', '_')}_{int(time.time())}.png"
    path = REPORT_DIR / filename
    img.save(path, "PNG")
    return path

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
