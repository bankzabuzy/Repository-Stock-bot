import os
import re
import hmac
import json
import time
import base64
import hashlib
import sqlite3
import threading
from datetime import datetime, timedelta

import requests
import yfinance as yf
from bs4 import BeautifulSoup
from flask import Flask, request, abort, jsonify, Response

app = Flask(__name__)

# ============================================================
# V7 HYBRID MAX FREE CONFIG
# ============================================================
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
PORT = int(os.getenv("PORT", "3000"))

WATCHLIST = [
    x.strip().upper()
    for x in os.getenv("WATCHLIST", "NVDA,AAPL,TSLA,QQQ,SPY,GOLD,SCB,AOT,PTT").split(",")
    if x.strip()
]

ALLOWED_USERS = [x.strip() for x in os.getenv("ALLOWED_USERS", "").split(",") if x.strip()]
ALERT_USER_IDS = [x.strip() for x in os.getenv("ALERT_USER_IDS", "").split(",") if x.strip()]

ENABLE_AUTO_ALERTS = os.getenv("ENABLE_AUTO_ALERTS", "false").lower() == "true"
ALERT_EVERY_MINUTES = int(os.getenv("ALERT_EVERY_MINUTES", "60"))
AUTO_ALERT_MIN_SCORE = int(os.getenv("AUTO_ALERT_MIN_SCORE", "80"))
AUTO_ALERT_MAX_SCORE = int(os.getenv("AUTO_ALERT_MAX_SCORE", "25"))

DB_PATH = os.getenv("DB_PATH", "signals.db")
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "60"))

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

GOLD_WORDS = {"GOLD", "ทอง", "ทองคำ", "ทองคํา", "XAUUSD", "XAU/USD"}
US_INDEX_SYMBOLS = {"SPX": "SPY", "NASDAQ": "QQQ", "NDX": "QQQ", "DOW": "DIA", "RUSSELL": "IWM"}

CACHE = {}


