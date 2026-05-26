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
    "TISCO", "LH", "MTC", "SAWAD", "TIDLOR", "OSP", "CBG", "TU", "IVL",
    "HANA", "DOHOME", "COM7", "JMART", "JMT", "BANPU", "BCP", "IRPC",
    "SPRC", "RATCH", "EGCO", "WHA", "AMATA", "ROJNA", "CK", "STECON",
    "ITD", "STPI", "TASCO", "GLOBAL", "MEGA", "CHG", "BCH", "VGI",
    "PLANB", "BEC", "MAJOR", "RS", "SINGER", "SABUY", "FORTH", "KCE",
    "SYNEX", "ITEL", "INET", "BE8", "BBIK", "DITTO", "SISB", "AU",
    "ZEN", "M", "TKN", "ICHI", "SAPPE", "RBF", "WARRIX", "MOSHI",
    "BJC", "MAKRO", "BTS", "MRT", "SIRI", "AP", "SPALI", "ORI",
    "ANAN", "NOBLE", "QH", "PSH", "LPN", "SENA", "AWC", "ERW",
    "BA", "AAV", "NEX", "BYD", "TTA", "PSL", "RCL", "STA", "STGT",
    "NER", "CPF", "GFPT", "BTG", "TFG", "XO", "PRM", "III", "JAS",
    "MONO", "THCOM", "INTUCH", "TLI", "BLA", "TIPH", "BAM", "CHAYO",
    "ASK", "KGI", "MST", "CGH", "TQM", "MENA", "SNNP", "PLUS"
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
# DYNAMIC THAI STOCK DETECTION V7.3
# ============================================================
def looks_like_stock_symbol(key):
    return bool(re.fullmatch(r"[A-Z0-9]{1,12}", key))


def yahoo_bk_exists(symbol):
    """Return True if Yahoo Finance has data for SYMBOL.BK.
    This lets the bot support Thai stocks without maintaining THAI_SYMBOLS manually.
    """
    if not looks_like_stock_symbol(symbol):
        return False

    cache_key = f"YF_BK_EXISTS:{symbol}"
    cached = cache_get(cache_key)
    if cached is not None:
        return bool(cached)

    # Avoid obvious US ETFs/indices from being tested as Thai first.
    known_us = {
        "NVDA", "AAPL", "TSLA", "MSFT", "META", "GOOGL", "GOOG", "AMZN",
        "NFLX", "AMD", "INTC", "QQQ", "SPY", "IWM", "DIA", "TQQQ", "SQQQ",
        "SOXL", "SOXS", "PLTR", "COIN", "MSTR", "AVGO", "SMCI"
    }
    if symbol in known_us:
        cache_set(cache_key, False)
        return False

    try:
        data = yf.Ticker(f"{symbol}.BK").history(period="10d", interval="1d", auto_adjust=False)
        exists = data is not None and not data.empty and "Close" in data.columns
        cache_set(cache_key, exists)
        return bool(exists)
    except Exception:
        cache_set(cache_key, False)
        return False

