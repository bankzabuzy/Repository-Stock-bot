import os
import hmac
import hashlib
import base64
import time
import threading
from datetime import datetime, timedelta

import requests
import yfinance as yf
from flask import Flask, request, abort

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
PORT = int(os.getenv("PORT", "3000"))

WATCHLIST = [
    x.strip().upper()
    for x in os.getenv("WATCHLIST", "NVDA,AAPL,TSLA,QQQ,SPY,GOLD,SCB,AOT,PTT").split(",")
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

ENABLE_AUTO_ALERTS = os.getenv("ENABLE_AUTO_ALERTS", "false").lower() == "true"
ALERT_EVERY_MINUTES = int(os.getenv("ALERT_EVERY_MINUTES", "60"))
AUTO_ALERT_MIN_SCORE = int(os.getenv("AUTO_ALERT_MIN_SCORE", "75"))
AUTO_ALERT_MAX_SCORE = int(os.getenv("AUTO_ALERT_MAX_SCORE", "25"))
LAST_ALERTS = {}

THAI_SYMBOLS = {
    "SCB", "AOT", "PTT", "CPALL", "KBANK", "BBL", "DELTA", "ADVANC", "TRUE",
    "BDMS", "MINT", "PTTEP", "GULF", "CPAXT", "BEM", "KTB", "KTC", "OR",
    "CRC", "HMPRO", "CENTEL", "GPSC", "EA", "BGRIM", "BH", "TOP", "SCC"
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
        if value is None:
            return default
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


def get_usd_thb_rate():
    try:
        if TWELVEDATA_API_KEY:
            r = requests.get(
                "https://api.twelvedata.com/exchange_rate",
                params={"symbol": "USD/THB", "apikey": TWELVEDATA_API_KEY},
                timeout=15,
            )
            data = r.json()
            rate = safe_float(data.get("rate"))
            if rate:
                return rate
    except Exception:
        pass

    try:
        data = yf.Ticker("USDTHB=X").history(period="5d", interval="1d")
        if not data.empty:
            return float(data["Close"].dropna().iloc[-1])
    except Exception:
        pass

    return 36.50


def gold_thb_per_baht_weight(xauusd_price, usd_thb_rate):
    # 1 baht gold weight approx 15.244 grams, 1 troy ounce = 31.1034768 grams.
    if not xauusd_price or not usd_thb_rate:
        return None
    return xauusd_price * usd_thb_rate * (15.244 / 31.1034768)


def normalize_asset(user_text):
    raw = user_text.strip()
    key = raw.upper().replace(" ", "")

    if raw in GOLD_WORDS or key in GOLD_WORDS:
        return {
            "display": "ทองคำ / XAUUSD",
            "symbol": "XAU/USD",
            "yf_symbol": "GC=F",
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

    if key in THAI_SYMBOLS:
        return {
            "display": f"{key}.BK",
            "symbol": key,
            "yf_symbol": f"{key}.BK",
            "currency": "THB",
            "asset_type": "THAI_STOCK",
            "news_symbol": key,
        }

    return {
        "display": key,
        "symbol": key,
        "yf_symbol": key,
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
            f"รายละเอียด: {msg}"
        )

    return {
        "close": safe_float(data.get("close")),
        "previous_close": safe_float(data.get("previous_close")),
        "change": safe_float(data.get("change")),
        "percent_change": safe_float(data.get("percent_change")),
    }


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


def yf_get_quote_and_series(asset):
    ticker = yf.Ticker(asset["yf_symbol"])

    # Yahoo Finance free data. 15m works for many tickers, but Thai stocks can be limited.
    data = ticker.history(period="3mo", interval="1d", auto_adjust=False)
    if data.empty:
        raise RuntimeError(f"Yahoo Finance ไม่พบข้อมูลสำหรับ {asset['display']}")

    data = data.dropna()
    closes = [float(x) for x in data["Close"].tolist()]
    highs = [float(x) for x in data["High"].tolist()]
    lows = [float(x) for x in data["Low"].tolist()]
    opens = [float(x) for x in data["Open"].tolist()]
    volumes = [float(x) for x in data["Volume"].fillna(0).tolist()]

    price = closes[-1] if closes else None
    prev = closes[-2] if len(closes) >= 2 else None
    change = price - prev if price is not None and prev is not None else None
    percent_change = (change / prev * 100) if change is not None and prev else None

    quote = {
        "close": price,
        "previous_close": prev,
        "change": change,
        "percent_change": percent_change,
    }
    return quote, closes, highs, lows, opens, volumes


def get_market_data(asset):
    if asset["asset_type"] == "THAI_STOCK":
        return yf_get_quote_and_series(asset)

    if asset["asset_type"] == "US_STOCK":
        quote = td_get_quote(asset)
        closes, highs, lows, opens, volumes = td_get_series(asset)
        return quote, closes, highs, lows, opens, volumes

    # Gold: try Twelve Data XAU/USD first, fallback to Yahoo GC=F.
    if asset["asset_type"] == "GOLD":
        try:
            quote = td_get_quote(asset)
            closes, highs, lows, opens, volumes = td_get_series(asset)
            if closes:
                return quote, closes, highs, lows, opens, volumes
        except Exception:
            pass
        return yf_get_quote_and_series(asset)

    return yf_get_quote_and_series(asset)


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
            reasons.append("โมเมนตัมล่าสุดเป็นบวก")
        elif percent_change < -1:
            score -= 8
            reasons.append("โมเมนตัมล่าสุดเป็นลบ")

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
        for item in items[:3]:
            headline = item.get("headline")
            if headline:
                headlines.append(f"- {headline}")

        return "\n".join(headlines) if headlines else "ไม่มีหัวข้อข่าวสำคัญ", len(headlines)

    except Exception as e:
        return f"ดึงข่าวไม่สำเร็จ: {e}", 0


def build_trade_plan(price, atr, bias, asset_type=None, thai_factor=None):
    if not price:
        return "ข้อมูลราคาไม่พอสำหรับทำแผน 3 ไม้"

    if not atr:
        atr = price * 0.01

    buy1 = price - atr * 0.30
    buy2 = price - atr * 0.70
    buy3 = price - atr * 1.10

    sell1 = price + atr * 0.50
    sell2 = price + atr * 1.00
    sell3 = price + atr * 1.60

    stop = price - atr * 1.50

    def fmt_level(value):
        if asset_type == "GOLD" and thai_factor:
            return f"{fmt_num(value, 0)} / {fmt_num(value * thai_factor, 0)}฿"
        return fmt_num(value)

    if "BEARISH" in bias:
        note = "แนวโน้มยังอ่อน แผนซื้อควรรอไม้ลึก/ลดขนาดไม้ และห้ามไล่ราคา"
    elif "BULLISH" in bias:
        note = "แนวโน้มบวก ใช้แผนย่อซื้อและแบ่งขายตามแนวต้าน"
    else:
        note = "แนวโน้มกลาง ใช้แผนแบ่งไม้ หลีกเลี่ยงการเข้าเต็มจำนวน"

    return f"""🧩 แผนเข้า/ออก 3 ไม้
ซื้อไม้ 1: {fmt_level(buy1)}
ซื้อไม้ 2: {fmt_level(buy2)}
ซื้อไม้ 3: {fmt_level(buy3)}

ขาย/ทำกำไร 1: {fmt_level(sell1)}
ขาย/ทำกำไร 2: {fmt_level(sell2)}
ขาย/ทำกำไร 3: {fmt_level(sell3)}

จุดคุมความเสี่ยง: {fmt_level(stop)}
หมายเหตุ: {note}"""


def build_gold_report(asset, analysis, news_text, reasons):
    price = analysis["price"]
    atr = analysis["atr"] or (price * 0.01 if price else None)

    usd_thb = get_usd_thb_rate()
    gold_thb_oz = price * usd_thb if price else None

    gold_bar_sell = gold_thb_per_baht_weight(price, usd_thb)
    gold_bar_buy = gold_bar_sell - 100 if gold_bar_sell else None
    gold_jewelry_sell = gold_bar_sell + 850 if gold_bar_sell else None

    thai_factor = gold_bar_sell / price if gold_bar_sell and price else None

    s1 = price - atr * 0.30 if price and atr else None
    s2 = price - atr * 0.70 if price and atr else None
    s3 = price - atr * 1.10 if price and atr else None
    r1 = price + atr * 0.50 if price and atr else None
    r2 = price + atr * 1.00 if price and atr else None
    r3 = price + atr * 1.60 if price and atr else None

    def gold_level(value):
        if value is None or thai_factor is None:
            return "N/A"
        return f"{fmt_num(value, 0)} / {fmt_num(value * thai_factor, 0)}฿"

    trade_plan = build_trade_plan(
        price,
        atr,
        analysis["bias"],
        asset_type="GOLD",
        thai_factor=thai_factor,
    )

    return f"""📊 วิเคราะห์ทองคำ

XAUUSD
{fmt_num(price)} USD

🇹🇭 เทียบเงินบาท
{fmt_num(gold_thb_oz, 0)} บาท/ออนซ์

🏆 ราคาทองไทย

ทองแท่งรับซื้อ
{fmt_num(gold_bar_buy, 0)} บาท

ทองแท่งขายออก
{fmt_num(gold_bar_sell, 0)} บาท

ทองรูปพรรณขายออก
{fmt_num(gold_jewelry_sell, 0)} บาท

AI Score: {analysis['score']}/100
มุมมอง: {analysis['bias']}

📈 Technical
EMA6: {fmt_num(analysis['ema6'])}
EMA12: {fmt_num(analysis['ema12'])}
EMA50: {fmt_num(analysis['ema50'])}
RSI14: {fmt_num(analysis['rsi'])}
ATR14: {fmt_num(analysis['atr'])}

🎯 แนวรับ / แนวต้าน

S1: {gold_level(s1)}
S2: {gold_level(s2)}
S3: {gold_level(s3)}

R1: {gold_level(r1)}
R2: {gold_level(r2)}
R3: {gold_level(r3)}

{trade_plan}

เหตุผลหลัก:
{chr(10).join("- " + r for r in reasons)}

📰 ข่าว/บริบท:
{news_text}

หมายเหตุ: ไม่ใช่คำแนะนำการลงทุน ราคาทองไทยเป็นค่าประมาณจาก XAUUSD และ USD/THB ไม่ใช่ประกาศสมาคมค้าทองคำแบบเรียลไทม์"""


def build_asset_report(user_text):
    asset = normalize_asset(user_text)
    quote, closes, highs, lows, opens, volumes = get_market_data(asset)
    analysis = analyze_signal(asset, quote, closes, highs, lows, opens, volumes)
    news_text, news_count = fetch_news(asset)

    reasons = analysis["reasons"][:5]
    if not reasons:
        reasons = ["ข้อมูลเทคนิคยังไม่พอ ให้ดูเป็นข้อมูลราคาเบื้องต้น"]

    if asset["asset_type"] == "GOLD":
        return build_gold_report(asset, analysis, news_text, reasons)

    currency = asset["currency"]
    price_label = "$" if currency == "USD" else "฿"
    trade_plan = build_trade_plan(analysis["price"], analysis["atr"], analysis["bias"])

    source_text = "Yahoo Finance" if asset["asset_type"] == "THAI_STOCK" else "Twelve Data"

    return f"""📊 วิเคราะห์ {asset['display']}
แหล่งข้อมูล: {source_text}
เวลาไทย: {now_text()}

ราคา: {price_label}{fmt_num(analysis['price'])}
เปลี่ยนแปลง: {fmt_num(analysis['change'])} ({fmt_num(analysis['percent_change'])}%)

AI Score: {analysis['score']}/100
มุมมอง: {analysis['bias']}

📈 Technical
EMA6: {fmt_num(analysis['ema6'])}
EMA12: {fmt_num(analysis['ema12'])}
EMA50: {fmt_num(analysis['ema50'])}
RSI14: {fmt_num(analysis['rsi'])}
ATR14: {fmt_num(analysis['atr'])}

🎯 โซนราคา
แนวรับประมาณ: {price_label}{fmt_num(analysis['support'])}
แนวต้านประมาณ: {price_label}{fmt_num(analysis['resistance'])}
Stop loss เชิงระบบ: {price_label}{fmt_num(analysis['stop_loss'])}
Take profit เชิงระบบ: {price_label}{fmt_num(analysis['take_profit'])}

{trade_plan}

เหตุผลหลัก:
{chr(10).join("- " + r for r in reasons)}

📰 ข่าว/บริบท:
{news_text}

หมายเหตุ: ไม่ใช่คำแนะนำการลงทุน ใช้เพื่อช่วยคัดกรองเท่านั้น"""


def line_reply(reply_token, text):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("LINE_CHANNEL_ACCESS_TOKEN is missing")
        return

    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text[:4900]}],
    }

    requests.post(url, headers=headers, json=payload, timeout=20)


