import os
import re
import hmac
import hashlib
import base64
import time
import threading
from datetime import datetime, timedelta

import requests
import yfinance as yf
from bs4 import BeautifulSoup
from flask import Flask, request, abort

app = Flask(__name__)

# =========================
# ENV CONFIG
# =========================
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

# If empty = everyone can use the bot.
ALLOWED_USERS = [
    x.strip()
    for x in os.getenv("ALLOWED_USERS", "").split(",")
    if x.strip()
]

# For push/auto-alert. Put LINE userId / groupId / roomId here.
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

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

THAI_SYMBOLS = {
    "SCB", "AOT", "PTT", "CPALL", "KBANK", "BBL", "DELTA", "ADVANC", "TRUE",
    "BDMS", "MINT", "PTTEP", "GULF", "CPAXT", "BEM", "KTB", "KTC", "OR",
    "CRC", "HMPRO", "CENTEL", "GPSC", "EA", "BGRIM", "BH", "TOP", "SCC",
    "TISCO", "LH", "MTC", "SAWAD", "TIDLOR", "OSP", "CBG", "TU", "IVL"
}

GOLD_WORDS = {"GOLD", "ทอง", "ทองคำ", "XAUUSD", "XAU/USD", "ทองคํา"}
US_INDEX_SYMBOLS = {
    "SPX": "SPY",
    "NASDAQ": "QQQ",
    "NDX": "QQQ",
    "DOW": "DIA",
    "RUSSELL": "IWM",
}


# =========================
# UTILS
# =========================
def now_text():
    return (datetime.utcnow() + timedelta(hours=7)).strftime("%d/%m/%Y %H:%M")


def safe_float(value, default=None):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace(",", "").strip()
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


def clean_price_text(value):
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return None
    return safe_float(match.group(0))


def extract_price_numbers(text):
    # Extract values like 70,050.00 / 70050 / 70,050
    nums = []
    for m in re.findall(r"\d{2,3},\d{3}(?:\.\d+)?|\d{5,6}(?:\.\d+)?", text):
        v = safe_float(m)
        if v and 10000 <= v <= 200000:
            nums.append(v)
    return nums


# =========================
# ASSET NORMALIZATION
# =========================
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


# =========================
# DATA SOURCES
# =========================
def get_usd_thb_rate():
    # 1) Twelve Data
    try:
        if TWELVEDATA_API_KEY:
            r = requests.get(
                "https://api.twelvedata.com/exchange_rate",
                params={"symbol": "USD/THB", "apikey": TWELVEDATA_API_KEY},
                headers=REQUEST_HEADERS,
                timeout=15,
            )
            data = r.json()
            rate = safe_float(data.get("rate"))
            if rate:
                return rate
    except Exception:
        pass

    # 2) Yahoo Finance fallback
    try:
        data = yf.Ticker("USDTHB=X").history(period="5d", interval="1d")
        if not data.empty:
            return float(data["Close"].dropna().iloc[-1])
    except Exception:
        pass

    # 3) Safe fallback
    return 36.50


def gold_thb_per_baht_weight(xauusd_price, usd_thb_rate):
    # 1 baht gold weight ≈ 15.244 g, 1 troy ounce = 31.1034768 g
    if not xauusd_price or not usd_thb_rate:
        return None
    return xauusd_price * usd_thb_rate * (15.244 / 31.1034768)