# ============================================================
# DATABASE
# ============================================================
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            asset_type TEXT,
            price REAL,
            score INTEGER,
            bias TEXT,
            signal_type TEXT,
            regime TEXT,
            probability INTEGER,
            report TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS alert_state (
            symbol TEXT PRIMARY KEY,
            last_sent_ts REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def save_signal(symbol, asset_type, price, score, bias, signal_type, regime, probability, report):
    try:
        conn = db()
        conn.execute(
            """INSERT INTO signals
               (created_at, symbol, asset_type, price, score, bias, signal_type, regime, probability, report)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (now_text(), symbol, asset_type, price, score, bias, signal_type, regime, probability, report[:4900]),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print("save_signal error:", e)


def get_last_alert_ts(symbol):
    try:
        conn = db()
        row = conn.execute("SELECT last_sent_ts FROM alert_state WHERE symbol=?", (symbol,)).fetchone()
        conn.close()
        return float(row["last_sent_ts"]) if row else 0.0
    except Exception:
        return 0.0


def set_last_alert_ts(symbol, ts):
    try:
        conn = db()
        conn.execute(
            "INSERT INTO alert_state(symbol, last_sent_ts) VALUES(?, ?) ON CONFLICT(symbol) DO UPDATE SET last_sent_ts=excluded.last_sent_ts",
            (symbol, ts),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print("set_last_alert_ts error:", e)


# ============================================================
# UTILS
# ============================================================
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


def round_strike(price):
    if price is None:
        return None
    if price >= 500:
        step = 5
    elif price >= 100:
        step = 2.5
    elif price >= 30:
        step = 1
    else:
        step = 0.5
    return round(price / step) * step


def clean_price_text(value):
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    match = re.search(r"\d+(?:\.\d+)?", text)
    return safe_float(match.group(0)) if match else None


def extract_price_numbers(text):
    nums = []
    for m in re.findall(r"\d{2,3},\d{3}(?:\.\d+)?|\d{5,6}(?:\.\d+)?", text):
        v = safe_float(m)
        if v and 10000 <= v <= 200000:
            nums.append(v)
    return nums


def cache_get(key):
    item = CACHE.get(key)
    if not item:
        return None
    ts, value = item
    if time.time() - ts > CACHE_TTL_SECONDS:
        CACHE.pop(key, None)
        return None
    return value


def cache_set(key, value):
    CACHE[key] = (time.time(), value)


# ============================================================
# ASSET NORMALIZATION
# ============================================================
def normalize_asset(user_text):
    raw = user_text.strip()
    key = raw.upper().replace(" ", "")

    if raw in GOLD_WORDS or key in GOLD_WORDS:
        return {"display": "ทองคำ / XAUUSD", "symbol": "XAU/USD", "yf_symbol": "GC=F", "currency": "USD", "asset_type": "GOLD", "news_symbol": "XAU"}

    if key in US_INDEX_SYMBOLS:
        key = US_INDEX_SYMBOLS[key]

    if key.endswith(".BK"):
        key = key.replace(".BK", "")
    if key.endswith(".SET"):
        key = key.replace(".SET", "")

    if key in THAI_SYMBOLS:
        return {"display": f"{key}.BK", "symbol": key, "yf_symbol": f"{key}.BK", "currency": "THB", "asset_type": "THAI_STOCK", "news_symbol": key}

    return {"display": key, "symbol": key, "yf_symbol": key, "currency": "USD", "asset_type": "US_STOCK", "news_symbol": key}


# ============================================================
# DATA SOURCES
# ============================================================
def get_usd_thb_rate():
    cached = cache_get("USDTHB")
    if cached:
        return cached

    try:
        if TWELVEDATA_API_KEY:
            r = requests.get(
                "https://api.twelvedata.com/exchange_rate",
                params={"symbol": "USD/THB", "apikey": TWELVEDATA_API_KEY},
                headers=REQUEST_HEADERS,
                timeout=15,
            )
            rate = safe_float(r.json().get("rate"))
            if rate:
                cache_set("USDTHB", rate)
                return rate
    except Exception:
        pass

    try:
        data = yf.Ticker("USDTHB=X").history(period="5d", interval="1d")
        if not data.empty:
            rate = float(data["Close"].dropna().iloc[-1])
            cache_set("USDTHB", rate)
            return rate
    except Exception:
        pass

    return 36.50


def gold_thb_per_baht_weight(xauusd_price, usd_thb_rate):
    if not xauusd_price or not usd_thb_rate:
        return None
    return xauusd_price * usd_thb_rate * (15.244 / 31.1034768)


def get_goldtraders_price():
    cached = cache_get("GOLDTRADERS")
    if cached:
        return cached

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

            soup = BeautifulSoup(r.text, "html.parser")
            text = soup.get_text(" ", strip=True)

            parsed = {}
            id_candidates = {
                "bar_buy": ["DetailPlace_uc_goldprices1_lblBLBuy", "lblBLBuy"],
                "bar_sell": ["DetailPlace_uc_goldprices1_lblBLSell", "lblBLSell"],
                "ornament_buy": ["DetailPlace_uc_goldprices1_lblOMBuy", "lblOMBuy"],
                "ornament_sell": ["DetailPlace_uc_goldprices1_lblOMSell", "lblOMSell"],
            }

            for key, ids in id_candidates.items():
                for id_ in ids:
                    tag = soup.find(id=id_)
                    value = clean_price_text(tag.get_text(" ", strip=True)) if tag else None
                    if value:
                        parsed[key] = value
                        break

            if "bar_buy" not in parsed or "bar_sell" not in parsed:
                numbers = extract_price_numbers(text)
                if len(numbers) >= 2:
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
                if parsed["bar_sell"] < parsed["bar_buy"]:
                    parsed["bar_buy"], parsed["bar_sell"] = parsed["bar_sell"], parsed["bar_buy"]

                result = {
                    "bar_buy": parsed.get("bar_buy"),
                    "bar_sell": parsed.get("bar_sell"),
                    "ornament_buy": parsed.get("ornament_buy"),
                    "ornament_sell": parsed.get("ornament_sell"),
                    "source": "สมาคมค้าทองคำ / GoldTraders",
                    "updated_at": now_text(),
                    "raw_url": url,
                    "is_estimate": False,
                }
                cache_set("GOLDTRADERS", result)
                return result
        except Exception as e:
            print("GoldTraders fetch error:", url, e)

    return None


def get_thai_gold_price_or_estimate(xauusd_price, usd_thb_rate):
    real = get_goldtraders_price()
    if real:
        return real

    bar_sell = gold_thb_per_baht_weight(xauusd_price, usd_thb_rate)
    return {
        "bar_buy": bar_sell - 100 if bar_sell else None,
        "bar_sell": bar_sell,
        "ornament_buy": bar_sell - 800 if bar_sell else None,
        "ornament_sell": bar_sell + 850 if bar_sell else None,
        "source": "คำนวณประมาณจาก XAUUSD × USD/THB",
        "updated_at": now_text(),
        "raw_url": None,
        "is_estimate": True,
    }


def td_params(asset, interval=None, outputsize=None):
    params = {"symbol": asset["symbol"], "apikey": TWELVEDATA_API_KEY}
    if interval:
        params["interval"] = interval
    if outputsize:
        params["outputsize"] = outputsize
    return params


def td_get_quote(asset):
    if not TWELVEDATA_API_KEY:
        raise RuntimeError("ยังไม่ได้ตั้งค่า TWELVEDATA_API_KEY")

    r = requests.get("https://api.twelvedata.com/quote", params=td_params(asset), headers=REQUEST_HEADERS, timeout=20)
    data = r.json()

    if data.get("status") == "error" or "close" not in data:
        raise RuntimeError(f"ไม่พบข้อมูลจาก Twelve Data สำหรับ {asset['display']}\nรายละเอียด: {data.get('message', '')}")

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


def yf_get_quote_and_series(asset, period="3mo", interval="1d"):
    ticker = yf.Ticker(asset["yf_symbol"])
    data = ticker.history(period=period, interval=interval, auto_adjust=False)
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
    return {"close": price, "previous_close": prev, "change": change, "percent_change": percent_change}, closes, highs, lows, opens, volumes


def get_market_data(asset):
    key = f"MD:{asset['asset_type']}:{asset['symbol']}"
    cached = cache_get(key)
    if cached:
        return cached

    if asset["asset_type"] == "THAI_STOCK":
        result = yf_get_quote_and_series(asset)
    elif asset["asset_type"] == "US_STOCK":
        quote = td_get_quote(asset)
        closes, highs, lows, opens, volumes = td_get_series(asset)
        result = (quote, closes, highs, lows, opens, volumes)
    elif asset["asset_type"] == "GOLD":
        try:
            quote = td_get_quote(asset)
            closes, highs, lows, opens, volumes = td_get_series(asset)
            result = (quote, closes, highs, lows, opens, volumes) if closes else yf_get_quote_and_series(asset)
        except Exception as e:
            print("Gold Twelve Data fallback to Yahoo:", e)
            result = yf_get_quote_and_series(asset)
    else:
        result = yf_get_quote_and_series(asset)

    cache_set(key, result)
    return result


def get_mtf(asset):
    """Multi-timeframe summary using best-free available sources."""
    frames = []
    if asset["asset_type"] == "US_STOCK":
        configs = [("15m", "15min"), ("1h", "1h")]
        for label, interval in configs:
            try:
                closes, highs, lows, opens, volumes = td_get_series(asset, interval=interval, outputsize=160)
                if closes:
                    frames.append((label, closes, highs, lows, volumes))
            except Exception:
                pass
    else:
        # Yahoo daily-based fallback for Thai/gold.
        configs = [("1D", ("3mo", "1d")), ("1W*", ("1y", "1wk"))]
        for label, (period, interval) in configs:
            try:
                _, closes, highs, lows, opens, volumes = yf_get_quote_and_series(asset, period=period, interval=interval)
                frames.append((label, closes, highs, lows, volumes))
            except Exception:
                pass
    return frames


# ============================================================
# INDICATORS + ENGINE
# ============================================================
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
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_atr(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    return sum(trs[-period:]) / period if len(trs) >= period else None


def calc_rvol(volumes, period=20):
    if len(volumes) < period + 1:
        return None
    avg = sum(volumes[-period-1:-1]) / period
    return volumes[-1] / avg if avg else None


def market_regime(price, ema12, ema50, atr, closes):
    if not price or not ema12 or not ema50 or not atr or len(closes) < 20:
        return "UNKNOWN"
    atr_pct = atr / price * 100
    change_20 = (closes[-1] - closes[-20]) / closes[-20] * 100 if closes[-20] else 0
    if price > ema12 > ema50 and change_20 > 3 and atr_pct >= 1:
        return "STRONG UPTREND"
    if price < ema12 < ema50 and change_20 < -3 and atr_pct >= 1:
        return "STRONG DOWNTREND"
    if atr_pct < 1.2:
        return "RANGE / LOW VOL"
    if price > ema50:
        return "UPTREND"
    if price < ema50:
        return "DOWNTREND"
    return "NEUTRAL"


def trend_state(closes):
    e6, e12, e50 = ema(closes, 6), ema(closes, 12), ema(closes, 50)
    price = closes[-1] if closes else None
    if price and e6 and e12 and e50:
        if price > e6 > e12 > e50:
            return "BULLISH"
        if price < e6 < e12 < e50:
            return "BEARISH"
    return "MIXED"


def mtf_alignment(asset):
    frames = get_mtf(asset)
    states = []
    for label, closes, highs, lows, volumes in frames:
        states.append((label, trend_state(closes)))
    bulls = sum(1 for _, s in states if s == "BULLISH")
    bears = sum(1 for _, s in states if s == "BEARISH")
    total = len(states)
    if total == 0:
        return "N/A", []
    if bulls > bears:
        summary = f"{bulls}/{total} Bullish"
    elif bears > bulls:
        summary = f"{bears}/{total} Bearish"
    else:
        summary = f"Mixed {total} TF"
    return summary, states


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
    rvol = calc_rvol(volumes)
    regime = market_regime(price, ema12, ema50, atr, closes)
    alignment, mtf_states = mtf_alignment(asset)

    trend_score = 0
    momentum_score = 0
    volume_score = 0
    volatility_score = 0

    reasons = []

    if price and ema6 and ema12:
        if price > ema6 > ema12:
            trend_score += 22
            reasons.append("ราคาอยู่เหนือ EMA6 และ EMA12")
        elif price < ema6 < ema12:
            trend_score -= 22
            reasons.append("ราคาอยู่ใต้ EMA6 และ EMA12")

    if ema12 and ema50:
        if ema12 > ema50:
            trend_score += 14
            reasons.append("แนวโน้มกลางยังเป็นบวก")
        elif ema12 < ema50:
            trend_score -= 14
            reasons.append("แนวโน้มกลางยังเป็นลบ")

    if rsi is not None:
        if 50 <= rsi <= 65:
            momentum_score += 14
            reasons.append("RSI อยู่ในโซนโมเมนตัมขาขึ้น")
        elif rsi >= 72:
            momentum_score -= 10
            reasons.append("RSI สูง ระวังพักตัว")
        elif rsi <= 30:
            momentum_score += 6
            reasons.append("RSI ต่ำ มีโอกาสรีบาวด์")
        elif rsi < 45:
            momentum_score -= 8
            reasons.append("RSI ต่ำกว่าโซนแข็งแรง")

    if percent_change is not None:
        if percent_change > 1:
            momentum_score += 9
            reasons.append("โมเมนตัมล่าสุดเป็นบวก")
        elif percent_change < -1:
            momentum_score -= 9
            reasons.append("โมเมนตัมล่าสุดเป็นลบ")

    if rvol is not None:
        if rvol >= 1.5 and percent_change and percent_change > 0:
            volume_score += 10
            reasons.append("Volume หนุนขาขึ้น")
        elif rvol >= 1.5 and percent_change and percent_change < 0:
            volume_score -= 10
            reasons.append("Volume หนุนแรงขาย")

    if atr and price:
        atr_pct = atr / price * 100
        if 0.8 <= atr_pct <= 3.5:
            volatility_score += 5
        elif atr_pct > 5:
            volatility_score -= 8
            reasons.append("ความผันผวนสูง คุมขนาดไม้")

    raw_score = 50 + trend_score + momentum_score + volume_score + volatility_score
    score = max(0, min(100, int(raw_score)))

    if score >= 75:
        bias = "BULLISH / ฝั่งซื้อได้เปรียบ"
    elif score <= 35:
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

    probability = max(40, min(78, 50 + int((score - 50) * 0.55)))

    return {
        "price": price, "previous_close": previous_close, "change": change, "percent_change": percent_change,
        "ema6": ema6, "ema12": ema12, "ema50": ema50, "rsi": rsi, "atr": atr, "rvol": rvol,
        "regime": regime, "alignment": alignment, "mtf_states": mtf_states,
        "score": score, "bias": bias, "probability": probability,
        "support": support, "resistance": resistance, "stop_loss": stop_loss, "take_profit": take_profit,
        "reasons": reasons,
        "component_scores": {
            "trend": trend_score,
            "momentum": momentum_score,
            "volume": volume_score,
            "volatility": volatility_score,
        },
    }


# ============================================================
# OPTIONS HYBRID MAX FREE
# ============================================================
def options_hybrid_engine(asset, analysis):
    if asset["asset_type"] != "US_STOCK":
        return ""

    price = analysis["price"]
    atr = analysis["atr"] or (price * 0.015 if price else None)
    if not price or not atr:
        return ""

    score = analysis["score"]
    prob = analysis["probability"]

    call_strike = round_strike(price + atr * 0.60)
    call_sell = round_strike(price + atr * 1.70)
    put_strike = round_strike(price - atr * 0.60)
    put_sell = round_strike(price - atr * 1.70)

    entry_low = price - atr * 0.25
    entry_high = price + atr * 0.15
    tp1 = price + atr * 0.90
    tp2 = price + atr * 1.80
    sl = price - atr * 0.90

    put_entry_low = price - atr * 0.15
    put_entry_high = price + atr * 0.25
    put_tp1 = price - atr * 0.90
    put_tp2 = price - atr * 1.80
    put_sl = price + atr * 0.90

    if score >= 70:
        setup = f"""🧠 Options Hybrid Max Free
Setup: CALL / Bullish
Strike แนะนำ: {fmt_num(call_strike, 2)}C
Probability ประมาณ: {prob}%

Entry Zone: {fmt_num(entry_low)} - {fmt_num(entry_high)}
TP1: {fmt_num(tp1)}
TP2: {fmt_num(tp2)}
SL: {fmt_num(sl)}

Spread Scanner:
Bull Call Spread
Buy {fmt_num(call_strike, 2)}C
Sell {fmt_num(call_sell, 2)}C

ข้อควรระวัง: ไม่มี Delta/IV/OI จริง ใช้ ATR + AI Score ประมาณ"""
    elif score <= 35:
        setup = f"""🧠 Options Hybrid Max Free
Setup: PUT / Bearish
Strike แนะนำ: {fmt_num(put_strike, 2)}P
Probability ประมาณ: {prob}%

Entry Zone: {fmt_num(put_entry_low)} - {fmt_num(put_entry_high)}
TP1: {fmt_num(put_tp1)}
TP2: {fmt_num(put_tp2)}
SL: {fmt_num(put_sl)}

Spread Scanner:
Bear Put Spread
Buy {fmt_num(put_strike, 2)}P
Sell {fmt_num(put_sell, 2)}P

ข้อควรระวัง: ไม่มี Delta/IV/OI จริง ใช้ ATR + AI Score ประมาณ"""
    else:
        setup = f"""🧠 Options Hybrid Max Free
Setup: WAIT / Neutral
Probability ประมาณ: {prob}%

ยังไม่ควรรีบซื้อ CALL/PUT
รอราคาเลือกทางชัดเจนเหนือแนวต้านหรือหลุดแนวรับ

Idea เฝ้าดู:
CALL เหนือ {fmt_num(analysis['resistance'])}
PUT ใต้ {fmt_num(analysis['support'])}"""

    return setup


# ============================================================
# NEWS + REPORTS
# ============================================================
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
            params={"symbol": asset["news_symbol"], "from": week_ago.isoformat(), "to": today.isoformat(), "token": FINNHUB_API_KEY},
            headers=REQUEST_HEADERS,
            timeout=20,
        )
        items = r.json()
        if not isinstance(items, list) or not items:
            return "ไม่พบข่าวล่าสุดจาก Finnhub", 0
        headlines = [f"- {x.get('headline')}" for x in items[:3] if x.get("headline")]
        return "\n".join(headlines) if headlines else "ไม่มีหัวข้อข่าวสำคัญ", len(headlines)
    except Exception as e:
        return f"ดึงข่าวไม่สำเร็จ: {e}", 0


def build_trade_plan(price, atr, bias, asset_type=None, thai_factor=None):
    if not price:
        return "ข้อมูลราคาไม่พอสำหรับทำแผน 3 ไม้"
    if not atr:
        atr = price * 0.01

    buy1, buy2, buy3 = price - atr * 0.30, price - atr * 0.70, price - atr * 1.10
    sell1, sell2, sell3 = price + atr * 0.50, price + atr * 1.00, price + atr * 1.60
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
    thai_factor = bar_sell / price if bar_sell and price else None

    s1, s2, s3 = price - atr * 0.30, price - atr * 0.70, price - atr * 1.10
    r1, r2, r3 = price + atr * 0.50, price + atr * 1.00, price + atr * 1.60

    def gold_level(value):
        return f"{fmt_num(value, 0)} / {fmt_num(value * thai_factor, 0)}฿" if thai_factor else "N/A"

    note = "ดึงจากแหล่งอ้างอิงสมาคมค้าทองคำ" if not thai_gold.get("is_estimate") else "fallback เป็นค่าประมาณ เพราะดึงราคาสมาคมไม่สำเร็จ"

    return f"""📊 วิเคราะห์ทองคำ

XAUUSD
{fmt_num(price)} USD

🇹🇭 เทียบเงินบาท
{fmt_num(gold_thb_oz, 0)} บาท/ออนซ์

🏆 ราคาทองไทย
ทองแท่งรับซื้อ: {fmt_num(bar_buy, 0)} บาท
ทองแท่งขายออก: {fmt_num(bar_sell, 0)} บาท
ทองรูปพรรณขายออก: {fmt_num(ornament_sell, 0)} บาท
แหล่งราคา: {thai_gold.get('source')}
อัปเดต: {thai_gold.get('updated_at')}

AI Score V3: {analysis['score']}/100
Probability ประมาณ: {analysis['probability']}%
มุมมอง: {analysis['bias']}
Market Regime: {analysis['regime']}
Trend Alignment: {analysis['alignment']}

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

{build_trade_plan(price, atr, analysis['bias'], asset_type='GOLD', thai_factor=thai_factor)}

เหตุผลหลัก:
{chr(10).join("- " + r for r in reasons)}

📰 ข่าว/บริบท:
{news_text}

หมายเหตุ: ไม่ใช่คำแนะนำการลงทุน ราคาทองไทย{note}"""


def build_asset_report(user_text):
    asset = normalize_asset(user_text)
    quote, closes, highs, lows, opens, volumes = get_market_data(asset)
    analysis = analyze_signal(asset, quote, closes, highs, lows, opens, volumes)
    news_text, _ = fetch_news(asset)
    reasons = analysis["reasons"][:5] or ["ข้อมูลเทคนิคยังไม่พอ ให้ดูเป็นข้อมูลราคาเบื้องต้น"]

    if asset["asset_type"] == "GOLD":
        report = build_gold_report(asset, analysis, news_text, reasons)
        save_signal(asset["symbol"], asset["asset_type"], analysis["price"], analysis["score"], analysis["bias"], "GOLD", analysis["regime"], analysis["probability"], report)
        return report

    price_label = "$" if asset["currency"] == "USD" else "฿"
    source_text = "Yahoo Finance" if asset["asset_type"] == "THAI_STOCK" else "Twelve Data"
    opt_text = options_hybrid_engine(asset, analysis)

    mtf_lines = "\n".join([f"- {label}: {state}" for label, state in analysis["mtf_states"]]) or "- N/A"

    report = f"""📊 วิเคราะห์ {asset['display']}
แหล่งข้อมูล: {source_text}
เวลาไทย: {now_text()}

ราคา: {price_label}{fmt_num(analysis['price'])}
เปลี่ยนแปลง: {fmt_num(analysis['change'])} ({fmt_num(analysis['percent_change'])}%)

AI Score V3: {analysis['score']}/100
Probability ประมาณ: {analysis['probability']}%
มุมมอง: {analysis['bias']}
Market Regime: {analysis['regime']}
Trend Alignment: {analysis['alignment']}

Multi Timeframe:
{mtf_lines}

📈 Technical
EMA6: {fmt_num(analysis['ema6'])}
EMA12: {fmt_num(analysis['ema12'])}
EMA50: {fmt_num(analysis['ema50'])}
RSI14: {fmt_num(analysis['rsi'])}
ATR14: {fmt_num(analysis['atr'])}
RVOL: {fmt_num(analysis['rvol'])}

🎯 โซนราคา
แนวรับประมาณ: {price_label}{fmt_num(analysis['support'])}
แนวต้านประมาณ: {price_label}{fmt_num(analysis['resistance'])}
Stop loss เชิงระบบ: {price_label}{fmt_num(analysis['stop_loss'])}
Take profit เชิงระบบ: {price_label}{fmt_num(analysis['take_profit'])}

{build_trade_plan(analysis['price'], analysis['atr'], analysis['bias'])}

{opt_text}

เหตุผลหลัก:
{chr(10).join("- " + r for r in reasons)}

📰 ข่าว/บริบท:
{news_text}

หมายเหตุ: ไม่ใช่คำแนะนำการลงทุน V7 Hybrid ใช้ข้อมูลฟรีและประเมิน Options จาก underlying/ATR ไม่ใช่ Option Chain จริง"""

    sig_type = "BUY" if analysis["score"] >= AUTO_ALERT_MIN_SCORE else "SELL" if analysis["score"] <= AUTO_ALERT_MAX_SCORE else "NEUTRAL"
    save_signal(asset["symbol"], asset["asset_type"], analysis["price"], analysis["score"], analysis["bias"], sig_type, analysis["regime"], analysis["probability"], report)
    return report


# ============================================================
# LINE
# ============================================================
def line_reply(reply_token, text):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("LINE_CHANNEL_ACCESS_TOKEN is missing")
        return
    r = requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers={"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}", "Content-Type": "application/json"},
        json={"replyToken": reply_token, "messages": [{"type": "text", "text": text[:4900]}]},
        timeout=20,
    )
    if r.status_code >= 300:
        print("LINE reply failed:", r.status_code, r.text)


def line_push(user_id, text):
    if not LINE_CHANNEL_ACCESS_TOKEN or not user_id:
        return
    r = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}", "Content-Type": "application/json"},
        json={"to": user_id, "messages": [{"type": "text", "text": text[:4900]}]},
        timeout=20,
    )
    if r.status_code >= 300:
        print("LINE push failed:", r.status_code, r.text)


def verify_line_signature(body, signature):
    if not LINE_CHANNEL_SECRET:
        return True
    digest = hmac.new(LINE_CHANNEL_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
    valid_signature = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(valid_signature, signature or "")


def help_text():
    return """V7 Hybrid Max Free

พิมพ์ชื่อสินทรัพย์:
หุ้นสหรัฐ: NVDA, AAPL, TSLA, QQQ, SPY
หุ้นไทย: SCB, AOT, PTT, KBANK, CPALL, ADVANC
ทองคำ: ทองคำ, GOLD, XAUUSD

คำสั่ง:
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
        return f"ระบบยังอ่านคำสั่งนี้ไม่ได้ครับ\nลองพิมพ์ เช่น NVDA, AAPL, SCB, AOT, ทองคำ, GOLD\n\nError: {e}"


# ============================================================
# ROUTES + DASHBOARD
# ============================================================
def require_admin():
    if not ADMIN_TOKEN:
        return True
    return request.args.get("token") == ADMIN_TOKEN or request.headers.get("X-Admin-Token") == ADMIN_TOKEN


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "ok",
        "service": "AI Market LINE Bot V7 Hybrid Max Free",
        "time_th": now_text(),
        "watchlist": WATCHLIST,
        "routes": ["/health", "/gold-test", "/dashboard", "/api/signals", "/api/watchlist"],
    })