# ============================================================
# ASSET NORMALIZATION
# ============================================================
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
        return {
            "display": f"{key}.BK",
            "symbol": key,
            "yf_symbol": f"{key}.BK",
            "currency": "THB",
            "asset_type": "THAI_STOCK",
            "news_symbol": key,
        }

    if key.endswith(".SET"):
        key = key.replace(".SET", "")
        return {
            "display": f"{key}.BK",
            "symbol": key,
            "yf_symbol": f"{key}.BK",
            "currency": "THB",
            "asset_type": "THAI_STOCK",
            "news_symbol": key,
        }

    # 1) Known Thai symbols.
    if key in THAI_SYMBOLS:
        return {
            "display": f"{key}.BK",
            "symbol": key,
            "yf_symbol": f"{key}.BK",
            "currency": "THB",
            "asset_type": "THAI_STOCK",
            "news_symbol": key,
        }

    # 2) Dynamic Thai detection:
    # If Yahoo Finance has KEY.BK data, treat it as Thai stock.
    # This fixes BEAUTY, HANA, DOHOME and future Thai tickers without manually editing THAI_SYMBOLS.
    if yahoo_bk_exists(key):
        return {
            "display": f"{key}.BK",
            "symbol": key,
            "yf_symbol": f"{key}.BK",
            "currency": "THB",
            "asset_type": "THAI_STOCK",
            "news_symbol": key,
        }

    # 3) Otherwise treat as US stock / ETF and use Twelve Data.
    return {
        "display": key,
        "symbol": key,
        "yf_symbol": key,
        "currency": "USD",
        "asset_type": "US_STOCK",
        "news_symbol": key,
    }


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
    """Fetch official Thai gold price from Gold Traders Association.

    Priority:
    1) classic.goldtraders.or.th/UpdatePriceList.aspx
    2) classic.goldtraders.or.th/DailyPrices.aspx
    3) classic/homepage/new site loose parser
    """
    cached = cache_get("GOLDTRADERS")
    if cached:
        return cached

    def parse_update_price_list(html, url):
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)

        row_pattern = re.compile(
            r"(\d{2}/\d{2}/\d{4})\s+"
            r"(\d{1,2}:\d{2})\s+"
            r"(\d+)\s+"
            r"(\d{2,3},\d{3}\.\d{2})\s+"
            r"(\d{2,3},\d{3}\.\d{2})\s+"
            r"(\d{2,3},\d{3}\.\d{2})\s+"
            r"(\d{2,3},\d{3}\.\d{2})\s+"
            r"(\d{1,2},\d{3}\.\d{2})\s+"
            r"(\d{2}\.\d{2})\s*"
            r"([+-]?\d+)?"
        )
        m = row_pattern.search(text)
        if not m:
            return None

        date_th, time_th, round_no = m.group(1), m.group(2), m.group(3)
        result = {
            "bar_buy": safe_float(m.group(4)),
            "bar_sell": safe_float(m.group(5)),
            "ornament_buy": safe_float(m.group(6)),
            "ornament_sell": safe_float(m.group(7)),
            "gold_spot": safe_float(m.group(8)),
            "usd_thb_ref": safe_float(m.group(9)),
            "change": safe_float(m.group(10), 0),
            "source": "สมาคมค้าทองคำ / GoldTraders UpdatePriceList",
            "updated_at": f"{date_th} {time_th} ครั้งที่ {round_no}",
            "raw_url": url,
            "is_estimate": False,
        }
        return result if result["bar_buy"] and result["bar_sell"] else None

    def parse_daily_prices(html, url):
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)

        bar = re.search(
            r"ทองคำแท่ง\s*96\.5%.*?(\d{2,3},\d{3}\.\d{2})\s+(\d{2,3},\d{3}\.\d{2})",
            text,
            re.S,
        )
        ornament = re.search(
            r"ทองรูปพรรณ\s*96\.5%.*?(\d{1,2},\d{3}\.\d{2})\s+(\d{2,3},\d{3}\.\d{2})\s+(\d{2,3},\d{3}\.\d{2})",
            text,
            re.S,
        )
        if not bar:
            return None

        result = {
            "bar_buy": safe_float(bar.group(1)),
            "bar_sell": safe_float(bar.group(2)),
            "ornament_buy": safe_float(ornament.group(2)) if ornament else None,
            "ornament_sell": safe_float(ornament.group(3)) if ornament else None,
            "gold_spot": None,
            "usd_thb_ref": None,
            "change": None,
            "source": "สมาคมค้าทองคำ / GoldTraders DailyPrices",
            "updated_at": now_text(),
            "raw_url": url,
            "is_estimate": False,
        }
        return result if result["bar_buy"] and result["bar_sell"] else None

    def parse_homepage_loose(html, url):
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)

        bar = re.search(
            r"ทองคำแท่ง\s*96\.5%.*?รับซื้อ\s*(\d{2,3},\d{3}\.\d{2}).*?ขายออก\s*(\d{2,3},\d{3}\.\d{2})",
            text,
            re.S,
        )
        ornament = re.search(
            r"ทองรูปพรรณ\s*96\.5%.*?(?:ฐานภาษี|รับซื้อ)\s*(\d{2,3},\d{3}\.\d{2}).*?ขายออก\s*(\d{2,3},\d{3}\.\d{2})",
            text,
            re.S,
        )
        if bar:
            return {
                "bar_buy": safe_float(bar.group(1)),
                "bar_sell": safe_float(bar.group(2)),
                "ornament_buy": safe_float(ornament.group(1)) if ornament else None,
                "ornament_sell": safe_float(ornament.group(2)) if ornament else None,
                "gold_spot": None,
                "usd_thb_ref": None,
                "change": None,
                "source": "สมาคมค้าทองคำ / GoldTraders Homepage",
                "updated_at": now_text(),
                "raw_url": url,
                "is_estimate": False,
            }

        bidask = re.search(
            r"(?:GTA Gold Price|Gold Price).*?Bid:\s*(\d{2,3},\d{3}\.\d{2}).*?Ask:\s*(\d{2,3},\d{3}\.\d{2})",
            text,
            re.S,
        )
        if bidask:
            return {
                "bar_buy": safe_float(bidask.group(1)),
                "bar_sell": safe_float(bidask.group(2)),
                "ornament_buy": None,
                "ornament_sell": None,
                "gold_spot": None,
                "usd_thb_ref": None,
                "change": None,
                "source": "สมาคมค้าทองคำ / GoldTraders GTA BidAsk",
                "updated_at": now_text(),
                "raw_url": url,
                "is_estimate": False,
            }
        return None

    sources = [
        ("https://classic.goldtraders.or.th/UpdatePriceList.aspx", parse_update_price_list),
        ("https://classic.goldtraders.or.th/DailyPrices.aspx", parse_daily_prices),
        ("https://classic.goldtraders.or.th/", parse_homepage_loose),
        ("https://www.goldtraders.or.th/", parse_homepage_loose),
        ("https://newgta.goldtraders.or.th/homepage_pre", parse_homepage_loose),
    ]

    for url, parser in sources:
        try:
            r = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
            if r.status_code != 200:
                continue
            result = parser(r.text, url)
            if result and result.get("bar_buy") and result.get("bar_sell"):
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
        try:
            quote = td_get_quote(asset)
            closes, highs, lows, opens, volumes = td_get_series(asset)
            result = (quote, closes, highs, lows, opens, volumes)
        except Exception as e:
            # V7.3 safety fallback:
            # If user typed a Thai ticker not in THAI_SYMBOLS and Yahoo dynamic check failed due timeout,
            # try SYMBOL.BK one last time before returning Twelve Data error.
            test_asset = {
                "display": f"{asset['symbol']}.BK",
                "symbol": asset["symbol"],
                "yf_symbol": f"{asset['symbol']}.BK",
                "currency": "THB",
                "asset_type": "THAI_STOCK",
                "news_symbol": asset["symbol"],
            }
            try:
                result = yf_get_quote_and_series(test_asset)
                # Mutate current asset so downstream report labels correctly.
                asset.update(test_asset)
            except Exception:
                raise e

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
# DIVIDEND + VALUATION V7.1
# ============================================================
def fmt_date_from_timestamp(ts):
    try:
        if not ts:
            return "N/A"
        return (datetime.utcfromtimestamp(int(ts)) + timedelta(hours=7)).strftime("%d/%m/%Y")
    except Exception:
        return "N/A"