def get_goldtraders_price():
    """Try to fetch Thai gold price from Gold Traders Association website.
    Returns dict:
      bar_buy, bar_sell, ornament_buy, ornament_sell, source, updated_at
    or None if parsing failed.

    Note: if GoldTraders changes HTML/JS rendering, this function may fail.
    The bot then falls back to calculated XAUUSD × USDTHB estimate.
    """
    urls = [
        "https://www.goldtraders.or.th/",
        "https://www.goldtraders.or.th/Default.aspx",
        "https://newgta.goldtraders.or.th/homepage_pre",
    ]

    for url in urls:
        try:
            r = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
            if r.status_code != 200:
                continue

            html = r.text
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(" ", strip=True)

            # Direct ID parsing for old ASP.NET GoldTraders site.
            # IDs have changed before, so this is best-effort.
            id_candidates = {
                "bar_buy": [
                    "DetailPlace_uc_goldprices1_lblBLSell",
                    "DetailPlace_uc_goldprices1_lblBLBuy",
                    "lblBLSell",
                    "lblBLBuy",
                ],
                "bar_sell": [
                    "DetailPlace_uc_goldprices1_lblBLSell2",
                    "DetailPlace_uc_goldprices1_lblBLSell",
                    "lblBLSell2",
                    "lblBLSell",
                ],
                "ornament_buy": [
                    "DetailPlace_uc_goldprices1_lblOMBuy",
                    "lblOMBuy",
                ],
                "ornament_sell": [
                    "DetailPlace_uc_goldprices1_lblOMSell",
                    "lblOMSell",
                ],
            }

            parsed = {}
            for key, ids in id_candidates.items():
                for id_ in ids:
                    tag = soup.find(id=id_)
                    value = clean_price_text(tag.get_text(" ", strip=True)) if tag else None
                    if value:
                        parsed[key] = value
                        break

            # Text-pattern parsing fallback around Thai labels.
            if "bar_buy" not in parsed or "bar_sell" not in parsed:
                # Try to find numbers around common labels.
                normalized = text.replace("\xa0", " ")
                numbers = extract_price_numbers(normalized)

                # In many GoldTraders pages, 4 core prices appear close together:
                # gold bar buy, gold bar sell, ornament buy, ornament sell.
                # We avoid over-claiming exact fields if order cannot be determined.
                if len(numbers) >= 2:
                    # Pick plausible adjacent prices with small spread.
                    candidates = []
                    for i in range(len(numbers) - 1):
                        a, b = numbers[i], numbers[i + 1]
                        if 0 <= b - a <= 1000:
                            candidates.append((a, b, i))
                    if candidates:
                        bar_buy, bar_sell, idx = candidates[0]
                        parsed.setdefault("bar_buy", bar_buy)
                        parsed.setdefault("bar_sell", bar_sell)
                        if len(numbers) > idx + 2:
                            parsed.setdefault("ornament_buy", numbers[idx + 2])
                        if len(numbers) > idx + 3:
                            parsed.setdefault("ornament_sell", numbers[idx + 3])

            if parsed.get("bar_buy") and parsed.get("bar_sell"):
                # Basic sanity checks.
                if parsed["bar_sell"] < parsed["bar_buy"]:
                    parsed["bar_buy"], parsed["bar_sell"] = parsed["bar_sell"], parsed["bar_buy"]

                return {
                    "bar_buy": parsed.get("bar_buy"),
                    "bar_sell": parsed.get("bar_sell"),
                    "ornament_buy": parsed.get("ornament_buy"),
                    "ornament_sell": parsed.get("ornament_sell"),
                    "source": "สมาคมค้าทองคำ / GoldTraders",
                    "updated_at": now_text(),
                    "raw_url": url,
                }

        except Exception as e:
            print("GoldTraders fetch error:", url, e)

    return None