def line_push(user_id, text):
    if not LINE_CHANNEL_ACCESS_TOKEN or not user_id:
        return

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": text[:4900]}],
    }

    requests.post(url, headers=headers, json=payload, timeout=20)


def verify_line_signature(body, signature):
    if not LINE_CHANNEL_SECRET:
        return True

    digest = hmac.new(
        LINE_CHANNEL_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()

    valid_signature = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(valid_signature, signature or "")


def help_text():
    return """พิมพ์ชื่อสินทรัพย์ที่ต้องการวิเคราะห์ เช่น

หุ้นสหรัฐ:
NVDA
AAPL
TSLA
QQQ
SPY

หุ้นไทย:
SCB
AOT
PTT
KBANK
CPALL
ADVANC

ทองคำ:
ทองคำ
GOLD
XAUUSD

คำสั่งพิเศษ:
watchlist = ดูรายการเฝ้าดู
help = วิธีใช้งาน"""


def handle_message(user_id, text):
    clean = text.strip()

    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return "User นี้ยังไม่ได้รับอนุญาตให้ใช้งานระบบ"

    lower = clean.lower()

    if lower in {"help", "วิธีใช้", "เมนู"}:
        return help_text()

    if lower == "watchlist":
        return "รายการเฝ้าดู:\n" + "\n".join(f"- {x}" for x in WATCHLIST)

    try:
        return build_asset_report(clean)
    except Exception as e:
        return (
            "ระบบยังอ่านคำสั่งนี้ไม่ได้ครับ\n"
            "ลองพิมพ์ เช่น NVDA, AAPL, SCB, AOT, ทองคำ, GOLD\n\n"
            f"Error: {e}"
        )


@app.route("/", methods=["GET"])
def home():
    return {
        "status": "ok",
        "service": "AI Market LINE Bot",
        "time_th": now_text(),
        "watchlist": WATCHLIST,
        "thai_stock_source": "Yahoo Finance",
        "us_stock_source": "Twelve Data",
    }


@app.route("/health", methods=["GET"])
def health():
    return "OK", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_data()
    signature = request.headers.get("X-Line-Signature", "")

    if not verify_line_signature(body, signature):
        abort(400)

    payload = request.get_json(silent=True) or {}

    for event in payload.get("events", []):
        event_type = event.get("type")
        reply_token = event.get("replyToken")
        source = event.get("source", {})
        user_id = source.get("userId", "")

        if event_type != "message":
            continue

        message = event.get("message", {})
        if message.get("type") != "text":
            line_reply(reply_token, "ตอนนี้รองรับเฉพาะข้อความเท่านั้นครับ")
            continue

        user_text = message.get("text", "")
        response_text = handle_message(user_id, user_text)
        line_reply(reply_token, response_text)

    return "OK", 200


def should_send_alert(symbol, score):
    now_ts = time.time()
    last_ts = LAST_ALERTS.get(symbol, 0)
    cooldown_seconds = ALERT_EVERY_MINUTES * 60

    if now_ts - last_ts < cooldown_seconds:
        return False

    if score >= AUTO_ALERT_MIN_SCORE or score <= AUTO_ALERT_MAX_SCORE:
        LAST_ALERTS[symbol] = now_ts
        return True

    return False


def auto_alert_loop():
    while True:
        try:
            if ENABLE_AUTO_ALERTS and ALERT_USER_IDS:
                for symbol in WATCHLIST:
                    try:
                        asset = normalize_asset(symbol)
                        quote, closes, highs, lows, opens, volumes = get_market_data(asset)
                        analysis = analyze_signal(asset, quote, closes, highs, lows, opens, volumes)

                        if should_send_alert(symbol, analysis["score"]):
                            report = build_asset_report(symbol)
                            if analysis["score"] >= AUTO_ALERT_MIN_SCORE:
                                header = f"🚨 BUY/MOMENTUM ALERT: {symbol}\n\n"
                            else:
                                header = f"⚠️ SELL/WEAKNESS ALERT: {symbol}\n\n"

                            for user_id in ALERT_USER_IDS:
                                line_push(user_id, header + report)

                        time.sleep(3)

                    except Exception as e:
                        print(f"Auto alert error for {symbol}: {e}")

            time.sleep(60)

        except Exception as e:
            print(f"Auto alert loop error: {e}")
            time.sleep(60)


if __name__ == "__main__":
    if ENABLE_AUTO_ALERTS and ALERT_USER_IDS:
        t = threading.Thread(target=auto_alert_loop, daemon=True)
        t.start()

    app.run(host="0.0.0.0", port=PORT)