def get_fundamental_data(asset):
    """Fetch free fundamental/dividend/event data mainly from Yahoo Finance.
    Not all tickers have complete data. Missing fields return N/A.
    """
    if asset["asset_type"] == "GOLD":
        return {}

    cache_key = f"FUND:{asset['yf_symbol']}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    result = {
        "market_cap": None,
        "trailing_pe": None,
        "forward_pe": None,
        "dividend_yield": None,
        "dividend_rate": None,
        "ex_dividend_date": "N/A",
        "earnings_date": "N/A",
        "fifty_two_week_low": None,
        "fifty_two_week_high": None,
        "source": "Yahoo Finance",
    }

    try:
        ticker = yf.Ticker(asset["yf_symbol"])
        info = {}
        try:
            info = ticker.get_info() or {}
        except Exception:
            try:
                info = ticker.info or {}
            except Exception:
                info = {}

        result["market_cap"] = safe_float(info.get("marketCap"))
        result["trailing_pe"] = safe_float(info.get("trailingPE"))
        result["forward_pe"] = safe_float(info.get("forwardPE"))
        result["dividend_yield"] = safe_float(info.get("dividendYield"))
        result["dividend_rate"] = safe_float(info.get("dividendRate"))
        result["fifty_two_week_low"] = safe_float(info.get("fiftyTwoWeekLow"))
        result["fifty_two_week_high"] = safe_float(info.get("fiftyTwoWeekHigh"))

        # Yahoo sometimes provides timestamp seconds.
        result["ex_dividend_date"] = fmt_date_from_timestamp(info.get("exDividendDate"))

        # Earnings date fallback.
        try:
            ed = ticker.get_earnings_dates(limit=1)
            if ed is not None and not ed.empty:
                result["earnings_date"] = str(ed.index[0].date())
        except Exception:
            pass

        # Dividend fallback from historical dividends if dividendRate missing.
        try:
            divs = ticker.dividends
            if divs is not None and not divs.empty:
                last_div = float(divs.iloc[-1])
                result["last_dividend"] = last_div
                result["last_dividend_date"] = str(divs.index[-1].date())
            else:
                result["last_dividend"] = None
                result["last_dividend_date"] = "N/A"
        except Exception:
            result["last_dividend"] = None
            result["last_dividend_date"] = "N/A"

    except Exception as e:
        print("get_fundamental_data error:", e)

    cache_set(cache_key, result)
    return result