def get_thai_gold_price_or_estimate(xauusd_price, usd_thb_rate):
    real_price = get_goldtraders_price()
    if real_price:
        real_price["is_estimate"] = False
        return real_price

    # Fallback estimate
    bar_sell = gold_thb_per_baht_weight(xauusd_price, usd_thb_rate)
    bar_buy = bar_sell - 100 if bar_sell else None
    ornament_sell = bar_sell + 850 if bar_sell else None
    ornament_buy = bar_buy - 700 if bar_buy else None

    return {
        "bar_buy": bar_buy,
        "bar_sell": bar_sell,
        "ornament_buy": ornament_buy,
        "ornament_sell": ornament_sell,
        "source": "คำนวณประมาณจาก XAUUSD × USD/THB",
        "updated_at": now_text(),
        "raw_url": None,
        "is_estimate": True,
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

    r = requests.get(
        "https://api.twelvedata.com/quote",
        params=td_params(asset),
        headers=REQUEST_HEADERS,
        timeout=20,
    )
    data = r.json()

    if data.get("status") == "error" or "close" not in data:
        msg = data.get("message", "")
        raise RuntimeError(f"ไม่พบข้อมูลจาก Twelve Data สำหรับ {asset['display']}\nรายละเอียด: {msg}")

    return {
        "close": safe_float(data.get("close")),
        "previous_close": safe_float(data.get("previous_close")),
        "change": safe_float(data.get("change")),
        "percent_change": safe_float(data.get("percent_change")),
    }


def td_get_series(asset, interval="15min", outputsize=160):
    r = requests.get(
        "https://api.twelvedata.com/time_series",
        params=td_params(asset, interval=interval, outputsize=outputsize),
        headers=REQUEST_HEADERS,
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

    if asset["asset_type"] == "GOLD":
        try:
            quote = td_get_quote(asset)
            closes, highs, lows, opens, volumes = td_get_series(asset)
            if closes:
                return quote, closes, highs, lows, opens, volumes
        except Exception as e:
            print("Gold Twelve Data fallback to Yahoo:", e)
        return yf_get_quote_and_series(asset)

    return yf_get_quote_and_series(asset)


# =========================
# INDICATORS
# =========================
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

    gains, losses = [], []
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


# =========================
# NEWS
# =========================
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

        r = requests.get(
            "https://finnhub.io/api/v1/company-news",
            params={
                "symbol": asset["news_symbol"],
                "from": week_ago.isoformat(),
                "to": today.isoformat(),
                "token": FINNHUB_API_KEY,
            },
            headers=REQUEST_HEADERS,
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


# =========================
# REPORT BUILDERS
# =========================
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

    thai_gold = get_thai_gold_price_or_estimate(price, usd_thb)

    bar_buy = thai_gold.get("bar_buy")
    bar_sell = thai_gold.get("bar_sell")
    ornament_sell = thai_gold.get("ornament_sell")
    source = thai_gold.get("source")
    is_estimate = thai_gold.get("is_estimate", False)

    # Convert XAUUSD levels to Thai baht gold price levels using actual Thai bar sell as base.
    # This keeps levels aligned with GoldTraders real Thai price, not just USDTHB formula.
    thai_factor = bar_sell / price if bar_sell and price else None

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

    price_note = (
        "ราคาทองไทย: ดึงจากแหล่งอ้างอิงสมาคมค้าทองคำ"
        if not is_estimate
        else "ราคาทองไทย: fallback เป็นค่าประมาณ เพราะดึงราคาสมาคมไม่สำเร็จ"
    )

    return f"""📊 วิเคราะห์ทองคำ

XAUUSD
{fmt_num(price)} USD

🇹🇭 เทียบเงินบาท
{fmt_num(gold_thb_oz, 0)} บาท/ออนซ์

🏆 ราคาทองไทย

ทองแท่งรับซื้อ
{fmt_num(bar_buy, 0)} บาท

ทองแท่งขายออก
{fmt_num(bar_sell, 0)} บาท

ทองรูปพรรณขายออก
{fmt_num(ornament_sell, 0)} บาท

แหล่งราคาทองไทย:
{source}
อัปเดต: {thai_gold.get('updated_at')}

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

หมายเหตุ: ไม่ใช่คำแนะนำการลงทุน {price_note}"""


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


# =========================
# LINE API
# =========================
def line_reply(reply_token, text):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("LINE_CHANNEL_ACCESS_TOKEN is missing")
        return

    r = requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers={
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "replyToken": reply_token,
            "messages": [{"type": "text", "text": text[:4900]}],
        },
        timeout=20,
    )
    if r.status_code >= 300:
        print("LINE reply failed:", r.status_code, r.text)


def line_push(user_id, text):
    if not LINE_CHANNEL_ACCESS_TOKEN or not user_id:
        return

    r = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "to": user_id,
            "messages": [{"type": "text", "text": text[:4900]}],
        },
        timeout=20,
    )
    if r.status_code >= 300:
        print("LINE push failed:", r.status_code, r.text)


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
        print("Handle message error:", e)
        return (
            "ระบบยังอ่านคำสั่งนี้ไม่ได้ครับ\n"
            "ลองพิมพ์ เช่น NVDA, AAPL, SCB, AOT, ทองคำ, GOLD\n\n"
            f"Error: {e}"
        )


# =========================
# ROUTES
# =========================
@app.route("/", methods=["GET"])
def home():
    return {
        "status": "ok",
        "service": "AI Market LINE Bot",
        "time_th": now_text(),
        "watchlist": WATCHLIST,
        "thai_stock_source": "Yahoo Finance",
        "us_stock_source": "Twelve Data",
        "gold_price_source": "GoldTraders first, fallback calculated",
    }


@app.route("/health", methods=["GET"])
def health():
    return "OK", 200


@app.route("/gold-test", methods=["GET"])
def gold_test():
    asset = normalize_asset("ทองคำ")
    quote, closes, highs, lows, opens, volumes = get_market_data(asset)
    analysis = analyze_signal(asset, quote, closes, highs, lows, opens, volumes)
    usd_thb = get_usd_thb_rate()
    thai_gold = get_thai_gold_price_or_estimate(analysis["price"], usd_thb)
    return {
        "xauusd": analysis["price"],
        "usd_thb": usd_thb,
        "thai_gold": thai_gold,
        "time_th": now_text(),
    }


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


# =========================
# AUTO ALERTS
# =========================
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