@app.route("/health", methods=["GET"])
def health():
    return "OK", 200


@app.route("/gold-test", methods=["GET"])
def gold_test():
    asset = normalize_asset("ทองคำ")
    quote, closes, highs, lows, opens, volumes = get_market_data(asset)
    analysis = analyze_signal(asset, quote, closes, highs, lows, opens, volumes)
    usd_thb = get_usd_thb_rate()
    return jsonify({"xauusd": analysis["price"], "usd_thb": usd_thb, "thai_gold": get_thai_gold_price_or_estimate(analysis["price"], usd_thb), "time_th": now_text()})


@app.route("/api/watchlist", methods=["GET"])
def api_watchlist():
    return jsonify({"watchlist": WATCHLIST})


@app.route("/api/signals", methods=["GET"])
def api_signals():
    if not require_admin():
        return jsonify({"error": "unauthorized"}), 401
    conn = db()
    rows = conn.execute("SELECT * FROM signals ORDER BY id DESC LIMIT 100").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/dashboard", methods=["GET"])
def dashboard():
    if not require_admin():
        return Response("Unauthorized", status=401)
    conn = db()
    rows = conn.execute("SELECT * FROM signals ORDER BY id DESC LIMIT 50").fetchall()
    conn.close()
    html_rows = "".join(
        f"<tr><td>{r['created_at']}</td><td>{r['symbol']}</td><td>{r['asset_type']}</td><td>{fmt_num(r['price'])}</td><td>{r['score']}</td><td>{r['probability']}%</td><td>{r['signal_type']}</td><td>{r['regime']}</td><td>{r['bias']}</td></tr>"
        for r in rows
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>V7 Hybrid Dashboard</title>
<style>body{{font-family:Arial;padding:24px;background:#f7f7f7}}table{{border-collapse:collapse;width:100%;background:#fff}}td,th{{border:1px solid #ddd;padding:8px}}th{{background:#111;color:#fff}}</style>
</head><body><h1>AI Market LINE Bot V7 Hybrid Max Free</h1><p>Time TH: {now_text()}</p>
<table><thead><tr><th>Time</th><th>Symbol</th><th>Asset</th><th>Price</th><th>Score</th><th>Prob</th><th>Signal</th><th>Regime</th><th>Bias</th></tr></thead><tbody>{html_rows}</tbody></table>
</body></html>"""


@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_data()
    signature = request.headers.get("X-Line-Signature", "")
    if not verify_line_signature(body, signature):
        abort(400)
    payload = request.get_json(silent=True) or {}
    for event in payload.get("events", []):
        if event.get("type") != "message":
            continue
        reply_token = event.get("replyToken")
        source = event.get("source", {})
        user_id = source.get("userId", "")
        message = event.get("message", {})
        if message.get("type") != "text":
            line_reply(reply_token, "ตอนนี้รองรับเฉพาะข้อความเท่านั้นครับ")
            continue
        line_reply(reply_token, handle_message(user_id, message.get("text", "")))
    return "OK", 200


# ============================================================
# AUTO ALERTS
# ============================================================
def should_send_alert(symbol, score):
    now_ts = time.time()
    last_ts = get_last_alert_ts(symbol)
    if now_ts - last_ts < ALERT_EVERY_MINUTES * 60:
        return False
    if score >= AUTO_ALERT_MIN_SCORE or score <= AUTO_ALERT_MAX_SCORE:
        set_last_alert_ts(symbol, now_ts)
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
                            header = f"🚨 BUY/MOMENTUM ALERT: {symbol}\n\n" if analysis["score"] >= AUTO_ALERT_MIN_SCORE else f"⚠️ SELL/WEAKNESS ALERT: {symbol}\n\n"
                            for user_id in ALERT_USER_IDS:
                                line_push(user_id, header + report)
                        time.sleep(3)
                    except Exception as e:
                        print(f"Auto alert error for {symbol}: {e}")
            time.sleep(60)
        except Exception as e:
            print(f"Auto alert loop error: {e}")
            time.sleep(60)


init_db()

if __name__ == "__main__":
    if ENABLE_AUTO_ALERTS and ALERT_USER_IDS:
        threading.Thread(target=auto_alert_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