def human_market_cap(value, currency):
    if value is None:
        return "N/A"
    try:
        value = float(value)
        suffix = ""
        scaled = value
        if abs(value) >= 1_000_000_000_000:
            scaled = value / 1_000_000_000_000
            suffix = "T"
        elif abs(value) >= 1_000_000_000:
            scaled = value / 1_000_000_000
            suffix = "B"
        elif abs(value) >= 1_000_000:
            scaled = value / 1_000_000
            suffix = "M"
        return f"{currency}{scaled:,.2f}{suffix}"
    except Exception:
        return "N/A"


def dividend_yield_text(value):
    if value is None:
        return "N/A"
    try:
        # Yahoo often returns 0.0285 for 2.85%.
        val = float(value)
        if val <= 1:
            val *= 100
        return f"{val:.2f}%"
    except Exception:
        return "N/A"


def valuation_engine(asset, analysis, fundamentals):
    """Simple rule-based valuation using free data.
    This is not intrinsic valuation; it is relative/technical valuation.
    """
    if asset["asset_type"] == "GOLD":
        return "", "N/A"

    price = analysis.get("price")
    ema50 = analysis.get("ema50")
    rsi = analysis.get("rsi")
    pe = fundamentals.get("trailing_pe")
    fwd_pe = fundamentals.get("forward_pe")
    div_yield = fundamentals.get("dividend_yield")
    low52 = fundamentals.get("fifty_two_week_low")
    high52 = fundamentals.get("fifty_two_week_high")

    score = 0
    reasons = []

    # 52W position
    if price and low52 and high52 and high52 > low52:
        pos = (price - low52) / (high52 - low52)
        if pos <= 0.25:
            score -= 2
            reasons.append("ราคาอยู่โซนล่างของกรอบ 52 สัปดาห์")
        elif pos >= 0.80:
            score += 2
            reasons.append("ราคาอยู่ใกล้โซนบนของกรอบ 52 สัปดาห์")
        else:
            reasons.append("ราคาอยู่กลางกรอบ 52 สัปดาห์")

    # EMA50 distance
    if price and ema50:
        dist = (price - ema50) / ema50 * 100
        if dist >= 12:
            score += 2
            reasons.append("ราคาอยู่เหนือ EMA50 ค่อนข้างมาก")
        elif dist <= -12:
            score -= 2
            reasons.append("ราคาอยู่ต่ำกว่า EMA50 ค่อนข้างมาก")
        else:
            reasons.append("ราคาไม่ห่างจาก EMA50 มากเกินไป")

    # RSI valuation pressure
    if rsi is not None:
        if rsi >= 72:
            score += 1
            reasons.append("RSI สูง มีความเสี่ยงไล่ราคา")
        elif rsi <= 35:
            score -= 1
            reasons.append("RSI ต่ำ มีโอกาสอยู่ในโซนถูกเชิงเทคนิค")

    # PE rough filter
    use_pe = pe or fwd_pe
    if use_pe:
        if use_pe >= 45:
            score += 2
            reasons.append("P/E สูงมาก ต้องระวังราคาสะท้อนความคาดหวังไปมากแล้ว")
        elif use_pe >= 25:
            score += 1
            reasons.append("P/E ค่อนข้างสูง")
        elif 0 < use_pe <= 12:
            score -= 1
            reasons.append("P/E อยู่ในโซนไม่แพงเมื่อเทียบเชิงตัวเลข")
        else:
            reasons.append("P/E อยู่ในโซนกลาง")

    # Dividend yield rough filter
    if div_yield:
        dy = div_yield * 100 if div_yield <= 1 else div_yield
        if dy >= 5:
            score -= 1
            reasons.append("Dividend Yield สูง น่าสนใจสำหรับสายปันผล")
        elif dy < 1:
            score += 1
            reasons.append("Dividend Yield ต่ำ ไม่ได้ช่วยรองรับ valuation มากนัก")

    if score <= -3:
        status = "ถูกน่าสนใจ"
    elif score <= -1:
        status = "ค่อนข้างถูก"
    elif score <= 2:
        status = "กลาง / พอรับได้"
    elif score <= 4:
        status = "แพงเล็กน้อย"
    else:
        status = "แพง / ระวังไล่ราคา"

    text = f"""💎 Dividend + Valuation

สถานะราคา: {status}

Market Cap: {human_market_cap(fundamentals.get('market_cap'), '฿' if asset['currency'] == 'THB' else '$')}
P/E: {fmt_num(fundamentals.get('trailing_pe'))}
Forward P/E: {fmt_num(fundamentals.get('forward_pe'))}
Dividend Yield: {dividend_yield_text(fundamentals.get('dividend_yield'))}
Dividend Rate: {fmt_num(fundamentals.get('dividend_rate'))}

XD / Ex-dividend: {fundamentals.get('ex_dividend_date', 'N/A')}
วันประกาศงบ: {fundamentals.get('earnings_date', 'N/A')}
ปันผลล่าสุด: {fmt_num(fundamentals.get('last_dividend'))}
วันที่ปันผลล่าสุด: {fundamentals.get('last_dividend_date', 'N/A')}

52W Low: {fmt_num(fundamentals.get('fifty_two_week_low'))}
52W High: {fmt_num(fundamentals.get('fifty_two_week_high'))}

เหตุผล valuation:
{chr(10).join("- " + r for r in reasons[:6]) if reasons else "- ข้อมูลพื้นฐานไม่พอสำหรับประเมินถูก/แพง"}"""

    return text, status

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

    fundamentals = get_fundamental_data(asset)
    valuation_text, valuation_status = valuation_engine(asset, analysis, fundamentals)

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

{valuation_text}

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
# THAILAND OIL PRICE V7.3.2 TODAY / TOMORROW
# ============================================================
OIL_WORDS = {
    "น้ำมัน", "ราคาน้ำมัน", "ราคาน้ํามัน",
    "oil", "oli", "oill", "fuel", "ptt", "บางจาก", "น้ำมันไทย"
}

def normalize_oil_name(name):
    raw = str(name or "").strip()
    n = raw.lower().replace(" ", "").replace("-", "").replace("_", "")
    mapping = [
        ("gasohol95", "แก๊สโซฮอล์ 95"), ("แก๊สโซฮอล์95", "แก๊สโซฮอล์ 95"),
        ("gasohol91", "แก๊สโซฮอล์ 91"), ("แก๊สโซฮอล์91", "แก๊สโซฮอล์ 91"),
        ("gsh95", "แก๊สโซฮอล์ 95"), ("gsh91", "แก๊สโซฮอล์ 91"),
        ("e20", "แก๊สโซฮอล์ E20"), ("e85", "แก๊สโซฮอล์ E85"),
        ("benzine95", "เบนซิน 95"), ("gasoline95", "เบนซิน 95"), ("เบนซิน95", "เบนซิน 95"),
        ("dieselb7", "ดีเซล B7"), ("ดีเซลb7", "ดีเซล B7"),
        ("premiumdiesel", "ดีเซลพรีเมียม"), ("superpowerdiesel", "ดีเซลพรีเมียม"),
        ("ดีเซลพรีเมียม", "ดีเซลพรีเมียม"),
        ("diesel", "ดีเซล"), ("ดีเซล", "ดีเซล"),
    ]
    for key, display in mapping:
        if key in n:
            return display
    return raw


def oil_change_text(today, tomorrow):
    if today is None or tomorrow is None:
        return "N/A"
    diff = round(float(tomorrow) - float(today), 2)
    if abs(diff) < 0.001:
        return "ไม่เปลี่ยนแปลง"
    sign = "+" if diff > 0 else ""
    return f"{sign}{diff:.2f}"


def split_oil_today_tomorrow(prices):
    """Normalize oil price object.
    Accepts either:
    - {"today": {...}, "tomorrow": {...}}
    - flat {"แก๊สโซฮอล์ 95": 35.45}
    """
    if not prices:
        return {}, {}

    if isinstance(prices, dict) and ("today" in prices or "tomorrow" in prices):
        return prices.get("today", {}) or {}, prices.get("tomorrow", {}) or {}

    return prices, {}


def parse_bangchak_numbers_by_order(text):
    """Parse current/tomorrow prices by known Bangchak widget order when names are absent."""
    nums = re.findall(r"\b(\d{2}\.\d{1,2})\b", text)
    values = []
    for n in nums:
        v = safe_float(n)
        if v and 10 <= v <= 90:
            values.append(v)

    names = [
        "แก๊สโซฮอล์ 95",
        "แก๊สโซฮอล์ 91",
        "เบนซิน 95",
        "แก๊สโซฮอล์ E85",
        "แก๊สโซฮอล์ E20",
        "ดีเซล B7",
        "ดีเซลพรีเมียม",
        "ดีเซล",
    ]

    # If page exposes today and tomorrow in adjacent blocks, total can be >= 12.
    # Best effort: first 8 = today, next 8 = tomorrow. If fewer, today only.
    today = {}
    tomorrow = {}

    if len(values) >= 6:
        for i in range(min(len(names), len(values))):
            today[names[i]] = values[i]

    if len(values) >= 12:
        start = min(len(names), len(values) // 2)
        # More conservative: use next values after first product group.
        for i in range(min(len(names), len(values) - start)):
            tomorrow[names[i]] = values[start + i]

    return today, tomorrow


def extract_oil_prices_from_text(combo):
    """Extract product prices from text. Also attempts tomorrow price if the page has 'tomorrow' nearby."""
    product_patterns = [
        ("เบนซิน 95", [r"เบนซิน\s*95", r"Gasoline\s*95"]),
        ("แก๊สโซฮอล์ 95", [r"แก๊สโซฮอล์\s*95", r"Gasohol\s*95", r"GSH\s*95"]),
        ("แก๊สโซฮอล์ 91", [r"แก๊สโซฮอล์\s*91", r"Gasohol\s*91", r"GSH\s*91"]),
        ("แก๊สโซฮอล์ E20", [r"E20"]),
        ("แก๊สโซฮอล์ E85", [r"E85"]),
        ("ดีเซล B7", [r"ดีเซล\s*B7", r"Diesel\s*B7"]),
        ("ดีเซลพรีเมียม", [r"ดีเซล\s*พรีเมียม", r"Premium\s*Diesel", r"Hi\s*Premium", r"Super\s*Power\s*Diesel"]),
        ("ดีเซล", [r"ดีเซล(?!\s*B7)(?!\s*พรีเมียม)", r"Diesel(?!\s*B7)(?!\s*Premium)"]),
    ]

    normalized = re.sub(r"\s+", " ", combo)
    today, tomorrow = {}, {}

    for display, pats in product_patterns:
        for pat in pats:
            mm = re.search(pat + r".{0,180}?(\d{2}\.\d{1,2})", normalized, re.I)
            if mm:
                today[display] = safe_float(mm.group(1))
                break

    # Try explicit tomorrow/next day blocks.
    tomorrow_keywords = r"(?:พรุ่งนี้|Tomorrow|tomorrow|วันพรุ่งนี้|ราคาใหม่|New Price)"
    for display, pats in product_patterns:
        for pat in pats:
            mm = re.search(tomorrow_keywords + r".{0,300}?" + pat + r".{0,180}?(\d{2}\.\d{1,2})", normalized, re.I)
            if not mm:
                mm = re.search(pat + r".{0,180}?" + tomorrow_keywords + r".{0,180}?(\d{2}\.\d{1,2})", normalized, re.I)
            if mm:
                tomorrow[display] = safe_float(mm.group(1))
                break

    return today, tomorrow


def get_ptt_oil_prices():
    """Fetch current retail oil prices from PTT OR SOAP Web Service.
    PTT endpoint usually gives current price. Tomorrow price may not be available.
    """
    cached = cache_get("THAI_OIL_PTT")
    if cached:
        return cached

    soap_body = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema"
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <CurrentOilPrice xmlns="http://www.pttor.com">
      <Language>TH</Language>
    </CurrentOilPrice>
  </soap:Body>
</soap:Envelope>"""

    try:
        r = requests.post(
            "https://orapiweb.pttor.com/oilservice/OilPrice.asmx",
            data=soap_body.encode("utf-8"),
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": '"https://orapiweb.pttor.com/CurrentOilPrice"',
                "User-Agent": REQUEST_HEADERS.get("User-Agent", "Mozilla/5.0"),
            },
            timeout=20,
        )
        if r.status_code != 200:
            return None

        xml_text = r.text
        m = re.search(r"<CurrentOilPriceResult[^>]*>(.*?)</CurrentOilPriceResult>", xml_text, re.S)
        if not m:
            return None

        inner = m.group(1)
        inner = inner.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
        text = BeautifulSoup(inner, "html.parser").get_text(" ", strip=True)
        combo = inner + " " + xml_text + " " + text

        today, tomorrow = extract_oil_prices_from_text(combo)

        # JSON/XML key-value fallback.
        for mm in re.finditer(
            r'(?:"?(?:product|productName|oilName|name|title)"?\s*[:=]\s*"([^"]+)".{0,180}?"?(?:price|currentPrice|Price)"?\s*[:=]\s*"?(\d{2}\.\d{1,2})"?)',
            combo,
            re.I | re.S,
        ):
            name = normalize_oil_name(mm.group(1))
            price = safe_float(mm.group(2))
            if price:
                today[name] = price

        today = {normalize_oil_name(k): float(v) for k, v in today.items() if v and 10 <= float(v) <= 90}
        tomorrow = {normalize_oil_name(k): float(v) for k, v in tomorrow.items() if v and 10 <= float(v) <= 90}

        if today:
            result = {
                "source": "PTT OR OilPrice Web Service",
                "updated_at": now_text(),
                "raw_url": "https://orapiweb.pttor.com/oilservice/OilPrice.asmx",
                "prices": {"today": today, "tomorrow": tomorrow},
                "has_tomorrow": bool(tomorrow),
                "is_estimate": False,
            }
            cache_set("THAI_OIL_PTT", result)
            return result

    except Exception as e:
        print("PTT oil fetch error:", e)

    return None


def get_bangchak_oil_prices():
    cached = cache_get("THAI_OIL_BANGCHAK")
    if cached:
        return cached

    urls = [
        "https://oil-price.bangchak.co.th/ApiOilPrice2/th",
        "https://oil-price.bangchak.co.th/ApiOilPrice2/en",
        "https://oil-price.bangchak.co.th/BcpOilPrice2/th",
        "https://oil-price.bangchak.co.th/BcpOilPrice2/en",
        "https://www.bangchak.co.th/th/oilprice/historical",
        "https://www.bangchak.co.th/en/oilprice/historical",
    ]

    for url in urls:
        try:
            r = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
            if r.status_code != 200:
                continue

            text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
            combo = r.text + " " + text

            today, tomorrow = extract_oil_prices_from_text(combo)

            # If names fail, map numeric order.
            if len(today) < 4:
                t2, tm2 = parse_bangchak_numbers_by_order(combo)
                today.update(t2)
                tomorrow.update(tm2)

            # Try JSON pairs with today/tomorrow fields.
            for mm in re.finditer(
                r'(?:"?(?:productName|oilName|name|title)"?\s*[:=]\s*"([^"]+)".{0,220}?"?(?:todayPrice|currentPrice|price|Price)"?\s*[:=]\s*"?(\d{2}\.\d{1,2})"?)',
                combo,
                re.I | re.S,
            ):
                name = normalize_oil_name(mm.group(1))
                price = safe_float(mm.group(2))
                if price:
                    today[name] = price

            for mm in re.finditer(
                r'(?:"?(?:productName|oilName|name|title)"?\s*[:=]\s*"([^"]+)".{0,220}?"?(?:tomorrowPrice|nextPrice|priceTomorrow)"?\s*[:=]\s*"?(\d{2}\.\d{1,2})"?)',
                combo,
                re.I | re.S,
            ):
                name = normalize_oil_name(mm.group(1))
                price = safe_float(mm.group(2))
                if price:
                    tomorrow[name] = price

            today = {normalize_oil_name(k): float(v) for k, v in today.items() if v and 10 <= float(v) <= 90}
            tomorrow = {normalize_oil_name(k): float(v) for k, v in tomorrow.items() if v and 10 <= float(v) <= 90}

            if today:
                result = {
                    "source": "บางจาก / Bangchak",
                    "updated_at": now_text(),
                    "raw_url": url,
                    "prices": {"today": today, "tomorrow": tomorrow},
                    "has_tomorrow": bool(tomorrow),
                    "is_estimate": False,
                }
                cache_set("THAI_OIL_BANGCHAK", result)
                return result

        except Exception as e:
            print("Bangchak oil fetch error:", url, e)

    return None


def get_thai_oil_prices():
    # Prefer Bangchak first for today/tomorrow, then PTT current price.
    result = get_bangchak_oil_prices()
    if result and result.get("prices", {}).get("today"):
        return result

    result = get_ptt_oil_prices()
    if result and result.get("prices", {}).get("today"):
        return result

    return {
        "source": "N/A",
        "updated_at": now_text(),
        "raw_url": None,
        "prices": {"today": {}, "tomorrow": {}},
        "has_tomorrow": False,
        "is_estimate": False,
        "error": "ดึงราคาน้ำมันไทยไม่สำเร็จ อาจเกิดจากแหล่งข้อมูลเปลี่ยนโครงสร้างหรือบล็อก request",
    }


def build_oil_report():
    data = get_thai_oil_prices()
    today, tomorrow = split_oil_today_tomorrow(data.get("prices", {}))

    order = [
        "เบนซิน 95",
        "แก๊สโซฮอล์ 95",
        "แก๊สโซฮอล์ 91",
        "แก๊สโซฮอล์ E20",
        "แก๊สโซฮอล์ E85",
        "ดีเซล",
        "ดีเซล B7",
        "ดีเซลพรีเมียม",
    ]

    all_names = []
    for name in order:
        if name in today or name in tomorrow:
            all_names.append(name)
    for name in list(today.keys()) + list(tomorrow.keys()):
        if name not in all_names:
            all_names.append(name)

    if not all_names:
        return f"""⛽ ราคาน้ำมันประเทศไทย

ดึงข้อมูลไม่สำเร็จ

สาเหตุ:
{data.get('error', 'ไม่พบราคาน้ำมันจากแหล่งข้อมูล')}

แหล่งข้อมูลที่พยายามดึง:
1) Bangchak Oil Price Widget/API
2) PTT OR OilPrice Web Service

หมายเหตุ: ระบบไม่คำนวณราคาน้ำมันเอง เพราะราคาขายปลีกไทยต้องอ้างอิงประกาศผู้ค้าน้ำมัน"""

    lines_today = []
    lines_tomorrow = []
    lines_change = []

    for name in all_names:
        t = today.get(name)
        tm = tomorrow.get(name)

        lines_today.append(f"{name}: {fmt_num(t)} บาท/ลิตร" if t is not None else f"{name}: N/A")

        if tm is not None:
            lines_tomorrow.append(f"{name}: {fmt_num(tm)} บาท/ลิตร")
            lines_change.append(f"{name}: {oil_change_text(t, tm)}")
        else:
            lines_tomorrow.append(f"{name}: ยังไม่ประกาศ")
            lines_change.append(f"{name}: N/A")

    tomorrow_note = "" if data.get("has_tomorrow") else "\nหมายเหตุราคาพรุ่งนี้: ยังไม่พบประกาศล่วงหน้าจากแหล่งข้อมูล จึงไม่เดาราคาเอง"

    return f"""⛽ ราคาน้ำมันประเทศไทย

แหล่งข้อมูล: {data.get('source')}
อัปเดต: {data.get('updated_at')}

📌 วันนี้
{chr(10).join(lines_today)}

📅 พรุ่งนี้
{chr(10).join(lines_tomorrow)}

🔁 เปลี่ยนแปลง
{chr(10).join(lines_change)}
{tomorrow_note}

หมายเหตุ: เป็นราคาขายปลีกอ้างอิงประเทศไทย อาจแตกต่างตามพื้นที่/ภาษีท้องถิ่น/สถานีบริการ"""

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
    return """V7.3.2 Oil Today/Tomorrow

พิมพ์ชื่อสินทรัพย์ หรือคำสั่งน้ำมัน:
หุ้นสหรัฐ: NVDA, AAPL, TSLA, QQQ, SPY
หุ้นไทย: SCB, AOT, PTT, HANA, DOHOME, BEAUTY, KBANK, CPALL, ADVANC
ทองคำ: ทองคำ, GOLD, XAUUSD
น้ำมันไทย: น้ำมัน, ราคาน้ำมัน, oil

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

    if lower in OIL_WORDS:
        return build_oil_report()

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
        "service": "AI Market LINE Bot V7.3.2 Oil Today/Tomorrow",
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
</head><body><h1>AI Market LINE Bot V7.3.2 Oil Today/Tomorrow</h1><p>Time TH: {now_text()}</p>
<table><thead><tr><th>Time</th><th>Symbol</th><th>Asset</th><th>Price</th><th>Score</th><th>Prob</th><th>Signal</th><th>Regime</th><th>Bias</th></tr></thead><tbody>{html_rows}</tbody></table>
</body></html>"""



@app.route("/oil-test", methods=["GET"])
def oil_test():
    return jsonify(get_thai_oil_prices())


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
