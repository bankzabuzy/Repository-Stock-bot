import os
import re
import hmac
import json
import time
import base64
import hashlib
import sqlite3
import threading
from datetime import datetime, timedelta, timezone, timezone, timezone

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
ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "")
FMP_API_KEY = os.getenv("FMP_API_KEY", "")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
PORT = int(os.getenv("PORT", "3000"))

WATCHLIST = [
    x.strip().upper()
    for x in os.getenv("WATCHLIST", "NVDA,AAPL,TSLA,QQQ,SPY,GOLD,SCB,AOT,PTT").split(",")
    if x.strip()
]

# ============================================================
# V8 PROFESSIONAL CONFIG
# ============================================================
def env_list(name, default=""):
    return [x.strip().upper() for x in os.getenv(name, default).split(",") if x.strip()]

DEFAULT_US_SYMBOLS = {
    "NVDA", "AAPL", "TSLA", "AMD", "MSFT", "META", "GOOGL", "GOOG", "AMZN",
    "NFLX", "QQQ", "SPY", "IWM", "DIA", "TQQQ", "SQQQ", "SOXL", "SOXS",
    "PLTR", "AVGO", "SMCI", "MU", "MSTR", "COIN", "ARM", "INTC", "NVO",
    "LULU", "COST", "JPM", "BAC", "XOM", "CVX", "UNH", "LLY", "WMT",
    "RKLB", "AAOI", "IREN", "ONDS", "PLUG", "EOSE", "QBTS", "HDC",
    "TJX", "CEG", "VST", "TSM", "DXYZ", "OKLO", "RGTI", "IONQ", "SOUN",
    "HOOD", "RBLX", "SHOP", "CRWD", "SNOW", "NET", "DDOG", "U", "PATH"
}

EXTRA_US_SYMBOLS = set(env_list("EXTRA_US_SYMBOLS", ""))
US_SYMBOLS = DEFAULT_US_SYMBOLS | EXTRA_US_SYMBOLS

US_WATCHLIST = env_list(
    "US_WATCHLIST",
    "NVDA,AAPL,TSLA,AMD,QQQ,SPY,META,MSFT,PLTR,RKLB,AAOI,IREN"
)

TH_WATCHLIST = env_list(
    "TH_WATCHLIST",
    "SCB,AOT,PTT,CPALL,KBANK,BBL,KTB,ADVANC,BDMS,PTTEP"
)

GOLD_WATCHLIST = env_list("GOLD_WATCHLIST", "GOLD")

ENABLE_SEPARATE_WATCHLISTS = os.getenv("ENABLE_SEPARATE_WATCHLISTS", "true").lower() == "true"

# Tier scan: A = high priority, B = medium, C = Thai/slow moving.
TIER_A_WATCHLIST = env_list("TIER_A_WATCHLIST", "NVDA,TSLA,AMD,QQQ,SPY,GOLD")
TIER_B_WATCHLIST = env_list("TIER_B_WATCHLIST", "AAPL,MSFT,META,PLTR,RKLB,AAOI,IREN")
TIER_C_WATCHLIST = env_list("TIER_C_WATCHLIST", "SCB,AOT,PTT,CPALL,KBANK,BBL,KTB,ADVANC")

V8_SKIP_INVALID_SYMBOLS = os.getenv("V8_SKIP_INVALID_SYMBOLS", "true").lower() == "true"
V8_LOG_SKIPPED_SYMBOLS = os.getenv("V8_LOG_SKIPPED_SYMBOLS", "false").lower() == "true"

ALLOWED_USERS = [x.strip() for x in os.getenv("ALLOWED_USERS", "").split(",") if x.strip()]
ALERT_USER_IDS = [x.strip() for x in os.getenv("ALERT_USER_IDS", "").split(",") if x.strip()]

ENABLE_AUTO_ALERTS = os.getenv("ENABLE_AUTO_ALERTS", "false").lower() == "true"
ENABLE_MARKET_HOURS_GUARD = os.getenv("ENABLE_MARKET_HOURS_GUARD", "true").lower() == "true"
ALLOW_GOLD_24H_ALERTS = os.getenv("ALLOW_GOLD_24H_ALERTS", "true").lower() == "true"
TH_MARKET_MORNING_START = os.getenv("TH_MARKET_MORNING_START", "10:00")
TH_MARKET_MORNING_END = os.getenv("TH_MARKET_MORNING_END", "12:30")
TH_MARKET_AFTERNOON_START = os.getenv("TH_MARKET_AFTERNOON_START", "14:30")
TH_MARKET_AFTERNOON_END = os.getenv("TH_MARKET_AFTERNOON_END", "16:45")
US_PREMARKET_START_TH = os.getenv("US_PREMARKET_START_TH", "15:00")
US_ALLOW_PREMARKET_ALERTS = os.getenv("US_ALLOW_PREMARKET_ALERTS", "true").lower() == "true"
US_SESSION_START_TH = os.getenv("US_SESSION_START_TH", "20:30")
US_SESSION_END_TH = os.getenv("US_SESSION_END_TH", "04:30")
SYMBOL_COOLDOWN_MINUTES = int(os.getenv("SYMBOL_COOLDOWN_MINUTES", "240"))

ALERT_COOLDOWN_MINUTES = int(os.getenv("ALERT_COOLDOWN_MINUTES", "240"))
STRICT_REQUIRE_4H_CONFIRM = os.getenv("STRICT_REQUIRE_4H_CONFIRM", "true").lower() == "true"
MIN_POSITION_RISK_LEVEL = os.getenv("MIN_POSITION_RISK_LEVEL", "MEDIUM").upper()

ALERT_EVERY_MINUTES = int(os.getenv("ALERT_EVERY_MINUTES", "60"))
AUTO_ALERT_MIN_SCORE = int(os.getenv("AUTO_ALERT_MIN_SCORE", "80"))
AUTO_ALERT_MAX_SCORE = int(os.getenv("AUTO_ALERT_MAX_SCORE", "25"))

# Auto Signal Pro
ENABLE_US_SESSION_ONLY = os.getenv("ENABLE_US_SESSION_ONLY", "true").lower() == "true"
US_SESSION_START_TH = os.getenv("US_SESSION_START_TH", "21:30")
US_SESSION_END_TH = os.getenv("US_SESSION_END_TH", "04:00")
SIGNAL_SCAN_SECONDS = int(os.getenv("SIGNAL_SCAN_SECONDS", str(ALERT_EVERY_MINUTES * 60)))
STRONG_CALL_SCORE = int(os.getenv("STRONG_CALL_SCORE", "85"))
STRONG_PUT_SCORE = int(os.getenv("STRONG_PUT_SCORE", "20"))

# V8 Final.4 Market Leaders Watchlist.4 Market Leaders Watchlist.3 Expanded Sector Watchlist.2 US Premarket Alert Fix
STRICT_ALERT_MODE = os.getenv("STRICT_ALERT_MODE", "true").lower() == "true"
STRICT_MIN_CONFIDENCE = int(os.getenv("STRICT_MIN_CONFIDENCE", "72"))
STRICT_MIN_TREND_STRENGTH = int(os.getenv("STRICT_MIN_TREND_STRENGTH", "5"))
STRICT_MIN_RVOL = float(os.getenv("STRICT_MIN_RVOL", "0.85"))
STRICT_REQUIRE_TF_CONFIRM = os.getenv("STRICT_REQUIRE_TF_CONFIRM", "true").lower() == "true"
STRICT_ALLOW_RANGE_GOLD = os.getenv("STRICT_ALLOW_RANGE_GOLD", "false").lower() == "true"
STRICT_CALL_SCORE = int(os.getenv("STRICT_CALL_SCORE", "88"))
STRICT_PUT_SCORE = int(os.getenv("STRICT_PUT_SCORE", "15"))

# V8 Final.4 Market Leaders Watchlist.4 Market Leaders Watchlist.3 Expanded Sector Watchlist.2 US Premarket Alert Fix
PREMARKET_REMINDER_TH = os.getenv("PREMARKET_REMINDER_TH", "21:15")
ENABLE_PREMARKET_REMINDER = os.getenv("ENABLE_PREMARKET_REMINDER", "true").lower() == "true"
TOP5_DAILY_TIME_TH = os.getenv("TOP5_DAILY_TIME_TH", "21:15")
ENABLE_TOP5_DAILY = os.getenv("ENABLE_TOP5_DAILY", "true").lower() == "true"
TOP5_UNIVERSE = [
    x.strip().upper()
    for x in os.getenv("TOP5_UNIVERSE", os.getenv("WATCHLIST", "NVDA,AAPL,TSLA,QQQ,SPY,META,AMD,PLTR,AVGO,MSFT")).split(",")
    if x.strip()
]
PREMARKET_COOLDOWN_KEY = "premarket_reminder"
TOP5_COOLDOWN_KEY = "top5_daily"

DB_PATH = os.getenv("DB_PATH", "signals.db")
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "60"))

# V8 Final.4 Market Leaders Watchlist.4 Market Leaders Watchlist.3 Expanded Sector Watchlist.2 US Premarket Alert Fix
ENABLE_MULTI_API_FALLBACK = os.getenv("ENABLE_MULTI_API_FALLBACK", "true").lower() == "true"
API_FALLBACK_VERBOSE = os.getenv("API_FALLBACK_VERBOSE", "false").lower() == "true"

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
    "MONO", "THCOM", "ADVANC", "TLI", "BLA", "TIPH", "BAM", "CHAYO",
    "ASK", "KGI", "MST", "CGH", "TQM", "MENA", "SNNP", "PLUS"
}

GOLD_WORDS = {"GOLD", "ทอง", "ทองคำ", "ทองคํา", "XAUUSD", "XAU/USD"}
US_INDEX_SYMBOLS = {"SPX": "SPY", "NASDAQ": "QQQ", "NDX": "QQQ", "DOW": "DIA", "RUSSELL": "IWM"}

CACHE = {}

# ============================================================
# DELISTED / MERGED SYMBOL FIXES
# ============================================================
# INTUCH was removed/merged from the active Thai market universe.
# The bot should not keep scanning INTUCH.BK because Yahoo Finance often returns no data.
# User commands for INTUCH are redirected to ADVANC as the closest active telecom proxy.
DELISTED_SYMBOL_ALIASES = {
    "INTUCH": "ADVANC",
    "INTUCH.BK": "ADVANC.BK",
    "INTUCH.SET": "ADVANC.SET",
}

def resolve_delisted_symbol(symbol):
    key = str(symbol or "").strip().upper()
    return DELISTED_SYMBOL_ALIASES.get(key, key)


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
    cur.execute("""
        CREATE TABLE IF NOT EXISTS alert_cooldown (
            alert_key TEXT PRIMARY KEY,
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
    return (datetime.now(timezone.utc) + timedelta(hours=7)).strftime("%d/%m/%Y %H:%M")


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
# DYNAMIC THAI STOCK DETECTION V7.5
# ============================================================
def looks_like_stock_symbol(key):
    return bool(re.fullmatch(r"[A-Z0-9]{1,12}", key))


def yahoo_bk_exists(symbol):
    """Detect Thai stocks dynamically using Yahoo Finance SYMBOL.BK.
    This supports BEAUTY, HANA, DOHOME and future Thai tickers without manual THAI_SYMBOLS edits.
    """
    if not looks_like_stock_symbol(symbol):
        return False

    known_us = {
        "NVDA", "AAPL", "TSLA", "MSFT", "META", "GOOGL", "GOOG", "AMZN",
        "NFLX", "AMD", "INTC", "QQQ", "SPY", "IWM", "DIA", "TQQQ", "SQQQ",
        "SOXL", "SOXS", "PLTR", "COIN", "MSTR", "AVGO", "SMCI", "MU"
    }
    if symbol in known_us:
        return False

    cache_key = f"YF_BK_EXISTS:{symbol}"
    cached = cache_get(cache_key)
    if cached is not None:
        return bool(cached)

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
    raw = (user_text or "").strip()
    key = raw.upper().replace(" ", "")

    # Redirect delisted/merged symbols before asset classification.
    # Example: INTUCH or INTUCH.BK -> ADVANC / ADVANC.BK
    if key in DELISTED_SYMBOL_ALIASES:
        key = DELISTED_SYMBOL_ALIASES[key].replace(".SET", ".BK")
        raw = key

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

    # Explicit Thai suffix always wins.
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

    # V8: US watchlist/symbols must be checked before THAI_SYMBOLS/yahoo_bk_exists.
    # This prevents RKLB.BK / AAOI.BK / CEG.BK / VST.BK false Thai conversion.
    if key in US_SYMBOLS or key in US_WATCHLIST or key in TIER_A_WATCHLIST or key in TIER_B_WATCHLIST:
        return {
            "display": key,
            "symbol": key,
            "yf_symbol": key,
            "currency": "USD",
            "asset_type": "US_STOCK",
            "news_symbol": key,
        }

    # Explicit Thai watchlist and known SET symbols.
    if key in TH_WATCHLIST or key in TIER_C_WATCHLIST or key in THAI_SYMBOLS:
        return {
            "display": f"{key}.BK",
            "symbol": key,
            "yf_symbol": f"{key}.BK",
            "currency": "THB",
            "asset_type": "THAI_STOCK",
            "news_symbol": key,
        }

    # V8 default: unknown plain ticker is treated as US stock, not Thai.
    # If a Thai symbol is not recognized, add it to TH_WATCHLIST or type SYMBOL.BK.
    return {
        "display": key,
        "symbol": key,
        "yf_symbol": key,
        "currency": "USD",
        "asset_type": "US_STOCK",
        "news_symbol": key,
    }



# ============================================================
# V7.8 MULTI-FREE API FALLBACK ENGINE
# ============================================================
def log_api_fallback(message):
    if API_FALLBACK_VERBOSE:
        print("[V7.8 API FALLBACK]", message)


def api_quote_template(symbol, price, previous_close=None, currency="USD", source=""):
    change = None
    percent_change = None
    try:
        if previous_close and price:
            change = float(price) - float(previous_close)
            percent_change = change / float(previous_close) * 100
    except Exception:
        pass

    return {
        "symbol": symbol,
        "close": price,
        "price": price,
        "previous_close": previous_close,
        "change": change,
        "percent_change": percent_change,
        "currency": currency,
        "source": source,
    }


def finnhub_get_quote(asset):
    if not FINNHUB_API_KEY:
        raise RuntimeError("ยังไม่ได้ตั้งค่า FINNHUB_API_KEY")
    symbol = asset["symbol"]
    r = requests.get(
        "https://finnhub.io/api/v1/quote",
        params={"symbol": symbol, "token": FINNHUB_API_KEY},
        headers=REQUEST_HEADERS,
        timeout=20,
    )
    q = r.json()
    price = safe_float(q.get("c"))
    prev = safe_float(q.get("pc"))
    if price is None or price <= 0:
        raise RuntimeError(f"Finnhub ไม่พบ quote สำหรับ {symbol}")
    return api_quote_template(symbol, price, prev, asset.get("currency", "USD"), "Finnhub")


def fmp_get_quote(asset):
    if not FMP_API_KEY:
        raise RuntimeError("ยังไม่ได้ตั้งค่า FMP_API_KEY")
    symbol = asset["symbol"]
    r = requests.get(
        f"https://financialmodelingprep.com/api/v3/quote/{symbol}",
        params={"apikey": FMP_API_KEY},
        headers=REQUEST_HEADERS,
        timeout=20,
    )
    data = r.json()
    if not isinstance(data, list) or not data:
        raise RuntimeError(f"FMP ไม่พบ quote สำหรับ {symbol}")
    q = data[0]
    price = safe_float(q.get("price"))
    prev = safe_float(q.get("previousClose"))
    if price is None:
        raise RuntimeError(f"FMP quote ไม่มีราคา {symbol}")
    return api_quote_template(symbol, price, prev, asset.get("currency", "USD"), "FMP")


def fmp_get_series(asset, outputsize=160):
    if not FMP_API_KEY:
        raise RuntimeError("ยังไม่ได้ตั้งค่า FMP_API_KEY")
    symbol = asset["symbol"]
    r = requests.get(
        f"https://financialmodelingprep.com/api/v3/historical-price-full/{symbol}",
        params={"timeseries": outputsize, "apikey": FMP_API_KEY},
        headers=REQUEST_HEADERS,
        timeout=25,
    )
    data = r.json()
    hist = data.get("historical", []) if isinstance(data, dict) else []
    if not hist:
        raise RuntimeError(f"FMP ไม่พบ historical สำหรับ {symbol}")
    hist = list(reversed(hist[:outputsize]))
    closes, highs, lows, opens, volumes = [], [], [], [], []
    for v in hist:
        try:
            closes.append(float(v.get("close")))
            highs.append(float(v.get("high")))
            lows.append(float(v.get("low")))
            opens.append(float(v.get("open")))
            volumes.append(float(v.get("volume") or 0))
        except Exception:
            pass
    if not closes:
        raise RuntimeError(f"FMP historical ไม่มีราคา {symbol}")
    return closes, highs, lows, opens, volumes


def alphavantage_get_quote(asset):
    if not ALPHAVANTAGE_API_KEY:
        raise RuntimeError("ยังไม่ได้ตั้งค่า ALPHAVANTAGE_API_KEY")
    symbol = asset["symbol"]
    r = requests.get(
        "https://www.alphavantage.co/query",
        params={"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": ALPHAVANTAGE_API_KEY},
        headers=REQUEST_HEADERS,
        timeout=20,
    )
    data = r.json()
    q = data.get("Global Quote", {}) if isinstance(data, dict) else {}
    price = safe_float(q.get("05. price"))
    prev = safe_float(q.get("08. previous close"))
    if price is None:
        raise RuntimeError(f"Alpha Vantage ไม่พบ quote สำหรับ {symbol}")
    return api_quote_template(symbol, price, prev, asset.get("currency", "USD"), "Alpha Vantage")


def alphavantage_get_series(asset):
    if not ALPHAVANTAGE_API_KEY:
        raise RuntimeError("ยังไม่ได้ตั้งค่า ALPHAVANTAGE_API_KEY")
    symbol = asset["symbol"]
    r = requests.get(
        "https://www.alphavantage.co/query",
        params={"function": "TIME_SERIES_DAILY_ADJUSTED", "symbol": symbol, "outputsize": "compact", "apikey": ALPHAVANTAGE_API_KEY},
        headers=REQUEST_HEADERS,
        timeout=25,
    )
    data = r.json()
    ts = data.get("Time Series (Daily)", {}) if isinstance(data, dict) else {}
    if not ts:
        raise RuntimeError(f"Alpha Vantage ไม่พบ series สำหรับ {symbol}")
    items = sorted(ts.items())[-160:]
    closes, highs, lows, opens, volumes = [], [], [], [], []
    for _, v in items:
        try:
            opens.append(float(v.get("1. open")))
            highs.append(float(v.get("2. high")))
            lows.append(float(v.get("3. low")))
            closes.append(float(v.get("4. close")))
            volumes.append(float(v.get("6. volume") or v.get("5. volume") or 0))
        except Exception:
            pass
    if not closes:
        raise RuntimeError(f"Alpha Vantage series ไม่มีราคา {symbol}")
    return closes, highs, lows, opens, volumes


def multi_api_get_us_market_data(asset):
    errors = []

    try:
        quote = td_get_quote(asset)
        closes, highs, lows, opens, volumes = td_get_series(asset)
        if closes:
            quote["source"] = "TwelveData"
            return quote, closes, highs, lows, opens, volumes
    except Exception as e:
        errors.append(f"TwelveData: {e}")
        log_api_fallback(errors[-1])

    try:
        quote = finnhub_get_quote(asset)
        try:
            _, closes, highs, lows, opens, volumes = yf_get_quote_and_series(asset)
        except Exception:
            closes, highs, lows, opens, volumes = fmp_get_series(asset)
        return quote, closes, highs, lows, opens, volumes
    except Exception as e:
        errors.append(f"Finnhub: {e}")
        log_api_fallback(errors[-1])

    try:
        quote = fmp_get_quote(asset)
        closes, highs, lows, opens, volumes = fmp_get_series(asset)
        return quote, closes, highs, lows, opens, volumes
    except Exception as e:
        errors.append(f"FMP: {e}")
        log_api_fallback(errors[-1])

    try:
        quote = alphavantage_get_quote(asset)
        closes, highs, lows, opens, volumes = alphavantage_get_series(asset)
        return quote, closes, highs, lows, opens, volumes
    except Exception as e:
        errors.append(f"AlphaVantage: {e}")
        log_api_fallback(errors[-1])

    try:
        quote, closes, highs, lows, opens, volumes = yf_get_quote_and_series(asset)
        quote["source"] = "Yahoo Finance"
        return quote, closes, highs, lows, opens, volumes
    except Exception as e:
        errors.append(f"Yahoo: {e}")

    raise RuntimeError("ไม่พบข้อมูลจากทุกแหล่ง: " + " | ".join(errors[-5:]))


def fmp_get_valuation(asset):
    if not FMP_API_KEY:
        return {}
    try:
        symbol = asset["symbol"]
        r = requests.get(
            f"https://financialmodelingprep.com/api/v3/profile/{symbol}",
            params={"apikey": FMP_API_KEY},
            headers=REQUEST_HEADERS,
            timeout=20,
        )
        data = r.json()
        if isinstance(data, list) and data:
            p = data[0]
            return {
                "source": "FMP",
                "price": safe_float(p.get("price")),
                "beta": safe_float(p.get("beta")),
                "mktCap": safe_float(p.get("mktCap")),
                "lastDiv": safe_float(p.get("lastDiv")),
                "companyName": p.get("companyName"),
                "sector": p.get("sector"),
                "industry": p.get("industry"),
            }
    except Exception as e:
        log_api_fallback(f"FMP valuation: {e}")
    return {}

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
        if ENABLE_MULTI_API_FALLBACK:
            result = multi_api_get_us_market_data(asset)
        else:
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
    quality_flags = []
    reasons = []

    bullish_structure = bool(price and ema6 and ema12 and price > ema6 > ema12)
    bearish_structure = bool(price and ema6 and ema12 and price < ema6 < ema12)

    if price and ema6 and ema12:
        if bullish_structure:
            trend_score += 22
            reasons.append("ราคาอยู่เหนือ EMA6 และ EMA12")
        elif bearish_structure:
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
            quality_flags.append("OVERBOUGHT_CHASE_RISK")
        elif rsi <= 30:
            momentum_score += 2
            reasons.append("RSI ต่ำมาก ระวังรีบาวด์ ไม่ควรไล่ SELL/PUT")
            quality_flags.append("OVERSOLD_REBOUND_RISK")
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
            reasons.append("Volume สูงและราคาปิดบวก หนุนแรงซื้อ")
        elif rvol >= 1.5 and percent_change and percent_change < 0:
            if bullish_structure:
                volume_score -= 4
                reasons.append("Volume สูงแต่ราคาอ่อนตัว ระวังแรงขายระยะสั้น ไม่ใช่แรงซื้อยืนยัน")
                quality_flags.append("BULLISH_WITH_SELL_VOLUME_CONFLICT")
            else:
                volume_score -= 10
                reasons.append("Volume สูงและราคาปิดลบ หนุนแรงขาย")

    if atr and price:
        atr_pct = atr / price * 100
        if 0.8 <= atr_pct <= 3.5:
            volatility_score += 5
        elif atr_pct > 5:
            volatility_score -= 8
            reasons.append("ความผันผวนสูง คุมขนาดไม้")
            quality_flags.append("HIGH_VOLATILITY_RISK")

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
        "quality_flags": quality_flags,
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
        val = float(value)
        if val <= 1:
            val *= 100
        if val < 0 or val > 15:
            return "N/A"
        return f"{val:.2f}%"
    except Exception:
        return "N/A"


def normalized_dividend_yield_pct(price, fundamentals):
    """Return a sane dividend yield percentage.
    Priority: Yahoo dividendYield if plausible; fallback to dividendRate/current price.
    Unrealistic yields are ignored to prevent outputs like QQQ Dividend Yield 42%.
    """
    try:
        raw = safe_float(fundamentals.get("dividend_yield"))
        if raw is not None:
            pct = raw * 100 if raw <= 1 else raw
            if 0 <= pct <= 15:
                return pct
    except Exception:
        pass
    try:
        rate = safe_float(fundamentals.get("dividend_rate"))
        if rate is not None and price and price > 0:
            pct = rate / price * 100
            if 0 <= pct <= 15:
                return pct
    except Exception:
        pass
    return None


def dividend_yield_pct_text(pct):
    return "N/A" if pct is None else f"{float(pct):.2f}%"


def valuation_engine(asset, analysis, fundamentals):
    """Simple rule-based valuation using free data.
    This is not intrinsic valuation; it is relative/technical valuation.
    V14.1 fixes dividend-yield unit errors and suppresses unrealistic Yahoo ETF yield glitches.
    """
    if asset["asset_type"] == "GOLD":
        return "", "N/A"

    price = analysis.get("price")
    ema50 = analysis.get("ema50")
    rsi = analysis.get("rsi")
    pe = fundamentals.get("trailing_pe")
    fwd_pe = fundamentals.get("forward_pe")
    div_yield_pct = normalized_dividend_yield_pct(price, fundamentals)
    low52 = fundamentals.get("fifty_two_week_low")
    high52 = fundamentals.get("fifty_two_week_high")

    score = 0
    reasons = []

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

    if rsi is not None:
        if rsi >= 72:
            score += 1
            reasons.append("RSI สูง มีความเสี่ยงไล่ราคา")
        elif rsi <= 35:
            score -= 1
            reasons.append("RSI ต่ำ มีโอกาสอยู่ในโซนถูกเชิงเทคนิค")

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

    if div_yield_pct is not None:
        if div_yield_pct >= 5:
            score -= 1
            reasons.append("Dividend Yield สูง น่าสนใจสำหรับสายปันผล")
        elif div_yield_pct < 1:
            score += 1
            reasons.append("Dividend Yield ต่ำ ไม่ได้ช่วยรองรับ valuation มากนัก")
    else:
        reasons.append("Dividend Yield ใช้ไม่ได้/ผิดหน่วย จึงตัดออกจากการประเมิน")

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
Dividend Yield: {dividend_yield_pct_text(div_yield_pct)}
Dividend Rate: {fmt_num(fundamentals.get('dividend_rate'))}

XD / Ex-dividend: {fundamentals.get('ex_dividend_date', 'N/A')}
วันประกาศงบ: {fundamentals.get('earnings_date', 'N/A')}
ปันผลล่าสุด: {fmt_num(fundamentals.get('last_dividend'))}
วันที่ปันผลล่าสุด: {fundamentals.get('last_dividend_date', 'N/A')}

52W Low: {fmt_num(fundamentals.get('fifty_two_week_low'))}
52W High: {fmt_num(fundamentals.get('fifty_two_week_high'))}

เหตุผล valuation:
{chr(10).join("- " + r for r in reasons[:7]) if reasons else "- ข้อมูลพื้นฐานไม่พอสำหรับประเมินถูก/แพง"}"""

    return text, status

# ============================================================
# OPTIONS HYBRID MAX FREE
# ============================================================
def option_strike_step(price):
    if price is None:
        return 1
    if price >= 500:
        return 5
    if price >= 100:
        return 2.5
    if price >= 30:
        return 1
    return 0.5


def ensure_spread_width(buy_strike, sell_strike, price, side="CALL"):
    step = option_strike_step(price)
    try:
        buy = float(buy_strike)
        sell = float(sell_strike)
    except Exception:
        return buy_strike, sell_strike
    if str(side).upper() == "CALL":
        if sell <= buy:
            sell = buy + step
    else:
        if sell >= buy:
            sell = buy - step
    return round(buy, 2), round(sell, 2)


def options_hybrid_engine(asset, analysis):
    if asset["asset_type"] != "US_STOCK":
        return ""

    price = analysis["price"]
    atr = analysis["atr"] or (price * 0.015 if price else None)
    if not price or not atr:
        return ""

    score = analysis["score"]
    prob = analysis["probability"]
    regime = str(analysis.get("regime", "")).upper()

    call_strike = round_strike(price + atr * 0.50)
    call_sell = round_strike(price + atr * 2.00)
    call_strike, call_sell = ensure_spread_width(call_strike, call_sell, price, "CALL")

    put_strike = round_strike(price - atr * 0.50)
    put_sell = round_strike(price - atr * 2.00)
    put_strike, put_sell = ensure_spread_width(put_strike, put_sell, price, "PUT")

    entry_low = price - atr * 0.35
    entry_high = price + atr * 0.10
    tp1 = price + atr * 1.00
    tp2 = price + atr * 2.00
    tp3 = price + atr * 3.00
    sl = price - atr * 1.00

    put_entry_low = price - atr * 0.10
    put_entry_high = price + atr * 0.35
    put_tp1 = price - atr * 1.00
    put_tp2 = price - atr * 2.00
    put_tp3 = price - atr * 3.00
    put_sl = price + atr * 1.00

    range_note = "\nหมายเหตุ Regime: ตลาดเป็น RANGE/LOW VOL จึงควรใช้ขนาดไม้ลดลงและเน้นย่อซื้อ/เด้งขาย ไม่ไล่ราคา" if ("RANGE" in regime or "LOW VOL" in regime) else ""

    if score >= 70:
        setup = f"""🧠 Options Hybrid Max Free
Setup: CALL / Bullish
Strike แนะนำ: {fmt_num(call_strike, 2)}C
Probability ประมาณ: {prob}%

Entry Zone: {fmt_num(entry_low)} - {fmt_num(entry_high)}
TP1: {fmt_num(tp1)}
TP2: {fmt_num(tp2)}
TP3: {fmt_num(tp3)}
SL: {fmt_num(sl)}

Spread Scanner:
Bull Call Spread
Buy {fmt_num(call_strike, 2)}C
Sell {fmt_num(call_sell, 2)}C

ข้อควรระวัง: ใช้ ATR + AI Score เป็น proxy หากต้องการสัญญาจริงให้ดู /v10/options หรือ /v12-1/liquidity เพิ่ม{range_note}"""
    elif score <= 35:
        setup = f"""🧠 Options Hybrid Max Free
Setup: PUT / Bearish
Strike แนะนำ: {fmt_num(put_strike, 2)}P
Probability ประมาณ: {prob}%

Entry Zone: {fmt_num(put_entry_low)} - {fmt_num(put_entry_high)}
TP1: {fmt_num(put_tp1)}
TP2: {fmt_num(put_tp2)}
TP3: {fmt_num(put_tp3)}
SL: {fmt_num(put_sl)}

Spread Scanner:
Bear Put Spread
Buy {fmt_num(put_strike, 2)}P
Sell {fmt_num(put_sell, 2)}P

ข้อควรระวัง: ใช้ ATR + AI Score เป็น proxy หากต้องการสัญญาจริงให้ดู /v10/options หรือ /v12-1/liquidity เพิ่ม{range_note}"""
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
        today = datetime.now(timezone.utc).date()
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
# THAILAND OIL PRICE V7.3.3 PT STATION DEFAULT
# ============================================================
OIL_WORDS = {
    "น้ำมัน", "ราคาน้ำมัน", "ราคาน้ํามัน",
    "oil", "oli", "oill", "fuel", "pt", "ptstation", "พีที", "ptt", "บางจาก", "น้ำมันไทย"
}

def normalize_oil_name(name):
    raw = str(name or "").strip()
    n = raw.lower().replace(" ", "").replace("-", "").replace("_", "")

    mapping = [
        ("แก๊สโซฮอล์95", "แก๊สโซฮอล์ 95"), ("gasohol95", "แก๊สโซฮอล์ 95"), ("gsh95", "แก๊สโซฮอล์ 95"),
        ("แก๊สโซฮอล์91", "แก๊สโซฮอล์ 91"), ("gasohol91", "แก๊สโซฮอล์ 91"), ("gsh91", "แก๊สโซฮอล์ 91"),
        ("e20", "แก๊สโซฮอล์ E20"), ("e85", "แก๊สโซฮอล์ E85"),
        ("เบนซิน95", "เบนซิน 95"), ("benzine95", "เบนซิน 95"), ("gasoline95", "เบนซิน 95"),
        ("ดีเซลb20", "ดีเซล B20"), ("dieselb20", "ดีเซล B20"),
        ("ดีเซลb7", "ดีเซล B7"), ("dieselb7", "ดีเซล B7"),
        ("ดีเซลพรีเมียม", "ดีเซลพรีเมียม"), ("premiumdiesel", "ดีเซลพรีเมียม"),
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
    if not prices:
        return {}, {}
    if isinstance(prices, dict) and ("today" in prices or "tomorrow" in prices):
        return prices.get("today", {}) or {}, prices.get("tomorrow", {}) or {}
    return prices, {}


def clean_oil_prices(d):
    return {normalize_oil_name(k): float(v) for k, v in (d or {}).items() if v is not None and 10 <= float(v) <= 90}


def extract_pt_station_prices_from_text(text):
    """Parse PT Station prices from PTG or PT price pages."""
    combo = re.sub(r"\s+", " ", text)

    patterns = [
        ("ดีเซล", [r"ดีเซล(?!\s*B20)(?!\s*B7)(?!\s*พรีเมียม)", r"Diesel(?!\s*B20)(?!\s*B7)(?!\s*Premium)"]),
        ("ดีเซล B20", [r"ดีเซล\s*B20", r"Diesel\s*B20"]),
        ("เบนซิน 95", [r"เบนซิน\s*95", r"Benzine\s*95", r"Gasoline\s*95"]),
        ("แก๊สโซฮอล์ 95", [r"แก๊สโซฮอล์\s*95", r"Gasohol\s*95"]),
        ("แก๊สโซฮอล์ 91", [r"แก๊สโซฮอล์\s*91", r"Gasohol\s*91"]),
        ("แก๊สโซฮอล์ E20", [r"แก๊สโซฮอล์\s*E20", r"E20"]),
        ("แก๊สโซฮอล์ E85", [r"แก๊สโซฮอล์\s*E85", r"E85"]),
    ]

    today, tomorrow = {}, {}
    for display, pats in patterns:
        for pat in pats:
            m = re.search(pat + r".{0,120}?(\d{2}\.\d{1,2})", combo, re.I)
            if m:
                today[display] = safe_float(m.group(1))
                break

    # Try "วันนี้ > พรุ่งนี้" rows e.g. ดีเซล 42.20 > 41.20 or 44.90 ▼ 44.30
    for display, pats in patterns:
        for pat in pats:
            m = re.search(pat + r".{0,100}?(\d{2}\.\d{1,2}).{0,30}?[>▼→]\s*(\d{2}\.\d{1,2})", combo, re.I)
            if m:
                today[display] = safe_float(m.group(1))
                tomorrow[display] = safe_float(m.group(2))
                break

    # PTG homepage often exposes only numeric values in this order:
    # Diesel, Diesel B20, Gasohol 95, Gasohol 91, Benzine 95, E20
    if len(today) < 4:
        nums = re.findall(r"\b(\d{2}\.\d{1,2})\b", combo)
        values = []
        for n in nums:
            v = safe_float(n)
            if v and 10 <= v <= 90 and v not in values:
                values.append(v)

        # Protect against older widgets that include "today then tomorrow" or "old then new".
        # If the set contains the current PT Station group, map by known PT order.
        pt_order = ["ดีเซล", "ดีเซล B20", "แก๊สโซฮอล์ 95", "แก๊สโซฮอล์ 91", "เบนซิน 95", "แก๊สโซฮอล์ E20"]
        if len(values) >= 6:
            # Heuristic: choose a 6-number window that looks like PT current prices.
            best = None
            for i in range(0, len(values) - 5):
                window = values[i:i+6]
                # Diesel should be 30-50, B20 often 30-40, gasohol 95/91 ~35-55, benzine high.
                if 30 <= window[0] <= 50 and 30 <= window[1] <= 45 and 35 <= window[2] <= 55 and 35 <= window[3] <= 55 and 45 <= window[4] <= 65 and 30 <= window[5] <= 50:
                    best = window
                    break
            if not best:
                best = values[:6]
            for idx, name in enumerate(pt_order):
                today.setdefault(name, best[idx])

    return clean_oil_prices(today), clean_oil_prices(tomorrow)


def get_pt_station_prices():
    """PT Station first, because user's reference image is PT Station."""
    cached = cache_get("THAI_OIL_PT_STATION")
    if cached:
        return cached

    urls = [
        "https://www.ptgenergy.co.th/",
        "https://www.ptgenergy.co.th/th/oil-price",
        "https://www.ptgenergy.co.th/th/pt-station/oil-price",
        "https://gasprice.kapook.com/gasprice.php",
        "https://xn--42cah7d0cxcvbbb9x.com/ราคาน้ำมัน-พีที-pt/",
    ]

    for url in urls:
        try:
            r = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
            if r.status_code != 200:
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            text = soup.get_text(" ", strip=True)
            combo = r.text + " " + text

            # If this is a multi-brand page, prefer section around PT.
            lower_text = combo.lower()
            if "ราคานํ้ามันพีที" in combo or "ราคาน้ำมันพีที" in combo or "pt)" in lower_text:
                idx = max(combo.find("ราคานํ้ามันพีที"), combo.find("ราคาน้ำมันพีที"), lower_text.find("pt)"))
                if idx >= 0:
                    combo = combo[idx:idx+4000]

            today, tomorrow = extract_pt_station_prices_from_text(combo)

            # Validate at least key products.
            if today and ("ดีเซล" in today or "แก๊สโซฮอล์ 95" in today):
                result = {
                    "source": "PT Station / PTG",
                    "updated_at": now_text(),
                    "raw_url": url,
                    "prices": {"today": today, "tomorrow": tomorrow},
                    "has_tomorrow": bool(tomorrow),
                    "is_estimate": False,
                }
                cache_set("THAI_OIL_PT_STATION", result)
                return result

        except Exception as e:
            print("PT Station oil fetch error:", url, e)

    return None


def get_ptt_oil_prices():
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

        text = BeautifulSoup(r.text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&"), "html.parser").get_text(" ", strip=True)
        today, tomorrow = extract_pt_station_prices_from_text(text)

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
        "https://www.bangchak.co.th/th/oilprice",
        "https://www.bangchak.co.th/th/oilprice/historical",
        "https://oil-price.bangchak.co.th/BcpOilPrice2/th",
        "https://oil-price.bangchak.co.th/ApiOilPrice2/th",
    ]

    for url in urls:
        try:
            r = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
            if r.status_code != 200:
                continue
            text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
            combo = r.text + " " + text
            today, tomorrow = extract_pt_station_prices_from_text(combo)

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
    # Default: PT Station first, because user wants prices matching PT Station reference.
    result = get_pt_station_prices()
    if result and result.get("prices", {}).get("today"):
        return result

    result = get_ptt_oil_prices()
    if result and result.get("prices", {}).get("today"):
        return result

    result = get_bangchak_oil_prices()
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
        "ดีเซล",
        "ดีเซล B20",
        "ดีเซล B7",
        "เบนซิน 95",
        "แก๊สโซฮอล์ 95",
        "แก๊สโซฮอล์ 91",
        "แก๊สโซฮอล์ E20",
        "แก๊สโซฮอล์ E85",
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
1) PT Station / PTG
2) PTT OR OilPrice Web Service
3) Bangchak

หมายเหตุ: ระบบไม่คำนวณราคาน้ำมันเอง เพราะราคาขายปลีกไทยต้องอ้างอิงประกาศผู้ค้าน้ำมัน"""

    lines_today, lines_tomorrow, lines_change = [], [], []

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

หมายเหตุ: ราคาขายปลีกอ้างอิงจากแหล่งที่ระบุ อาจแตกต่างตามพื้นที่/ภาษีท้องถิ่น/สถานีบริการ"""

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
    return """V8 Final.4 Market Leaders Watchlist.4 Market Leaders Watchlist.3 Expanded Sector Watchlist.2 US Premarket Alert Fix

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
        "service": "AI Market LINE Bot V8 Final.4 Market Leaders Watchlist.4 Market Leaders Watchlist.4 Market Leaders Watchlist.3 Expanded Sector Watchlist.3 Expanded Sector Watchlist.2 US Premarket Alert Fix.2 US Premarket Alert Fix.1 Market Hours Guard",
        "time_th": now_text(),
        "v8_professional": True,
        "v8_watchlist": v8_watchlist_status_dict(),
        "multi_api_fallback": ENABLE_MULTI_API_FALLBACK,
        "api_keys": {
            "twelvedata": bool(TWELVEDATA_API_KEY),
            "finnhub": bool(FINNHUB_API_KEY),
            "fmp": bool(FMP_API_KEY),
            "alphavantage": bool(ALPHAVANTAGE_API_KEY),
        },
        "premarket_reminder_th": PREMARKET_REMINDER_TH,
        "enable_premarket_reminder": ENABLE_PREMARKET_REMINDER,
        "top5_daily_time_th": TOP5_DAILY_TIME_TH,
        "enable_top5_daily": ENABLE_TOP5_DAILY,
        "top5_universe": TOP5_UNIVERSE,
        "strict_alert_mode": STRICT_ALERT_MODE,
        "strict_min_confidence": STRICT_MIN_CONFIDENCE,
        "strict_min_trend_strength": STRICT_MIN_TREND_STRENGTH,
        "strict_min_rvol": STRICT_MIN_RVOL,
        "strict_require_tf_confirm": STRICT_REQUIRE_TF_CONFIRM,
        "strict_call_score": STRICT_CALL_SCORE,
        "strict_put_score": STRICT_PUT_SCORE,
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
</head><body><h1>AI Market LINE Bot V8 Final.4 Market Leaders Watchlist.4 Market Leaders Watchlist.4 Market Leaders Watchlist.3 Expanded Sector Watchlist.3 Expanded Sector Watchlist.2 US Premarket Alert Fix.2 US Premarket Alert Fix.1 Market Hours Guard</h1><p>Time TH: {now_text()}</p>
<table><thead><tr><th>Time</th><th>Symbol</th><th>Asset</th><th>Price</th><th>Score</th><th>Prob</th><th>Signal</th><th>Regime</th><th>Bias</th></tr></thead><tbody>{html_rows}</tbody></table>
</body></html>"""



@app.route("/oil-test", methods=["GET"])
def oil_test():
    return jsonify(get_thai_oil_prices())



@app.route("/signal-status", methods=["GET"])
def signal_status():
    return jsonify({
        "enable_auto_alerts": ENABLE_AUTO_ALERTS,
        "watchlist": WATCHLIST,
        "alert_user_ids_count": len(ALERT_USER_IDS),
        "signal_scan_seconds": SIGNAL_SCAN_SECONDS,
        "enable_us_session_only": ENABLE_US_SESSION_ONLY,
        "us_session_start_th": US_SESSION_START_TH,
        "us_session_end_th": US_SESSION_END_TH,
        "strong_call_score": STRONG_CALL_SCORE,
        "strong_put_score": STRONG_PUT_SCORE,
        "auto_alert_min_score": AUTO_ALERT_MIN_SCORE,
        "auto_alert_max_score": AUTO_ALERT_MAX_SCORE,
        "time_th": now_text(),
        "v8_professional": True,
        "v8_watchlist": v8_watchlist_status_dict(),
        "multi_api_fallback": ENABLE_MULTI_API_FALLBACK,
        "api_keys": {
            "twelvedata": bool(TWELVEDATA_API_KEY),
            "finnhub": bool(FINNHUB_API_KEY),
            "fmp": bool(FMP_API_KEY),
            "alphavantage": bool(ALPHAVANTAGE_API_KEY),
        },
        "premarket_reminder_th": PREMARKET_REMINDER_TH,
        "enable_premarket_reminder": ENABLE_PREMARKET_REMINDER,
        "top5_daily_time_th": TOP5_DAILY_TIME_TH,
        "enable_top5_daily": ENABLE_TOP5_DAILY,
        "top5_universe": TOP5_UNIVERSE,
        "strict_alert_mode": STRICT_ALERT_MODE,
        "strict_min_confidence": STRICT_MIN_CONFIDENCE,
        "strict_min_trend_strength": STRICT_MIN_TREND_STRENGTH,
        "strict_min_rvol": STRICT_MIN_RVOL,
        "strict_require_tf_confirm": STRICT_REQUIRE_TF_CONFIRM,
        "strict_call_score": STRICT_CALL_SCORE,
        "strict_put_score": STRICT_PUT_SCORE,
    })



@app.route("/top5", methods=["GET"])
def top5_route():
    if not require_admin():
        return Response("Unauthorized", status=401)
    return Response(build_top5_daily_message(), mimetype="text/plain; charset=utf-8")


@app.route("/premarket", methods=["GET"])
def premarket_route():
    if not require_admin():
        return Response("Unauthorized", status=401)
    return Response(build_premarket_reminder(), mimetype="text/plain; charset=utf-8")



@app.route("/strict-check/<symbol>", methods=["GET"])
def strict_check(symbol):
    if not require_admin():
        return jsonify({"error": "unauthorized"}), 401
    asset = normalize_asset(symbol)
    quote, closes, highs, lows, opens, volumes = get_market_data(asset)
    analysis = analyze_signal(asset, quote, closes, highs, lows, opens, volumes)
    raw_sig = signal_type_from_analysis(asset, analysis)
    ok, reason = strict_alert_gate(symbol.upper(), asset, analysis, raw_sig) if raw_sig != "NONE" else (False, "No raw signal")
    return jsonify({
        "symbol": symbol.upper(),
        "asset_type": asset.get("asset_type"),
        "raw_signal": raw_sig,
        "allowed_to_alert": ok,
        "reason": reason,
        "score": analysis.get("score"),
        "confidence": adjusted_confidence(analysis, raw_sig) if raw_sig != "NONE" and "adjusted_confidence" in globals() else calculate_signal_confidence(analysis),
        "trend_strength": trend_strength_score(analysis) if "trend_strength_score" in globals() else None,
        "rvol": analysis.get("rvol"),
        "regime": analysis.get("regime"),
        "time_th": now_text(),
        "v8_professional": True,
        "v8_watchlist": v8_watchlist_status_dict(),
        "multi_api_fallback": ENABLE_MULTI_API_FALLBACK,
        "api_keys": {
            "twelvedata": bool(TWELVEDATA_API_KEY),
            "finnhub": bool(FINNHUB_API_KEY),
            "fmp": bool(FMP_API_KEY),
            "alphavantage": bool(ALPHAVANTAGE_API_KEY),
        },
    })



# ============================================================
# V7.8 LINE COMMAND ROUTER
# ============================================================
def build_signal_status_text():
    return f"""📡 Signal Status

App: V8 Final.4 Market Leaders Watchlist.4 Market Leaders Watchlist.3 Expanded Sector Watchlist.2 US Premarket Alert Fix
เวลาไทย: {now_text()}

Auto Alerts: {ENABLE_AUTO_ALERTS}
Alert Users: {len(ALERT_USER_IDS)}
Watchlist: {", ".join(WATCHLIST[:30])}

Multi API Fallback: {ENABLE_MULTI_API_FALLBACK}
Strict Alert: {STRICT_ALERT_MODE if 'STRICT_ALERT_MODE' in globals() else 'N/A'}

API Keys:
TwelveData: {'OK' if TWELVEDATA_API_KEY else 'Missing'}
Finnhub: {'OK' if FINNHUB_API_KEY else 'Missing'}
FMP: {'OK' if FMP_API_KEY else 'Missing'}
Alpha Vantage: {'OK' if ALPHAVANTAGE_API_KEY else 'Missing'}"""


def handle_line_command(user_text):
    text = (user_text or "").strip()
    low = text.lower()

    if low in {"/health", "health"}:
        return "OK"

    if low in {"/oil", "oil", "oli", "น้ำมัน", "ราคาน้ำมัน"}:
        return build_oil_report()

    if low in {"/gold", "gold", "ทอง", "ทองคำ", "xauusd"}:
        try:
            return build_asset_report("GOLD")
        except Exception:
            return handle_message("", "GOLD") if "handle_message" in globals() else "ไม่สามารถดึงข้อมูลทองคำได้"

    if low in {"/signal-status", "signal-status", "status", "/status"}:
        return build_signal_status_text()

    if low in {"/watchlist-status", "watchlist-status", "/watchlist"}:
        return json.dumps(v8_watchlist_status_dict(), ensure_ascii=False, indent=2)

    if low in {"/top5", "top5"}:
        return build_top5_daily_message()

    if low in {"/premarket", "premarket"}:
        return build_premarket_reminder()

    if low.startswith("/strict-check"):
        parts = text.split()
        sym = parts[1] if len(parts) > 1 else "NVDA"
        try:
            asset = normalize_asset(sym)
            quote, closes, highs, lows, opens, volumes = get_market_data(asset)
            analysis = analyze_signal(asset, quote, closes, highs, lows, opens, volumes)
            raw_sig = signal_type_from_analysis(asset, analysis)
            if raw_sig != "NONE" and "strict_alert_gate" in globals():
                ok, reason = strict_alert_gate(sym.upper(), asset, analysis, raw_sig)
            else:
                ok, reason = False, "No raw signal"
            return f"""🧪 Strict Check {sym.upper()}

Raw Signal: {raw_sig}
Allowed: {ok}
Reason: {reason}
Score: {analysis.get('score')}
Regime: {analysis.get('regime')}
เวลาไทย: {now_text()}"""
        except Exception as e:
            return f"Strict Check Error: {e}"

    if low.startswith("/"):
        return "ไม่รู้จักคำสั่งนี้ครับ\nลองใช้ /gold, /oil, /signal-status, /top5, /premarket หรือพิมพ์ชื่อหุ้น เช่น NVDA, AAPL, SCB"

    return None


@app.route("/watchlist-status", methods=["GET"])
def watchlist_status():
    return jsonify(v8_watchlist_status_dict())


@app.route("/v8-status", methods=["GET"])
def v8_status():
    return jsonify({
        "app": "V8 Final.4 Market Leaders Watchlist.4 Market Leaders Watchlist.3 Expanded Sector Watchlist.2 US Premarket Alert Fix",
        "time_th": now_text(),
        "v8_professional": True,
        "v8_watchlist": v8_watchlist_status_dict(),
        "multi_api_fallback": ENABLE_MULTI_API_FALLBACK if "ENABLE_MULTI_API_FALLBACK" in globals() else None,
        "strict_alert_mode": STRICT_ALERT_MODE if "STRICT_ALERT_MODE" in globals() else None,
        "watchlist": v8_watchlist_status_dict(),
        "api_keys": {
            "twelvedata": bool(TWELVEDATA_API_KEY),
            "finnhub": bool(FINNHUB_API_KEY),
            "fmp": bool(FMP_API_KEY),
            "alphavantage": bool(ALPHAVANTAGE_API_KEY),
        }
    })



# ============================================================
# V8.1 TEST ALERT ENDPOINTS
# ============================================================
def require_test_token():
    token = os.getenv("TEST_ALERT_TOKEN", "")
    if not token:
        return True
    return request.args.get("token", "") == token


def send_test_alert(kind="buy", symbol="NVDA"):
    if not ALERT_USER_IDS:
        return {"ok": False, "error": "ALERT_USER_IDS is empty"}

    kind = (kind or "buy").lower()
    symbol = (symbol or "NVDA").upper()

    if kind == "sell":
        msg = f"""🔴 TEST SELL ALERT

Symbol: {symbol}
เวลาไทย: {now_text()}

ระบบทดสอบการส่ง LINE สำเร็จ
นี่ไม่ใช่สัญญาณจริง"""
    elif kind == "top5":
        msg = build_top5_daily_message()
    else:
        msg = f"""🟢 TEST BUY ALERT

Symbol: {symbol}
เวลาไทย: {now_text()}

ระบบทดสอบการส่ง LINE สำเร็จ
นี่ไม่ใช่สัญญาณจริง"""

    sent = 0
    for uid in ALERT_USER_IDS:
        line_push(uid, msg)
        sent += 1
    return {"ok": True, "sent": sent, "kind": kind, "symbol": symbol, "time_th": now_text()}


@app.route("/test-buy", methods=["GET"])
def test_buy():
    if not require_test_token():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return jsonify(send_test_alert("buy", request.args.get("symbol", "NVDA")))


@app.route("/test-sell", methods=["GET"])
def test_sell():
    if not require_test_token():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return jsonify(send_test_alert("sell", request.args.get("symbol", "GOLD")))


@app.route("/test-top5", methods=["GET"])
def test_top5():
    if not require_test_token():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return jsonify(send_test_alert("top5", "TOP5"))


@app.route("/production-status", methods=["GET"])
def production_status():
    return jsonify({
        "app": "V8 Final.4 Market Leaders Watchlist.4 Market Leaders Watchlist.3 Expanded Sector Watchlist.2 US Premarket Alert Fix",
        "time_th": now_text(),
        "health": "OK",
        "line_ready": bool(LINE_CHANNEL_ACCESS_TOKEN and LINE_CHANNEL_SECRET),
        "alert_users": len(ALERT_USER_IDS),
        "auto_alerts": ENABLE_AUTO_ALERTS,
        "top5_daily": globals().get("ENABLE_TOP5_DAILY", None),
        "top5_time_th": globals().get("TOP5_DAILY_TIME_TH", None),
        "multi_api_fallback": globals().get("ENABLE_MULTI_API_FALLBACK", None),
        "api_keys": {
            "twelvedata": bool(TWELVEDATA_API_KEY),
            "finnhub": bool(FINNHUB_API_KEY),
            "fmp": bool(FMP_API_KEY),
            "alphavantage": bool(ALPHAVANTAGE_API_KEY),
        },
        "datetime_utcnow_fixed": True,
    })




@app.route("/sector-watchlist-status", methods=["GET"])
def sector_watchlist_status():
    return jsonify({
        "enabled": ENABLE_EXPANDED_SECTOR_WATCHLIST,
        "expanded_us_count": len(EXPANDED_US_WATCHLIST),
        "expanded_th_count": len(EXPANDED_TH_WATCHLIST),
        "us_groups": SECTOR_WATCHLISTS,
        "thai_groups": THAI_SECTOR_WATCHLISTS,
        "total_scan_count": len(build_v8_scan_watchlist()) if "build_v8_scan_watchlist" in globals() else None,
    })



@app.route("/market-leader-watchlist-status", methods=["GET"])
def market_leader_watchlist_status():
    return jsonify({
        "enabled": ENABLE_MARKET_LEADER_WATCHLIST,
        "market_leader_us_count": len(MARKET_LEADER_US_WATCHLIST),
        "market_leader_th_count": len(MARKET_LEADER_TH_WATCHLIST),
        "us_groups": MARKET_LEADER_WATCHLISTS,
        "thai_groups": THAI_MARKET_LEADER_WATCHLISTS,
        "total_scan_count": len(build_v8_scan_watchlist()) if "build_v8_scan_watchlist" in globals() else None,
    })


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
        user_text = message.get("text", "")
        command_response = handle_line_command(user_text) if "handle_line_command" in globals() else None
        if command_response is not None:
            line_reply(reply_token, command_response)
            continue
        line_reply(reply_token, handle_message(user_id, user_text))
    return "OK", 200





# ============================================================
# V8 FINAL.3 EXPANDED SECTOR WATCHLIST
# ============================================================
SECTOR_WATCHLISTS = {
    "AI_CHIP": [
        "NVDA", "AMD", "AVGO", "TSM", "ASML", "ARM", "MU", "MRVL", "QCOM",
        "INTC", "SMCI", "ANET", "LRCX", "KLAC", "AMAT", "ON", "MCHP", "MPWR"
    ],
    "AI_SOFTWARE_CLOUD": [
        "MSFT", "GOOGL", "GOOG", "META", "PLTR", "SNOW", "CRM", "DDOG",
        "CRWD", "NET", "MDB", "ORCL", "CFLT", "NOW", "ADBE"
    ],
    "NUCLEAR_URANIUM": [
        "OKLO", "SMR", "NNE", "LEU", "CCJ", "UEC", "URA", "EU", "DNN", "NXE"
    ],
    "ENERGY_OIL_GAS": [
        "XOM", "CVX", "OXY", "COP", "SLB", "HAL", "EOG", "DVN", "FANG",
        "VLO", "MPC", "PSX", "LNG", "EQT", "ET"
    ],
    "UTILITIES_POWER": [
        "NEE", "SO", "DUK", "AEP", "XLU", "CEG", "VST", "PEG", "EXC", "EIX"
    ],
    "FINANCIALS": [
        "JPM", "BAC", "GS", "MS", "WFC", "C", "BLK", "SCHW", "AXP", "V", "MA"
    ],
    "QUANTUM": [
        "IONQ", "RGTI", "QBTS", "QUBT"
    ],
    "ROBOTICS_AUTOMATION": [
        "TSLA", "ABB", "SYM", "SERV", "TER", "ISRG", "PATH", "ROK", "IRBT"
    ],
    "DEFENSE": [
        "RTX", "LMT", "NOC", "GD", "PLTR", "KTOS", "AVAV"
    ],
    "MOMENTUM_SMALL_CAP": [
        "RKLB", "AAOI", "IREN", "ONDS", "PLUG", "EOSE", "SOUN", "HOOD",
        "RBLX", "SHOP", "SOFI", "UPST", "AFRM", "HIMS", "CELH"
    ],
    "ETF_SCANNER": [
        "SPY", "QQQ", "IWM", "DIA", "TQQQ", "SQQQ", "SOXL", "SOXS",
        "SMH", "XLK", "XLE", "XLF", "XLU", "URA", "GLD", "GDX"
    ],
    "GOLD_SILVER": [
        "GOLD", "GLD", "GDX", "NEM", "AEM", "PAAS", "SILJ", "AG", "WPM"
    ],
}

THAI_SECTOR_WATCHLISTS = {
    "BANK": ["KBANK", "BBL", "SCB", "KTB", "TTB", "TISCO", "KKP"],
    "ENERGY": ["PTT", "PTTEP", "TOP", "BCP", "SPRC", "IRPC", "OR"],
    "POWER": ["GPSC", "GULF", "BGRIM", "EGCO", "RATCH", "EA"],
    "COMMUNICATION": ["ADVANC", "TRUE", "DIF"],
    "RETAIL": ["CPALL", "CRC", "HMPRO", "COM7", "CPAXT", "DOHOME", "GLOBAL"],
    "TRANSPORT": ["AOT", "BTS", "BEM", "BA"],
    "ELECTRONICS": ["DELTA", "HANA", "KCE", "CCET"],
    "PROPERTY": ["AP", "SIRI", "LH", "SPALI", "WHA", "AMATA"],
    "HEALTHCARE": ["BDMS", "BH", "CHG", "BCH"],
    "TOURISM": ["MINT", "CENTEL", "ERW"],
}

def _flatten_sector_watchlists():
    out = []
    for group in SECTOR_WATCHLISTS.values():
        out.extend(group)
    return dedupe_keep_order(out) if "dedupe_keep_order" in globals() else list(dict.fromkeys(out))

def _flatten_thai_sector_watchlists():
    out = []
    for group in THAI_SECTOR_WATCHLISTS.values():
        out.extend(group)
    return dedupe_keep_order(out) if "dedupe_keep_order" in globals() else list(dict.fromkeys(out))

EXPANDED_US_WATCHLIST = env_list("EXPANDED_US_WATCHLIST", ",".join(_flatten_sector_watchlists())) if "env_list" in globals() else _flatten_sector_watchlists()
EXPANDED_TH_WATCHLIST = env_list("EXPANDED_TH_WATCHLIST", ",".join(_flatten_thai_sector_watchlists())) if "env_list" in globals() else _flatten_thai_sector_watchlists()

ENABLE_EXPANDED_SECTOR_WATCHLIST = os.getenv("ENABLE_EXPANDED_SECTOR_WATCHLIST", "true").lower() == "true"

# เพิ่ม US_SYMBOLS ให้รู้จักหุ้น US กลุ่มใหม่ ไม่ถูกแปลงเป็น .BK
try:
    US_SYMBOLS.update(set(EXPANDED_US_WATCHLIST))
except Exception:
    pass

# เพิ่ม THAI_SYMBOLS ให้รู้จักหุ้นไทยกลุ่มใหม่
try:
    THAI_SYMBOLS.update(set(EXPANDED_TH_WATCHLIST))
except Exception:
    pass


# ============================================================
# V8 FINAL.4 MARKET LEADERS WATCHLIST
# ============================================================
MARKET_LEADER_WATCHLISTS = {
    # Core market leaders / mega-cap liquidity
    "MEGA_CAP_LEADERS": [
        "NVDA", "MSFT", "AAPL", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "AVGO", "BRK.B"
    ],

    # AI infrastructure / semiconductors / hardware
    "AI_INFRA_SEMICONDUCTOR": [
        "NVDA", "AMD", "AVGO", "TSM", "ASML", "ARM", "MU", "MRVL", "QCOM",
        "INTC", "SMCI", "ANET", "LRCX", "KLAC", "AMAT", "ON", "MCHP",
        "MPWR", "AMKR", "WDC", "AXTI", "AAOI", "AEHR", "CRDO", "NVTS", "MTRN"
    ],

    # AI software, cloud, data, cybersecurity-adjacent AI platforms
    "AI_SOFTWARE_CLOUD_DATA": [
        "MSFT", "GOOGL", "GOOG", "META", "PLTR", "SNOW", "CRM", "DDOG", "NET",
        "MDB", "ORCL", "CFLT", "NOW", "ADBE", "CRWV", "NBIS", "INFQ", "ZETA", "IBM"
    ],

    # Cybersecurity leaders
    "CYBERSECURITY": [
        "CRWD", "PANW", "FTNT", "ZS", "S", "NET", "OKTA", "CYBR", "TENB", "QLYS"
    ],

    # Nuclear, uranium, grid power, electricity
    "NUCLEAR_URANIUM_POWER": [
        "OKLO", "SMR", "NNE", "LEU", "CCJ", "UEC", "URA", "EU", "DNN", "NXE",
        "UUUU", "CEG", "VST", "NEE", "SO", "DUK", "AEP", "XLU", "PEG", "EXC"
    ],

    # Energy, oil, gas, LNG, refiners, pipelines
    "ENERGY_OIL_GAS_LNG": [
        "XOM", "CVX", "OXY", "COP", "SLB", "HAL", "EOG", "DVN", "FANG",
        "VLO", "MPC", "PSX", "LNG", "EQT", "ET", "KMI", "WMB", "OKE", "BKR"
    ],

    # Financials, brokers, payments, credit
    "FINANCIALS_PAYMENTS": [
        "JPM", "BAC", "GS", "MS", "WFC", "C", "BLK", "SCHW", "AXP", "V", "MA",
        "COF", "DFS", "BX", "KKR", "ICE", "CME", "SPGI", "MCO", "HOOD", "SOFI", "PYPL"
    ],

    # Healthcare, pharma, biotech, medtech
    "HEALTHCARE_PHARMA_BIOTECH": [
        "LLY", "NVO", "UNH", "JNJ", "MRK", "ABBV", "PFE", "AMGN", "GILD",
        "REGN", "VRTX", "TMO", "DHR", "ISRG", "SYK", "MDT", "BSX", "ABT", "HIMS"
    ],

    # Consumer leaders / retail / restaurants / apparel
    "CONSUMER_RETAIL_BRANDS": [
        "COST", "WMT", "TGT", "HD", "LOW", "MCD", "SBUX", "CMG", "NKE", "LULU",
        "TJX", "ELF", "CELH", "DECK", "ULTA"
    ],

    # Industrials, aerospace, machinery, electrification
    "INDUSTRIAL_AEROSPACE_AUTOMATION": [
        "GE", "GEV", "CAT", "DE", "ETN", "HON", "EMR", "ROK", "PH", "ITW",
        "BA", "LMT", "RTX", "NOC", "GD", "LHX", "KTOS", "AVAV", "AXON"
    ],

    # Space economy / satellite / defense tech
    "SPACE_SATELLITE_DEFENSE_TECH": [
        "RKLB", "ASTS", "PL", "BKSY", "LUNR", "RDW", "SPIR", "MDAI", "KTOS", "AVAV"
    ],

    # Crypto, bitcoin miners, blockchain infrastructure
    "CRYPTO_BITCOIN_MINERS": [
        "MSTR", "COIN", "HOOD", "MARA", "RIOT", "CLSK", "IREN", "CIFR", "HUT", "BTDR", "WULF"
    ],

    # Quantum / advanced computing
    "QUANTUM_ADVANCED_COMPUTING": [
        "IONQ", "RGTI", "QBTS", "QUBT", "IBM", "GOOGL", "MSFT"
    ],

    # Robotics / automation / autonomous / drones
    "ROBOTICS_AUTONOMY_DRONES": [
        "TSLA", "SYM", "SERV", "TER", "ISRG", "PATH", "ROK", "ABB", "IRBT", "UMAC", "AVAV", "KTOS"
    ],

    # Small/mid-cap momentum names from user's watchlist
    "USER_MOMENTUM_NAMES": [
        "HOOD", "MTRN", "LAES", "CRDO", "MRVL", "NOW", "PLTR", "NVTS", "CRWV",
        "CIFR", "NBIS", "AMKR", "INTC", "AEHR", "LEU", "UUUU", "UMAC", "INFQ",
        "PLUG", "QBTS", "WDC", "AXTI", "DXYZ", "AAOI", "RKLB", "TJX", "ONDS",
        "IREN", "EOSE", "BKSY", "PL", "ASTS", "IBM", "CEG", "VST", "TSM"
    ],

    # ETF / sector confirmation instruments
    "ETF_SECTOR_CONFIRM": [
        "SPY", "QQQ", "IWM", "DIA", "TQQQ", "SQQQ", "SOXL", "SOXS", "SMH",
        "XLK", "XLE", "XLF", "XLU", "XLV", "XLI", "XLY", "XLP", "URA", "GLD", "GDX", "IBIT"
    ],
}

THAI_MARKET_LEADER_WATCHLISTS = {
    "THAI_BANK_FINANCE": ["KBANK", "BBL", "SCB", "KTB", "TTB", "TISCO", "KKP", "KTC", "MTC", "SAWAD", "TIDLOR"],
    "THAI_ENERGY_POWER": ["PTT", "PTTEP", "TOP", "BCP", "SPRC", "IRPC", "OR", "GPSC", "GULF", "BGRIM", "EGCO", "RATCH", "EA"],
    "THAI_COMMERCE_CONSUMER": ["CPALL", "CRC", "HMPRO", "COM7", "CPAXT", "DOHOME", "GLOBAL", "CBG", "OSP"],
    "THAI_TELECOM_DIGITAL": ["ADVANC", "TRUE", "DIF"],
    "THAI_TRANSPORT_TOURISM": ["AOT", "BTS", "BEM", "BA", "MINT", "CENTEL", "ERW"],
    "THAI_ELECTRONICS_EXPORT": ["DELTA", "HANA", "KCE", "CCET", "SVI"],
    "THAI_HEALTHCARE": ["BDMS", "BH", "CHG", "BCH", "PR9"],
    "THAI_PROPERTY_INDUSTRIAL": ["AP", "SIRI", "LH", "SPALI", "WHA", "AMATA", "CPN"],
}

def _flatten_market_leaders():
    out = []
    for group in MARKET_LEADER_WATCHLISTS.values():
        out.extend(group)
    if "dedupe_keep_order" in globals():
        return dedupe_keep_order(out)
    return list(dict.fromkeys(out))

def _flatten_thai_market_leaders():
    out = []
    for group in THAI_MARKET_LEADER_WATCHLISTS.values():
        out.extend(group)
    if "dedupe_keep_order" in globals():
        return dedupe_keep_order(out)
    return list(dict.fromkeys(out))

ENABLE_MARKET_LEADER_WATCHLIST = os.getenv("ENABLE_MARKET_LEADER_WATCHLIST", "true").lower() == "true"
MARKET_LEADER_US_WATCHLIST = env_list("MARKET_LEADER_US_WATCHLIST", ",".join(_flatten_market_leaders())) if "env_list" in globals() else _flatten_market_leaders()
MARKET_LEADER_TH_WATCHLIST = env_list("MARKET_LEADER_TH_WATCHLIST", ",".join(_flatten_thai_market_leaders())) if "env_list" in globals() else _flatten_thai_market_leaders()

try:
    US_SYMBOLS.update(set(MARKET_LEADER_US_WATCHLIST))
except Exception:
    pass

try:
    THAI_SYMBOLS.update(set(MARKET_LEADER_TH_WATCHLIST))
except Exception:
    pass

# ============================================================
# V8 PROFESSIONAL WATCHLIST ENGINE
# ============================================================
def dedupe_keep_order(items):
    seen = set()
    out = []
    for x in items:
        k = str(x).strip().upper()
        if k and k not in seen:
            out.append(k)
            seen.add(k)
    return out


def classify_watchlist_symbol(symbol):
    key = resolve_delisted_symbol(symbol)
    if key.endswith(".BK"):
        key = key.replace(".BK", "")
    if key.endswith(".SET"):
        key = key.replace(".SET", "")
    if not key:
        return None
    if key in GOLD_WORDS or key in GOLD_WATCHLIST:
        return "GOLD"
    if key.endswith(".BK") or key.endswith(".SET"):
        return "THAI_STOCK"
    if key in US_SYMBOLS or key in US_WATCHLIST or key in TIER_A_WATCHLIST or key in TIER_B_WATCHLIST:
        return "US_STOCK"
    if key in TH_WATCHLIST or key in TIER_C_WATCHLIST or key in THAI_SYMBOLS:
        return "THAI_STOCK"
    # Default plain unknown ticker = US stock to avoid fake .BK errors.
    return "US_STOCK"


def build_v8_scan_watchlist():
    if ENABLE_SEPARATE_WATCHLISTS:
        base = []
        # Priority order
        base.extend(TIER_A_WATCHLIST)
        base.extend(TIER_B_WATCHLIST)
        base.extend(TIER_C_WATCHLIST)
        base.extend(GOLD_WATCHLIST)
        base.extend(US_WATCHLIST)
        base.extend(TH_WATCHLIST)
        if ENABLE_EXPANDED_SECTOR_WATCHLIST:
            base.extend(EXPANDED_US_WATCHLIST)
            base.extend(EXPANDED_TH_WATCHLIST)
        if ENABLE_MARKET_LEADER_WATCHLIST:
            base.extend(MARKET_LEADER_US_WATCHLIST)
            base.extend(MARKET_LEADER_TH_WATCHLIST)
        base = [resolve_delisted_symbol(x).replace(".BK", "").replace(".SET", "") for x in base]
        return dedupe_keep_order(base)

    # Backward compatible mode from old WATCHLIST, but with safer classification.
    valid = []
    for s in WATCHLIST:
        asset_class = classify_watchlist_symbol(s)
        if asset_class:
            valid.append(s)
    return dedupe_keep_order(valid)


def v8_skip_symbol(symbol):
    # Skip empty/slash commands accidentally placed in watchlist.
    key = str(symbol).strip().upper()
    if not key:
        return True
    if key.startswith("/"):
        return True
    if key in {"OIL", "น้ำมัน"}:
        return True
    return False


def v8_watchlist_status_dict():
    return {
        "enable_separate_watchlists": ENABLE_SEPARATE_WATCHLISTS,
        "scan_watchlist": build_v8_scan_watchlist(),
        "us_watchlist": US_WATCHLIST,
        "th_watchlist": TH_WATCHLIST,
        "gold_watchlist": GOLD_WATCHLIST,
        "tier_a": TIER_A_WATCHLIST,
        "tier_b": TIER_B_WATCHLIST,
        "tier_c": TIER_C_WATCHLIST,
        "known_us_count": len(US_SYMBOLS),
        "market_leader_enabled": ENABLE_MARKET_LEADER_WATCHLIST,
        "market_leader_us_count": len(MARKET_LEADER_US_WATCHLIST),
        "market_leader_th_count": len(MARKET_LEADER_TH_WATCHLIST),
        "market_leader_groups": list(MARKET_LEADER_WATCHLISTS.keys()),
        "thai_market_leader_groups": list(THAI_MARKET_LEADER_WATCHLISTS.keys()),
        "expanded_sector_enabled": ENABLE_EXPANDED_SECTOR_WATCHLIST,
        "expanded_us_count": len(EXPANDED_US_WATCHLIST),
        "expanded_th_count": len(EXPANDED_TH_WATCHLIST),
        "sector_groups": list(SECTOR_WATCHLISTS.keys()),
        "thai_sector_groups": list(THAI_SECTOR_WATCHLISTS.keys()),
    }

# ============================================================
# AUTO SIGNAL PRO
# ============================================================
def parse_hhmm(value):
    try:
        hh, mm = value.split(":")
        return int(hh), int(mm)
    except Exception:
        return 0, 0


def now_th_datetime():
    return datetime.now(timezone.utc) + timedelta(hours=7)


def is_in_time_window(now_dt, start_hhmm, end_hhmm):
    sh, sm = parse_hhmm(start_hhmm)
    eh, em = parse_hhmm(end_hhmm)

    now_minutes = now_dt.hour * 60 + now_dt.minute
    start_minutes = sh * 60 + sm
    end_minutes = eh * 60 + em

    if start_minutes <= end_minutes:
        return start_minutes <= now_minutes <= end_minutes

    # overnight session e.g. 21:30 to 04:00
    return now_minutes >= start_minutes or now_minutes <= end_minutes


def should_scan_symbol_by_session(asset):
    if not globals().get("ENABLE_US_SESSION_ONLY", False):
        return True
    if asset.get("asset_type") == "US_STOCK":
        return is_us_market_open_now_th() if "is_us_market_open_now_th" in globals() else True
    return True



def signal_type_from_analysis(asset, analysis):
    score = analysis.get("score", 50)
    if asset.get("asset_type") == "US_STOCK":
        if score >= STRONG_CALL_SCORE:
            return "STRONG_CALL"
        if score <= STRONG_PUT_SCORE:
            return "STRONG_PUT"
    else:
        if score >= AUTO_ALERT_MIN_SCORE:
            return "BUY"
        if score <= AUTO_ALERT_MAX_SCORE:
            return "SELL"
    return "NONE"


def build_auto_signal_message(symbol, asset, analysis):
    msg = professional_alert_message_v77(symbol, asset, analysis)
    if msg:
        return append_final_blocks_to_message(msg, asset, analysis, signal_type_from_analysis(asset, analysis))

    # fallback to V7.6 if needed
    try:
        return professional_alert_message(symbol, asset, analysis)
    except Exception:
        price = analysis.get("price")
        price_label = "$" if asset.get("currency") == "USD" else "฿"
        return f"""⚠️ SIGNAL ALERT

Symbol: {symbol}
เวลาไทย: {now_text()}

ราคา: {price_label}{fmt_num(price)}
AI Score: {analysis.get('score')}/100

หมายเหตุ: ข้อมูลไม่พอสำหรับแผนเต็ม"""



def date_key_th():
    return now_th_datetime().strftime("%Y-%m-%d")


def alert_key_for_today(name):
    return f"{name}:{date_key_th()}"


def already_sent_daily(name):
    return get_last_alert_ts(alert_key_for_today(name)) > 0


def mark_sent_daily(name):
    set_last_alert_ts(alert_key_for_today(name), time.time())


def is_hhmm_now(target_hhmm, window_minutes=5):
    now_dt = now_th_datetime()
    th, tm = parse_hhmm(target_hhmm)
    target = now_dt.replace(hour=th, minute=tm, second=0, microsecond=0)
    diff = abs((now_dt - target).total_seconds()) / 60
    return diff <= window_minutes


def get_earnings_text(symbols):
    lines = []
    for s in symbols[:20]:
        try:
            asset = normalize_asset(s)
            if asset.get("asset_type") != "US_STOCK":
                continue
            ticker = yf.Ticker(asset["symbol"])
            ed = ticker.get_earnings_dates(limit=2)
            if ed is not None and not ed.empty:
                d = str(ed.index[0].date())
                lines.append(f"- {asset['symbol']}: {d}")
        except Exception:
            continue
    return "\n".join(lines) if lines else "- N/A"


def get_premarket_change(asset):
    """Best effort premarket/gap using Yahoo fast_info/info. Missing fields return N/A."""
    if asset.get("asset_type") != "US_STOCK":
        return None
    try:
        ticker = yf.Ticker(asset["symbol"])
        info = {}
        try:
            info = ticker.get_info() or {}
        except Exception:
            info = ticker.info or {}

        pre = safe_float(info.get("preMarketPrice"))
        prev = safe_float(info.get("previousClose"))
        regular = safe_float(info.get("regularMarketPrice"))

        ref = pre or regular
        if ref and prev:
            pct = (ref - prev) / prev * 100
            return pct
    except Exception:
        return None
    return None


def build_premarket_reminder():
    rows = []
    movers = []
    for s in TOP5_UNIVERSE[:30]:
        try:
            asset = normalize_asset(s)
            if asset.get("asset_type") != "US_STOCK":
                continue
            pct = get_premarket_change(asset)
            if pct is not None:
                movers.append((s, pct))
        except Exception:
            pass

    movers_sorted = sorted(movers, key=lambda x: abs(x[1]), reverse=True)[:5]
    if movers_sorted:
        rows = [f"- {s}: {pct:+.2f}%" for s, pct in movers_sorted]
    else:
        rows = ["- ยังดึง Premarket movers ไม่ได้ หรือไม่มีข้อมูลจาก Yahoo"]

    earnings = get_earnings_text(TOP5_UNIVERSE)

    return f"""⏰ US Open Reminder 21:15

ตลาด US ใกล้เปิดแล้ว
เวลาไทย: {now_text()}

🔥 Premarket Movers
{chr(10).join(rows)}

📅 Earnings Watch
{earnings}

คำแนะนำระบบ:
- รอแท่งแรก 5-15 นาที
- หลีกเลี่ยงไล่ราคาในช่วงเปิดแรง
- ใช้สัญญาณ STRONG CALL/PUT จากระบบเป็นตัวกรอง

หมายเหตุ: ข้อมูล premarket ฟรีอาจไม่ครบทุกตัว"""


def rank_top5_picks():
    picks = []
    for s in TOP5_UNIVERSE:
        try:
            asset = normalize_asset(s)
            quote, closes, highs, lows, opens, volumes = get_market_data(asset)
            analysis = analyze_signal(asset, quote, closes, highs, lows, opens, volumes)
            picks.append((s, asset, analysis))
            time.sleep(0.5)
        except Exception as e:
            print("top5 scan error:", s, e)

    picks = sorted(picks, key=lambda x: x[2].get("score", 0), reverse=True)
    return picks[:5]


def build_top5_daily_message():
    return compact_top5_message()



def maybe_send_premarket_and_top5():
    if not (ENABLE_AUTO_ALERTS and ALERT_USER_IDS):
        return

    if ENABLE_PREMARKET_REMINDER and is_hhmm_now(PREMARKET_REMINDER_TH, window_minutes=5):
        if not already_sent_daily(PREMARKET_COOLDOWN_KEY):
            msg = build_premarket_reminder()
            for user_id in ALERT_USER_IDS:
                line_push(user_id, msg)
            mark_sent_daily(PREMARKET_COOLDOWN_KEY)

    if ENABLE_TOP5_DAILY and is_hhmm_now(TOP5_DAILY_TIME_TH, window_minutes=5):
        if not already_sent_daily(TOP5_COOLDOWN_KEY):
            msg = build_top5_daily_message()
            for user_id in ALERT_USER_IDS:
                line_push(user_id, msg)
            mark_sent_daily(TOP5_COOLDOWN_KEY)


# ============================================================
# V7.6 PROFESSIONAL ALERT UPGRADE
# ============================================================
def calculate_signal_confidence(analysis):
    try:
        score = int(analysis.get("score", 50))
        prob = int(analysis.get("probability", 50))
        regime = str(analysis.get("regime", "")).upper()
        alignment = str(analysis.get("alignment", "")).upper()
        rvol = safe_float(analysis.get("rvol"), 1.0) or 1.0

        confidence = int((abs(score - 50) * 1.1) + (prob * 0.45))
        if "TREND" in regime:
            confidence += 8
        if "HIGH" in alignment or "BULL" in alignment or "BEAR" in alignment:
            confidence += 5
        if rvol >= 1.5:
            confidence += 5
        elif rvol < 0.8:
            confidence -= 7
        return max(35, min(95, confidence))
    except Exception:
        return 50


def timeframe_side_from_numbers(ema6, ema12, ema50, rsi):
    try:
        if ema6 and ema12 and ema50:
            if ema6 > ema12 > ema50 and (rsi is None or rsi >= 50):
                return "BUY"
            if ema6 < ema12 < ema50 and (rsi is None or rsi <= 50):
                return "SELL"
        if rsi is not None:
            if rsi >= 60:
                return "BUY"
            if rsi <= 40:
                return "SELL"
    except Exception:
        pass
    return "NEUTRAL"


def build_timeframe_confirm(asset, analysis):
    try:
        main_side = timeframe_side_from_numbers(
            analysis.get("ema6"),
            analysis.get("ema12"),
            analysis.get("ema50"),
            analysis.get("rsi"),
        )

        states = {}
        for label, state in analysis.get("mtf_states", []) or []:
            s = str(state).upper()
            if "BULL" in s or "BUY" in s:
                states[str(label).upper()] = "BUY"
            elif "BEAR" in s or "SELL" in s:
                states[str(label).upper()] = "SELL"
            else:
                states[str(label).upper()] = "NEUTRAL"

        tf5 = states.get("5M") or main_side
        tf15 = states.get("15M") or main_side
        tf1h = states.get("1H") or main_side

        sides = [tf5, tf15, tf1h]
        buy_count = sides.count("BUY")
        sell_count = sides.count("SELL")

        if buy_count == 3:
            overall = "STRONG BUY"
        elif sell_count == 3:
            overall = "STRONG SELL"
        elif buy_count >= 2:
            overall = "BUY"
        elif sell_count >= 2:
            overall = "SELL"
        else:
            overall = "MIXED / WAIT"

        return f"""🧭 Timeframe Confirm
5m : {tf5}
15m : {tf15}
1H : {tf1h}

Overall : {overall}"""
    except Exception:
        return """🧭 Timeframe Confirm
5m : N/A
15m : N/A
1H : N/A

Overall : N/A"""


def get_gold_thai_block(price_usd=None):
    try:
        usdthb = get_usd_thb_rate()
    except Exception:
        usdthb = None

    thb_oz = None
    try:
        if price_usd and usdthb:
            thb_oz = float(price_usd) * float(usdthb)
    except Exception:
        thb_oz = None

    gt = None
    try:
        gt = get_thai_gold_price_or_estimate(price_usd, usdthb)
    except Exception as e:
        print("get_gold_thai_block error:", e)

    lines = []
    if price_usd:
        if thb_oz:
            lines.append(f"ราคา: ${fmt_num(price_usd)}")
            lines.append(f"≈ {fmt_num(thb_oz, 0)} บาท/ออนซ์")
        else:
            lines.append(f"ราคา: ${fmt_num(price_usd)}")

    if gt:
        lines.append("")
        lines.append("🏆 ราคาทองไทย")
        if gt.get("bar_sell") is not None:
            lines.append(f"ทองแท่งขายออก: {fmt_num(gt.get('bar_sell'), 0)} บาท")
        if gt.get("bar_buy") is not None:
            lines.append(f"ทองแท่งรับซื้อ: {fmt_num(gt.get('bar_buy'), 0)} บาท")
        if gt.get("ornament_sell") is not None:
            lines.append(f"ทองรูปพรรณขายออก: {fmt_num(gt.get('ornament_sell'), 0)} บาท")
        if gt.get("source"):
            lines.append(f"แหล่งข้อมูล: {gt.get('source')}")

    return "\n".join(lines)


def next_friday_text():
    try:
        today = now_th_datetime().date()
        days_ahead = (4 - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        d = today + timedelta(days=days_ahead)
        return d.strftime("%d/%m/%Y")
    except Exception:
        return "Friday"


def suggested_options_contract(asset, analysis):
    if asset["asset_type"] != "US_STOCK":
        return ""

    price = analysis.get("price")
    atr = analysis.get("atr") or (price * 0.015 if price else None)
    score = analysis.get("score", 50)
    if not price or not atr:
        return ""

    if score >= 70:
        buy = round_strike(price + atr * 0.50)
        sell = round_strike(price + atr * 2.00)
        buy, sell = ensure_spread_width(buy, sell, price, "CALL")
        tp1, tp2, tp3, sl = price + atr, price + atr * 2, price + atr * 3, price - atr
        return f"""🧾 Options Contract Proxy
Side: CALL
Buy Strike: {fmt_num(buy, 2)}C
Spread: Buy {fmt_num(buy, 2)}C / Sell {fmt_num(sell, 2)}C
TP Underlying: {fmt_num(tp1)} / {fmt_num(tp2)} / {fmt_num(tp3)}
Invalid/SL Underlying: {fmt_num(sl)}
หมายเหตุ: เป็น Options Hybrid จากราคา/ATR/AI Score ไม่ใช่ราคา option จริง"""

    if score <= 35:
        buy = round_strike(price - atr * 0.50)
        sell = round_strike(price - atr * 2.00)
        buy, sell = ensure_spread_width(buy, sell, price, "PUT")
        tp1, tp2, tp3, sl = price - atr, price - atr * 2, price - atr * 3, price + atr
        return f"""🧾 Options Contract Proxy
Side: PUT
Buy Strike: {fmt_num(buy, 2)}P
Spread: Buy {fmt_num(buy, 2)}P / Sell {fmt_num(sell, 2)}P
TP Underlying: {fmt_num(tp1)} / {fmt_num(tp2)} / {fmt_num(tp3)}
Invalid/SL Underlying: {fmt_num(sl)}
หมายเหตุ: เป็น Options Hybrid จากราคา/ATR/AI Score ไม่ใช่ราคา option จริง"""

    return "🧾 Options Contract Proxy\nSide: WAIT\nยังไม่มี edge มากพอสำหรับเลือก CALL/PUT"


def compact_top5_message():
    picks = rank_top5_picks()
    if not picks:
        return f"""🏆 Top 5 Today

ยังจัดอันดับไม่ได้
เวลาไทย: {now_text()}"""

    lines = []
    for i, (s, asset, a) in enumerate(picks, 1):
        lines.append(f"{i}. {s} {a.get('score')}/100")

    return f"""🏆 Top 5 Today

{chr(10).join(lines)}

เวลาไทย: {now_text()}
หมายเหตุ: คัดจาก TOP5_UNIVERSE / WATCHLIST"""


def professional_alert_message(symbol, asset, analysis):
    price = analysis.get("price")
    if not price:
        return None

    atr = analysis.get("atr") or price * 0.015
    score = int(analysis.get("score", 50))
    confidence = calculate_signal_confidence(analysis)
    sig = signal_type_from_analysis(asset, analysis)
    price_label = "$" if asset.get("currency") == "USD" else "฿"

    if sig in {"STRONG_CALL", "BUY"}:
        header = "🟢 STRONG CALL SIGNAL" if asset.get("asset_type") == "US_STOCK" else "🟢 BUY ALERT"
        entry_low = price - atr * 0.20
        entry_high = price + atr * 0.10
        sl = price - atr * 0.90
        tp1 = price + atr * 0.80
        tp2 = price + atr * 1.50
        tp3 = price + atr * 2.20
    elif sig in {"STRONG_PUT", "SELL"}:
        header = "🔴 STRONG PUT SIGNAL" if asset.get("asset_type") == "US_STOCK" else "🔴 SELL ALERT"
        if asset.get("asset_type") == "GOLD":
            header = "🔴 SELL ALERT"
        entry_low = price - atr * 0.10
        entry_high = price + atr * 0.20
        sl = price + atr * 0.90
        tp1 = price - atr * 0.80
        tp2 = price - atr * 1.50
        tp3 = price - atr * 2.20
    else:
        return None

    adjusted_word = adjusted_signal_word(asset, analysis, side)
    if adjusted_word in {"BUY WATCH / WAIT FOR CONFIRM", "BUY / NEED CONFIRM"}:
        header = "🟡 " + adjusted_word
    elif adjusted_word in {"SELL WATCH / WAIT FOR CONFIRM", "SELL / RANGE WEAK"}:
        header = "🟠 " + adjusted_word

    if asset.get("asset_type") == "GOLD":
        price_block = get_gold_thai_block_v772(price)
    else:
        price_block = f"ราคา: {price_label}{fmt_num(price)}"

    tf_block = build_timeframe_confirm_final(asset, analysis, side)
    opt_block = suggested_options_contract(asset, analysis)

    reasons = analysis.get("reasons", []) or []
    reasons_text = chr(10).join("- " + str(r) for r in reasons[:4]) if reasons else "- N/A"

    return f"""{header}

Symbol: {symbol}
เวลาไทย: {now_text()}

{price_block}

AI Score: {score}/100
Signal Confidence: {confidence}%
Probability: {analysis.get('probability')}%
มุมมอง: {analysis.get('bias')}
Regime: {analysis.get('regime')}

{tf_block}

{build_trade_plan_3_mai(asset, price, atr, side, analysis)}

{opt_block}

เหตุผลหลัก:
{reasons_text}

หมายเหตุ: เป็นสัญญาณจากระบบ Hybrid ไม่ใช่คำแนะนำการลงทุน"""


# ============================================================
# V7.7 PROFESSIONAL TRADING ASSISTANT
# ============================================================
def clamp(value, low, high):
    try:
        return max(low, min(high, value))
    except Exception:
        return low


def normalized_signal_score(raw_score, side):
    """Avoid impossible-looking 0/100 unless signal is extreme.
    Keeps scale readable for users.
    """
    try:
        score = int(raw_score)
    except Exception:
        score = 50

    if side in {"SELL", "STRONG_PUT"}:
        if score <= 0:
            return 8
        return clamp(score, 5, 45)
    if side in {"BUY", "STRONG_CALL"}:
        if score >= 100:
            return 92
        return clamp(score, 55, 95)
    return clamp(score, 20, 80)


def professional_probability(analysis, side):
    """Probability-like quality score aligned with direction.
    This is not statistical win probability.
    """
    try:
        base = int(analysis.get("probability", 50))
    except Exception:
        base = 50

    score = int(analysis.get("score", 50))
    rsi = safe_float(analysis.get("rsi"), 50) or 50
    rvol = safe_float(analysis.get("rvol"), 1.0) or 1.0
    regime = str(analysis.get("regime", "")).upper()

    directional_strength = abs(score - 50)
    prob = 50 + int(directional_strength * 0.65)

    if side in {"SELL", "STRONG_PUT"} and rsi <= 45:
        prob += 6
    if side in {"BUY", "STRONG_CALL"} and rsi >= 55:
        prob += 6

    if rvol >= 1.3:
        prob += 5
    elif rvol < 0.8:
        prob -= 7

    if "LOW VOL" in regime:
        prob -= 4
    if "TREND" in regime:
        prob += 5

    # Blend with existing probability so it does not jump too wildly.
    prob = int(prob * 0.65 + base * 0.35)
    return clamp(prob, 35, 92)


def professional_signal_confidence(analysis, side):
    prob = professional_probability(analysis, side)
    score = int(analysis.get("score", 50))
    rvol = safe_float(analysis.get("rvol"), 1.0) or 1.0
    regime = str(analysis.get("regime", "")).upper()
    trend = trend_strength_score(analysis)

    conf = int(prob * 0.72 + abs(score - 50) * 0.55 + trend * 1.6)

    if rvol >= 1.5:
        conf += 5
    elif rvol < 0.8:
        conf -= 5

    if "RANGE" in regime:
        conf -= 3
    if "LOW VOL" in regime:
        conf -= 4

    return clamp(conf, 40, 95)


def trend_strength_score(analysis):
    try:
        price = safe_float(analysis.get("price"))
        ema6 = safe_float(analysis.get("ema6"))
        ema12 = safe_float(analysis.get("ema12"))
        ema50 = safe_float(analysis.get("ema50"))
        atr = safe_float(analysis.get("atr"))
        rsi = safe_float(analysis.get("rsi"), 50) or 50

        score = 0
        if price and ema50:
            dist = abs(price - ema50) / ema50 * 100
            if dist >= 2.0:
                score += 3
            elif dist >= 1.0:
                score += 2
            elif dist >= 0.4:
                score += 1

        if ema6 and ema12 and ema50:
            if ema6 > ema12 > ema50 or ema6 < ema12 < ema50:
                score += 3
            elif (ema6 > ema12) or (ema6 < ema12):
                score += 1

        if rsi >= 65 or rsi <= 35:
            score += 2
        elif rsi >= 58 or rsi <= 42:
            score += 1

        if atr and price:
            atr_pct = atr / price * 100
            if atr_pct >= 1.2:
                score += 2
            elif atr_pct >= 0.6:
                score += 1

        return clamp(score, 1, 10)
    except Exception:
        return 5


def trend_strength_text(analysis):
    s = trend_strength_score(analysis)
    if s >= 8:
        label = "Strong"
    elif s >= 5:
        label = "Medium"
    else:
        label = "Weak"
    return f"""📐 Trend Strength
Score: {s}/10
Status: {label}"""


def gold_premium_analysis_block(price_usd=None, thai_gold=None):
    """Compare spot THB per ounce vs Thai gold per baht-weight.
    Prevents confusion between ounce and Thai baht-weight prices.
    """
    if not price_usd:
        return ""

    try:
        usdthb = get_usd_thb_rate()
    except Exception:
        usdthb = None

    if not usdthb:
        return ""

    spot_thb_oz = float(price_usd) * float(usdthb)
    spot_thb_baht_weight = gold_thb_per_baht_weight(price_usd, usdthb)

    bar_sell = None
    if thai_gold:
        bar_sell = thai_gold.get("bar_sell")

    lines = [
        "🧮 Gold Premium Analysis",
        f"Spot THB/oz: {fmt_num(spot_thb_oz, 0)} บาท/ออนซ์",
    ]

    if spot_thb_baht_weight:
        lines.append(f"Spot เทียบบาททอง: {fmt_num(spot_thb_baht_weight, 0)} บาท/บาททอง")

    if bar_sell:
        premium = float(bar_sell) - float(spot_thb_baht_weight or 0)
        premium_pct = premium / float(spot_thb_baht_weight) * 100 if spot_thb_baht_weight else 0
        lines.append(f"Thai Gold Sell: {fmt_num(bar_sell, 0)} บาท/บาททอง")
        lines.append(f"Premium: {premium:+,.0f} บาท ({premium_pct:+.2f}%)")

        if abs(premium_pct) >= 8:
            status = "ข้อมูลต่างมาก ควรตรวจสอบแหล่งราคา/หน่วยราคา"
        elif premium_pct >= 2:
            status = "ไทยแพงกว่า Spot เล็กน้อยถึงปานกลาง"
        elif premium_pct <= -2:
            status = "ไทยต่ำกว่า Spot ผิดปกติหรือมีส่วนต่างหน่วยราคา"
        else:
            status = "สอดคล้องกับ Spot โดยรวม"
        lines.append(f"Status: {status}")
    else:
        lines.append("Thai Gold Sell: N/A")
        lines.append("Status: ยังเทียบ Premium ไม่ได้")

    return "\n".join(lines)


def risk_context_warning(asset, analysis, side):
    warnings = []
    regime = str(analysis.get("regime", "")).upper()
    rvol = safe_float(analysis.get("rvol"), 1.0) or 1.0
    score = int(analysis.get("score", 50))

    if side in {"BUY", "STRONG_CALL"} and "DOWNTREND" in regime:
        warnings.append("⚠️ Buy ระยะสั้น แต่โครงสร้างกลางยังเป็น Downtrend ควรลดขนาดไม้หรือรอยืนยันเบรกแนวต้าน")
    if side in {"SELL", "STRONG_PUT"} and "UPTREND" in regime:
        warnings.append("⚠️ Sell ระยะสั้น แต่โครงสร้างกลางยังเป็น Uptrend ควรระวังแรงเด้งกลับ")
    if "RANGE" in regime:
        warnings.append("⚠️ ตลาดเป็น Range ระบบลดระดับสัญญาณจาก STRONG เป็น WATCH/CONFIRM")
    if "LOW VOL" in regime or rvol < 0.8:
        warnings.append("⚠️ Volume ต่ำ ระบบลดความมั่นใจของสัญญาณ")
    if score <= 3 or score >= 97:
        warnings.append("⚠️ คะแนนสุดขั้ว ระบบปรับให้อ่านง่ายใน V8.1 แต่ควรดู Timeframe Confirm ประกอบ")

    return "\n".join(warnings)



def warning_penalty_score(asset, analysis, side):
    """Penalty for overconfident wording.
    Higher = should downgrade STRONG wording/confidence.
    """
    penalty = 0
    regime = str(analysis.get("regime", "")).upper()
    rvol = safe_float(analysis.get("rvol"), 1.0) or 1.0
    trend = trend_strength_score(analysis)

    if "RANGE" in regime:
        penalty += 18
    if "LOW VOL" in regime:
        penalty += 15
    if rvol < 0.8:
        penalty += 14
    if trend < 5:
        penalty += 18

    if side in {"BUY", "STRONG_CALL"} and "DOWNTREND" in regime:
        penalty += 22
    if side in {"SELL", "STRONG_PUT"} and "UPTREND" in regime:
        penalty += 22

    return penalty


def adjusted_signal_word(asset, analysis, side):
    """Downgrade STRONG labels when warning conditions are present."""
    regime = str(analysis.get("regime", "")).upper()
    trend = trend_strength_score(analysis)
    rvol = safe_float(analysis.get("rvol"), 1.0) or 1.0
    penalty = warning_penalty_score(asset, analysis, side)

    if side in {"BUY", "STRONG_CALL"}:
        if penalty >= 35:
            return "BUY WATCH / WAIT FOR CONFIRM"
        if trend < 5 or "RANGE" in regime or rvol < 0.8:
            return "BUY / NEED CONFIRM"
        return "STRONG BUY"

    if side in {"SELL", "STRONG_PUT"}:
        if penalty >= 35:
            return "SELL WATCH / WAIT FOR CONFIRM"
        if trend < 5 or "RANGE" in regime or rvol < 0.8:
            return "SELL / RANGE WEAK"
        return "STRONG SELL"

    return "WAIT"


def adjusted_confidence(analysis, side):
    conf = professional_signal_confidence(analysis, side)
    penalty = warning_penalty_score({}, analysis, side)
    conf = conf - int(penalty * 0.45)
    return clamp(conf, 35, 92)


def adjusted_probability(analysis, side):
    prob = professional_probability(analysis, side)
    penalty = warning_penalty_score({}, analysis, side)
    prob = prob - int(penalty * 0.35)
    return clamp(prob, 35, 90)


def build_timeframe_confirm_v771(asset, analysis, side):
    """Same TF lines, but overall label is downgraded by warning weight."""
    try:
        base = build_timeframe_confirm(asset, analysis)
        adjusted = adjusted_signal_word(asset, analysis, side)

        # Replace only the Overall line.
        lines = base.splitlines()
        out = []
        for line in lines:
            if line.startswith("Overall"):
                out.append(f"Overall : {adjusted}")
            else:
                out.append(line)
        return "\n".join(out)
    except Exception:
        return build_timeframe_confirm(asset, analysis)


# ============================================================
# V7.7.2 TRADE PLAN 3 MAI + GOLD THAI RESTORE
# ============================================================
def thai_gold_factor_from_spot(price_usd):
    """Return factor to convert XAUUSD level to Thai gold baht-weight price.
    Prefer GoldTraders bar_sell / spot price so Thai levels align with Thai market.
    """
    if not price_usd:
        return None, None
    try:
        usdthb = get_usd_thb_rate()
    except Exception:
        usdthb = None

    thai_gold = None
    try:
        thai_gold = get_thai_gold_price_or_estimate(price_usd, usdthb)
    except Exception:
        thai_gold = None

    if thai_gold and thai_gold.get("bar_sell"):
        try:
            return float(thai_gold.get("bar_sell")) / float(price_usd), thai_gold
        except Exception:
            pass

    if usdthb:
        try:
            return gold_thb_per_baht_weight(price_usd, usdthb) / float(price_usd), thai_gold
        except Exception:
            pass

    return None, thai_gold


def fmt_level_asset(asset, value, thai_factor=None):
    if value is None:
        return "N/A"
    if asset.get("asset_type") == "GOLD":
        if thai_factor:
            return f"${fmt_num(value)} / {fmt_num(value * thai_factor, 0)} บาท"
        return f"${fmt_num(value)}"
    price_label = "$" if asset.get("currency") == "USD" else "฿"
    return f"{price_label}{fmt_num(value)}"



def strict_entry_multiplier(asset, analysis=None):
    """Increase entry distance when signal quality is weak."""
    m = 1.0
    try:
        if analysis:
            regime = str(analysis.get("regime", "")).upper()
            rvol = safe_float(analysis.get("rvol"), 1.0) or 1.0
            trend = trend_strength_score(analysis)

            if "RANGE" in regime:
                m += 0.25
            if "LOW VOL" in regime or rvol < 0.8:
                m += 0.25
            if trend < 5:
                m += 0.25
            if asset.get("asset_type") == "GOLD":
                m += 0.15
    except Exception:
        pass
    return clamp(m, 1.0, 1.9)


def build_trade_plan_3_mai(asset, price, atr, side, analysis=None):
    """Strict 3-entry plan for US stocks, Thai stocks, and gold."""
    if not price:
        return """🎯 แผนซื้อขาย 3 ไม้
ข้อมูลราคาไม่พอ"""

    if not atr:
        atr = price * 0.012

    strict_m = strict_entry_multiplier(asset, analysis)
    thai_factor = None
    if asset.get("asset_type") == "GOLD":
        thai_factor, _ = thai_gold_factor_from_spot(price)

    if side in {"SELL", "STRONG_PUT"}:
        entry1 = price + atr * 0.45 * strict_m
        entry2 = price + atr * 0.90 * strict_m
        entry3 = price + atr * 1.45 * strict_m

        tp1 = price - atr * 0.75
        tp2 = price - atr * 1.35
        tp3 = price - atr * 2.05

        sl = price + atr * 1.80 * strict_m

        return f"""🎯 แผนขาย/ซื้อคืน 3 ไม้ แบบเข้มงวด

ขายไม้ 1: {fmt_level_asset(asset, entry1, thai_factor)}
ขายไม้ 2: {fmt_level_asset(asset, entry2, thai_factor)}
ขายไม้ 3: {fmt_level_asset(asset, entry3, thai_factor)}

ซื้อคืน/TP1: {fmt_level_asset(asset, tp1, thai_factor)}
ซื้อคืน/TP2: {fmt_level_asset(asset, tp2, thai_factor)}
ซื้อคืน/TP3: {fmt_level_asset(asset, tp3, thai_factor)}

จุดคุมความเสี่ยง SL:
{fmt_level_asset(asset, sl, thai_factor)}

กติกาเข้าไม้:
- ไม่ขายไล่ราคา ให้รอเด้งเข้าโซนขาย
- ถ้า Volume ต่ำ ให้เริ่มพิจารณาเฉพาะไม้ 2-3
- ถ้าแท่งกลับตัวไม่ชัด ให้รอแท่งยืนยันก่อน"""

    buy1 = price - atr * 0.55 * strict_m
    buy2 = price - atr * 1.05 * strict_m
    buy3 = price - atr * 1.65 * strict_m

    sell1 = price + atr * 0.75 * strict_m
    sell2 = price + atr * 1.35 * strict_m
    sell3 = price + atr * 2.05 * strict_m

    sl = price - atr * 1.80 * strict_m

    return f"""🎯 แผนซื้อ/ขาย 3 ไม้ แบบเข้มงวด

ซื้อไม้ 1: {fmt_level_asset(asset, buy1, thai_factor)}
ซื้อไม้ 2: {fmt_level_asset(asset, buy2, thai_factor)}
ซื้อไม้ 3: {fmt_level_asset(asset, buy3, thai_factor)}

ขาย/TP1: {fmt_level_asset(asset, sell1, thai_factor)}
ขาย/TP2: {fmt_level_asset(asset, sell2, thai_factor)}
ขาย/TP3: {fmt_level_asset(asset, sell3, thai_factor)}

จุดคุมความเสี่ยง SL:
{fmt_level_asset(asset, sl, thai_factor)}

กติกาเข้าไม้:
- ไม่ซื้อไล่ราคา ให้รอย่อเข้าโซนซื้อ
- ถ้า Volume ต่ำ ให้เริ่มพิจารณาเฉพาะไม้ 2-3
- ถ้าเป็น Buy สวน Downtrend ให้ลดขนาดไม้ลงครึ่งหนึ่ง"""

def get_gold_thai_block_v772(price_usd=None):
    """Gold block guaranteed to show Thai gold prices if GoldTraders/fallback works."""
    try:
        usdthb = get_usd_thb_rate()
    except Exception:
        usdthb = None

    thb_oz = None
    try:
        if price_usd and usdthb:
            thb_oz = float(price_usd) * float(usdthb)
    except Exception:
        thb_oz = None

    thai_gold = None
    try:
        thai_gold = get_thai_gold_price_or_estimate(price_usd, usdthb)
    except Exception as e:
        print("get_gold_thai_block_v772 error:", e)

    lines = []
    if price_usd:
        lines.append(f"ราคา: ${fmt_num(price_usd)}")
        if thb_oz:
            lines.append(f"≈ {fmt_num(thb_oz, 0)} บาท/ออนซ์")

    lines.append("")
    lines.append("🏆 ราคาทองไทย")
    if thai_gold:
        lines.append(f"ทองแท่งขายออก: {fmt_num(thai_gold.get('bar_sell'), 0)} บาท")
        lines.append(f"ทองแท่งรับซื้อ: {fmt_num(thai_gold.get('bar_buy'), 0)} บาท")
        lines.append(f"ทองรูปพรรณขายออก: {fmt_num(thai_gold.get('ornament_sell'), 0)} บาท")
        lines.append(f"แหล่งข้อมูล: {thai_gold.get('source', 'GoldTraders / Estimate')}")
    else:
        lines.append("ทองแท่งขายออก: N/A")
        lines.append("ทองแท่งรับซื้อ: N/A")
        lines.append("ทองรูปพรรณขายออก: N/A")
        lines.append("แหล่งข้อมูล: N/A")

    return "\n".join(lines)

def professional_alert_message_v77(symbol, asset, analysis):
    price = analysis.get("price")
    if not price:
        return None

    sig = signal_type_from_analysis(asset, analysis)
    if sig == "NONE":
        return None

    side = sig
    if sig == "BUY":
        side = "BUY"
    elif sig == "SELL":
        side = "SELL"

    atr = analysis.get("atr") or price * 0.015
    score = normalized_signal_score(analysis.get("score", 50), side)
    confidence = adjusted_confidence(analysis, side)
    probability = adjusted_probability(analysis, side)
    price_label = "$" if asset.get("currency") == "USD" else "฿"

    if side in {"STRONG_CALL", "BUY"}:
        header = "🟢 STRONG CALL SIGNAL" if asset.get("asset_type") == "US_STOCK" else "🟢 BUY ALERT"
        entry_low = price - atr * 0.20
        entry_high = price + atr * 0.10
        sl = price - atr * 0.90
        tp1 = price + atr * 0.80
        tp2 = price + atr * 1.50
        tp3 = price + atr * 2.20
    elif side in {"STRONG_PUT", "SELL"}:
        header = "🔴 STRONG PUT SIGNAL" if asset.get("asset_type") == "US_STOCK" else "🔴 SELL ALERT"
        if asset.get("asset_type") == "GOLD":
            header = "🔴 SELL ALERT"
        entry_low = price - atr * 0.10
        entry_high = price + atr * 0.20
        sl = price + atr * 0.90
        tp1 = price - atr * 0.80
        tp2 = price - atr * 1.50
        tp3 = price - atr * 2.20
    else:
        return None

    thai_gold = None
    if asset.get("asset_type") == "GOLD":
        try:
            thai_gold = get_thai_gold_price_or_estimate(price, get_usd_thb_rate())
        except Exception:
            thai_gold = None
        price_block = get_gold_thai_block_v772(price)
        premium_block = gold_premium_analysis_block(price, thai_gold)
    else:
        price_block = f"ราคา: {price_label}{fmt_num(price)}"
        premium_block = ""

    tf_block = build_timeframe_confirm_final(asset, analysis, side)
    trend_block = trend_strength_text(analysis)
    opt_block = suggested_options_contract(asset, analysis)
    warning_block = risk_context_warning(asset, analysis, side)

    reasons = analysis.get("reasons", []) or []
    reasons_text = chr(10).join("- " + str(r) for r in reasons[:5]) if reasons else "- N/A"

    return f"""{header}

Symbol: {symbol}
เวลาไทย: {now_text()}

{price_block}

AI Score: {score}/100
Signal Confidence: {confidence}%
Probability: {probability}%
มุมมอง: {analysis.get('bias')}
Regime: {analysis.get('regime')}

{trend_block}

{tf_block}

{premium_block}

{build_trade_plan_3_mai(asset, price, atr, side, analysis)}

{opt_block}

เหตุผลหลัก:
{reasons_text}

{warning_block}

หมายเหตุ: เป็นสัญญาณจากระบบ Hybrid ไม่ใช่คำแนะนำการลงทุน"""


# ============================================================
# V7.7.4 STRICT ALERT GATE
# ============================================================
def tf_confirm_counts(asset, analysis, side):
    """Return number of TFs aligned with side from 5m/15m/1H synthetic confirm."""
    block = build_timeframe_confirm_v771(asset, analysis, side) if "build_timeframe_confirm_v771" in globals() else build_timeframe_confirm(asset, analysis)
    lines = block.splitlines()
    target = "BUY" if side in {"BUY", "STRONG_CALL"} else "SELL"
    count = 0
    total = 0
    for line in lines:
        if line.startswith("5m") or line.startswith("15m") or line.startswith("1H"):
            total += 1
            if target in line:
                count += 1
    return count, total


def strict_alert_gate(symbol, asset, analysis, sig):
    """Decide if alert is strong enough to send.
    Returns (allowed: bool, reason: str)
    """
    if not STRICT_ALERT_MODE:
        return True, "STRICT_ALERT_MODE=false"

    score = int(analysis.get("score", 50))
    side = sig
    confidence = adjusted_confidence(analysis, side) if "adjusted_confidence" in globals() else calculate_signal_confidence(analysis)
    trend = trend_strength_score(analysis) if "trend_strength_score" in globals() else 5
    rvol = safe_float(analysis.get("rvol"), 1.0) or 1.0
    regime = str(analysis.get("regime", "")).upper()

    # 1) Score must be extreme enough.
    if sig in {"STRONG_CALL", "BUY"}:
        if score < STRICT_CALL_SCORE and asset.get("asset_type") == "US_STOCK":
            return False, f"Score {score} < STRICT_CALL_SCORE {STRICT_CALL_SCORE}"
        if asset.get("asset_type") != "US_STOCK" and score < AUTO_ALERT_MIN_SCORE:
            return False, f"Score {score} < AUTO_ALERT_MIN_SCORE {AUTO_ALERT_MIN_SCORE}"

    if sig in {"STRONG_PUT", "SELL"}:
        if score > STRICT_PUT_SCORE and asset.get("asset_type") == "US_STOCK":
            return False, f"Score {score} > STRICT_PUT_SCORE {STRICT_PUT_SCORE}"
        if asset.get("asset_type") != "US_STOCK" and score > AUTO_ALERT_MAX_SCORE:
            return False, f"Score {score} > AUTO_ALERT_MAX_SCORE {AUTO_ALERT_MAX_SCORE}"

    # 2) Confidence.
    if confidence < STRICT_MIN_CONFIDENCE:
        return False, f"Confidence {confidence}% < {STRICT_MIN_CONFIDENCE}%"

    # 3) Trend strength.
    if trend < STRICT_MIN_TREND_STRENGTH:
        return False, f"Trend Strength {trend}/10 < {STRICT_MIN_TREND_STRENGTH}/10"

    # 4) Volume.
    if rvol < STRICT_MIN_RVOL:
        return False, f"RVOL {rvol:.2f} < {STRICT_MIN_RVOL:.2f}"

    # 5) Range / low vol filters.
    if "LOW VOL" in regime:
        return False, "Regime LOW VOL"
    if "RANGE" in regime and not (asset.get("asset_type") == "GOLD" and STRICT_ALLOW_RANGE_GOLD):
        return False, "Regime RANGE"

    # 6) Counter-trend block.
    if sig in {"STRONG_CALL", "BUY"} and "DOWNTREND" in regime:
        return False, "Buy signal but regime is DOWNTREND"
    if sig in {"STRONG_PUT", "SELL"} and "UPTREND" in regime:
        return False, "Sell signal but regime is UPTREND"

    # 7) Timeframe confirmation.
    if STRICT_REQUIRE_TF_CONFIRM:
        aligned, total = tf_confirm_counts(asset, analysis, sig)
        if total >= 3 and aligned < 3:
            return False, f"TF Confirm {aligned}/{total}, require 3/3"

    return True, "PASS"


def strict_signal_type_from_analysis(asset, analysis):
    """Return NONE unless the signal passes strict alert gate."""
    raw_sig = signal_type_from_analysis(asset, analysis)
    if raw_sig == "NONE":
        return "NONE", "No raw signal"

    ok, reason = strict_alert_gate(asset.get("symbol", ""), asset, analysis, raw_sig)
    if not ok:
        return "NONE", reason

    return raw_sig, reason


# ============================================================
# V8.1 TOP 5 DAILY SCANNER
# ============================================================
_LAST_TOP5_SENT_DATE = None


def rank_top5_picks():
    symbols = globals().get("TOP5_UNIVERSE", WATCHLIST)
    picks = []
    for sym in symbols:
        try:
            asset = normalize_asset(sym)
            quote, closes, highs, lows, opens, volumes = get_market_data(asset)
            analysis = analyze_signal(asset, quote, closes, highs, lows, opens, volumes)
            score = int(analysis.get("score", 50))
            confidence = calculate_signal_confidence(analysis) if "calculate_signal_confidence" in globals() else abs(score - 50) + 50
            trend = trend_strength_score(analysis) if "trend_strength_score" in globals() else 5
            rank_score = score * 0.50 + confidence * 0.30 + trend * 2.0
            if asset.get("asset_type") == "GOLD":
                rank_score -= 5
            picks.append((rank_score, sym, asset, analysis))
        except Exception as e:
            print(f"Top5 skip {sym}: {e}")
    picks.sort(key=lambda x: x[0], reverse=True)
    return [(sym, asset, analysis) for _, sym, asset, analysis in picks[:5]]


def build_top5_daily_message():
    picks = rank_top5_picks()
    if not picks:
        return f"""🏆 Top 5 Daily Picks

ยังจัดอันดับไม่ได้
เวลาไทย: {now_text()}"""

    lines = []
    for i, (sym, asset, analysis) in enumerate(picks, 1):
        lines.append(
            f"{i}. {sym} {analysis.get('score')}/100 | {analysis.get('bias')} | {analysis.get('regime')}"
        )

    return f"""🏆 Top 5 Daily Picks

{chr(10).join(lines)}

เวลาไทย: {now_text()}
หมายเหตุ: คัดจาก TOP5_UNIVERSE ด้วยระบบ V8.1"""


def should_send_top5_now():
    global _LAST_TOP5_SENT_DATE
    if not globals().get("ENABLE_TOP5_DAILY", True):
        return False

    try:
        now = datetime.now(timezone.utc) + timedelta(hours=7)
        hhmm = now.strftime("%H:%M")
        today = now.strftime("%Y-%m-%d")
        target = globals().get("TOP5_DAILY_TIME_TH", "21:15")

        if hhmm == target and _LAST_TOP5_SENT_DATE != today:
            _LAST_TOP5_SENT_DATE = today
            return True
    except Exception as e:
        print("should_send_top5_now error:", e)

    return False


def maybe_send_top5_daily():
    try:
        if should_send_top5_now() and ALERT_USER_IDS:
            msg = build_top5_daily_message()
            for uid in ALERT_USER_IDS:
                line_push(uid, msg)
    except Exception as e:
        print("maybe_send_top5_daily error:", e)


# ============================================================
# V8 FINAL PRODUCTION HARDENING
# ============================================================
def get_cooldown_ts(alert_key):
    try:
        conn = db()
        row = conn.execute("SELECT last_sent_ts FROM alert_cooldown WHERE alert_key=?", (alert_key,)).fetchone()
        conn.close()
        return float(row["last_sent_ts"]) if row else 0.0
    except Exception:
        return 0.0


def set_cooldown_ts(alert_key, ts=None):
    try:
        if ts is None:
            ts = time.time()
        conn = db()
        conn.execute(
            "INSERT INTO alert_cooldown(alert_key, last_sent_ts) VALUES(?, ?) "
            "ON CONFLICT(alert_key) DO UPDATE SET last_sent_ts=excluded.last_sent_ts",
            (alert_key, ts),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print("set_cooldown_ts error:", e)


def cooldown_pass(alert_key):
    last = get_cooldown_ts(alert_key)
    return (time.time() - last) >= ALERT_COOLDOWN_MINUTES * 60


def timeframe_4h_confirm(asset, analysis, side):
    """Best-effort 4H confirm.
    Uses Yahoo/TwelveData daily/available data when true 4H is unavailable.
    Conservative: if insufficient data, returns NEUTRAL.
    """
    try:
        closes = analysis.get("closes_4h") or analysis.get("closes") or []
        if not closes or len(closes) < 20:
            # Fall back to current EMA alignment.
            ema6 = safe_float(analysis.get("ema6"))
            ema12 = safe_float(analysis.get("ema12"))
            ema50 = safe_float(analysis.get("ema50"))
            rsi = safe_float(analysis.get("rsi"), 50)
            tf = timeframe_side_from_numbers(ema6, ema12, ema50, rsi) if "timeframe_side_from_numbers" in globals() else "NEUTRAL"
        else:
            ema_fast = sum(closes[-6:]) / 6
            ema_mid = sum(closes[-12:]) / 12
            ema_long = sum(closes[-20:]) / 20
            if ema_fast > ema_mid > ema_long:
                tf = "BUY"
            elif ema_fast < ema_mid < ema_long:
                tf = "SELL"
            else:
                tf = "NEUTRAL"

        target = "BUY" if side in {"BUY", "STRONG_CALL"} else "SELL"
        return tf, tf == target
    except Exception:
        return "NEUTRAL", False


def build_timeframe_confirm_final(asset, analysis, side):
    base = build_timeframe_confirm_v771(asset, analysis, side) if "build_timeframe_confirm_v771" in globals() else build_timeframe_confirm(asset, analysis)
    tf4h, ok4h = timeframe_4h_confirm(asset, analysis, side)
    lines = base.splitlines()
    out = []
    inserted = False
    for line in lines:
        out.append(line)
        if line.startswith("1H"):
            out.append(f"4H : {tf4h}")
            inserted = True
    if not inserted:
        out.append(f"4H : {tf4h}")

    target = "BUY" if side in {"BUY", "STRONG_CALL"} else "SELL"
    if STRICT_REQUIRE_4H_CONFIRM and not ok4h:
        out = [("Overall : WAIT FOR 4H CONFIRM" if x.startswith("Overall") else x) for x in out]
    elif f"Overall : STRONG {target}" not in "\n".join(out):
        pass
    return "\n".join(out)


def dynamic_position_size(asset, analysis, side):
    confidence = calculate_signal_confidence_v2(asset, analysis, side) if "calculate_signal_confidence_v2" in globals() else calculate_signal_confidence(analysis)
    trend = trend_strength_score(analysis) if "trend_strength_score" in globals() else 5
    rvol = safe_float(analysis.get("rvol"), 1.0) or 1.0
    regime = str(analysis.get("regime", "")).upper()
    rsi = safe_float(analysis.get("rsi"))
    side_upper = str(side or "").upper()

    risk_points = 0
    warnings = []

    if confidence >= 85:
        risk_points += 2
    elif confidence >= 72:
        risk_points += 1

    if trend >= 8:
        risk_points += 2
    elif trend >= 5:
        risk_points += 1

    if rvol >= 1.3:
        risk_points += 1
    elif rvol < 0.85:
        risk_points -= 1

    if "RANGE" in regime or "LOW VOL" in regime:
        risk_points -= 1
        warnings.append("Regime เป็น Range/Low Vol ลดขนาดไม้")

    tf4h, ok4h = timeframe_4h_confirm(asset, analysis, side)
    if ok4h:
        risk_points += 1
    else:
        risk_points -= 1

    oversold_sell = side_upper in {"SELL", "PUT"} and rsi is not None and rsi <= 35
    overbought_call = side_upper in {"BUY", "CALL"} and rsi is not None and rsi >= 72
    if oversold_sell:
        risk_points -= 3
        warnings.append("RSI ต่ำ/oversold มีโอกาสรีบาวด์แรง ห้าม SELL/PUT ไล่ราคา")
    if overbought_call:
        risk_points -= 2
        warnings.append("RSI สูง/overbought ระวังไล่ CALL/BUY ตอนปลายรอบ")

    if risk_points >= 5:
        level = "LOW"
        size = "เต็มแผนได้ แต่ยังต้องคุม SL"
        percent = "75-100% ของขนาดไม้ปกติ"
    elif risk_points >= 3:
        level = "MEDIUM"
        size = "เข้าแบบมาตรฐาน"
        percent = "40-60% ของขนาดไม้ปกติ"
    else:
        level = "HIGH"
        size = "ลดขนาดไม้ / รอ confirmation"
        percent = "20-30% ของขนาดไม้ปกติ"

    if oversold_sell:
        level = "HIGH"
        percent = "25-50% ของขนาดไม้ปกติ"
        size = "รอเด้งเข้าโซนขายเท่านั้น ไม่ขายไล่ราคา"
    if overbought_call and level == "LOW":
        level = "MEDIUM"
        percent = "40-60% ของขนาดไม้ปกติ"
        size = "รอย่อ/รอ breakout confirmation ไม่ไล่ราคา"

    warn_text = ""
    if warnings:
        warn_text = "\nRisk Notes:\n" + "\n".join("- " + w for w in warnings[:4])

    return f"""⚖️ Dynamic Position Size
Risk Level: {level}
Suggested Size: {percent}
Action: {size}{warn_text}"""


def final_gate_extra(asset, analysis, sig):
    if sig == "NONE":
        return False, "No signal"

    if STRICT_REQUIRE_4H_CONFIRM:
        _, ok4h = timeframe_4h_confirm(asset, analysis, sig)
        if not ok4h:
            return False, "4H not confirmed"

    return True, "PASS"


def should_send_alert_final(symbol, sig, analysis, asset):
    market_ok, market_reason = market_guard_check(symbol, asset)
    if not market_ok:
        return False, market_reason

    alert_key = f"{symbol}:{sig}"
    if not cooldown_pass(alert_key):
        return False, f"Cooldown active {ALERT_COOLDOWN_MINUTES}m"

    ok, reason = final_gate_extra(asset, analysis, sig)
    if not ok:
        return False, reason

    if "should_send_alert" in globals():
        try:
            if not should_send_alert(alert_key, analysis.get("score", 50)):
                return False, "Base should_send_alert rejected"
        except Exception:
            pass

    return True, "PASS"


def mark_alert_sent_final(symbol, sig):
    set_cooldown_ts(f"{symbol}:{sig}")


def append_final_blocks_to_message(msg, asset, analysis, side):
    pos = dynamic_position_size(asset, analysis, side)
    if "⚖️ Dynamic Position Size" not in msg:
        msg = msg.replace("หมายเหตุ: เป็นสัญญาณจากระบบ Hybrid ไม่ใช่คำแนะนำการลงทุน", pos + "\n\nหมายเหตุ: เป็นสัญญาณจากระบบ Hybrid ไม่ใช่คำแนะนำการลงทุน")
    msg = msg.replace("ระบบปรับให้อ่านง่ายใน V7.7", "ระบบปรับให้อ่านง่ายใน V8 Final.4 Market Leaders Watchlist.4 Market Leaders Watchlist.3 Expanded Sector Watchlist.2 US Premarket Alert Fix")
    msg = msg.replace("ระบบปรับให้อ่านง่ายใน V8.1", "ระบบปรับให้อ่านง่ายใน V8 Final.4 Market Leaders Watchlist.4 Market Leaders Watchlist.3 Expanded Sector Watchlist.2 US Premarket Alert Fix")
    return msg


# ============================================================
# V8 FINAL.1 MARKET HOURS GUARD
# ============================================================
def th_now_dt():
    return datetime.now(timezone.utc) + timedelta(hours=7)


def parse_hhmm(value):
    h, m = str(value).split(":")
    return int(h), int(m)


def minutes_now_th():
    n = th_now_dt()
    return n.hour * 60 + n.minute


def hhmm_to_minutes(value):
    h, m = parse_hhmm(value)
    return h * 60 + m


def is_weekday_th():
    return th_now_dt().weekday() < 5


def time_in_range_th(start_hhmm, end_hhmm):
    now_m = minutes_now_th()
    start = hhmm_to_minutes(start_hhmm)
    end = hhmm_to_minutes(end_hhmm)
    if start <= end:
        return start <= now_m <= end
    return now_m >= start or now_m <= end


def is_th_market_open_now():
    if not is_weekday_th():
        return False
    return (
        time_in_range_th(TH_MARKET_MORNING_START, TH_MARKET_MORNING_END)
        or time_in_range_th(TH_MARKET_AFTERNOON_START, TH_MARKET_AFTERNOON_END)
    )


def is_us_market_open_now_th():
    if not is_weekday_th():
        return False
    regular_or_after = time_in_range_th(US_SESSION_START_TH, US_SESSION_END_TH)
    premarket = False
    try:
        premarket = US_ALLOW_PREMARKET_ALERTS and time_in_range_th(US_PREMARKET_START_TH, US_SESSION_START_TH)
    except Exception:
        premarket = False
    return regular_or_after or premarket


def asset_market_open_for_alert(asset):
    if not ENABLE_MARKET_HOURS_GUARD:
        return True, "Market hours guard disabled"

    atype = asset.get("asset_type")
    if atype == "THAI_STOCK":
        return is_th_market_open_now(), "Thai market closed"

    if atype == "US_STOCK":
        return is_us_market_open_now_th(), "US market closed"

    if atype == "GOLD":
        return bool(ALLOW_GOLD_24H_ALERTS), "Gold 24H alerts disabled"

    return True, "Unknown asset type allowed"


def _cooldown_get(alert_key):
    try:
        if "get_cooldown_ts" in globals():
            return get_cooldown_ts(alert_key)
        conn = db()
        row = conn.execute("SELECT last_sent_ts FROM alert_cooldown WHERE alert_key=?", (alert_key,)).fetchone()
        conn.close()
        return float(row["last_sent_ts"]) if row else 0.0
    except Exception:
        return 0.0


def _cooldown_set(alert_key):
    try:
        if "set_cooldown_ts" in globals():
            set_cooldown_ts(alert_key, time.time())
            return
        conn = db()
        conn.execute(
            "INSERT INTO alert_cooldown(alert_key, last_sent_ts) VALUES(?, ?) "
            "ON CONFLICT(alert_key) DO UPDATE SET last_sent_ts=excluded.last_sent_ts",
            (alert_key, time.time()),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print("cooldown set error:", e)


def symbol_cooldown_key(symbol):
    return f"SYMBOL:{str(symbol).upper()}"


def symbol_cooldown_pass(symbol):
    last = _cooldown_get(symbol_cooldown_key(symbol))
    return (time.time() - last) >= SYMBOL_COOLDOWN_MINUTES * 60


def mark_symbol_cooldown(symbol):
    _cooldown_set(symbol_cooldown_key(symbol))


def market_guard_check(symbol, asset):
    ok, reason = asset_market_open_for_alert(asset)
    if not ok:
        return False, reason
    if not symbol_cooldown_pass(symbol):
        return False, f"Symbol cooldown active {SYMBOL_COOLDOWN_MINUTES}m"
    return True, "PASS"


@app.route("/market-hours-status", methods=["GET"])
def market_hours_status():
    return jsonify({
        "time_th": now_text(),
        "guard_enabled": ENABLE_MARKET_HOURS_GUARD,
        "thai_market_open": is_th_market_open_now(),
        "us_market_open": is_us_market_open_now_th(),
        "allow_gold_24h": ALLOW_GOLD_24H_ALERTS,
        "thai_sessions": {
            "morning": [TH_MARKET_MORNING_START, TH_MARKET_MORNING_END],
            "afternoon": [TH_MARKET_AFTERNOON_START, TH_MARKET_AFTERNOON_END],
        },
        "us_session_th": [US_SESSION_START_TH, US_SESSION_END_TH],
        "us_premarket_start_th": US_PREMARKET_START_TH,
        "us_allow_premarket_alerts": US_ALLOW_PREMARKET_ALERTS,
        "symbol_cooldown_minutes": SYMBOL_COOLDOWN_MINUTES,
    })

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
            maybe_send_premarket_and_top5()

            if ENABLE_AUTO_ALERTS and ALERT_USER_IDS:
                for symbol in build_v8_scan_watchlist():
                    try:
                        if v8_skip_symbol(symbol):
                            continue
                        asset = normalize_asset(symbol)

                        if not should_scan_symbol_by_session(asset):
                            continue

                        quote, closes, highs, lows, opens, volumes = get_market_data(asset)
                        analysis = analyze_signal(asset, quote, closes, highs, lows, opens, volumes)
                        sig, gate_reason = strict_signal_type_from_analysis(asset, analysis)

                        ok_final, reason_final = should_send_alert_final(symbol, sig, analysis, asset)
                        if sig != "NONE" and ok_final:
                            message = build_auto_signal_message(symbol, asset, analysis)
                            if message:
                                for user_id in ALERT_USER_IDS:
                                    line_push(user_id, message)

                                mark_symbol_cooldown(symbol)

                                save_signal(
                                    asset["symbol"],
                                    asset["asset_type"],
                                    analysis.get("price"),
                                    analysis.get("score"),
                                    analysis.get("bias"),
                                    sig,
                                    analysis.get("regime"),
                                    analysis.get("probability"),
                                    message,
                                )

                        time.sleep(3)

                    except Exception as e:
                        msg = str(e)
                        if V8_SKIP_INVALID_SYMBOLS and ("possibly delisted" in msg.lower() or "no price data" in msg.lower()):
                            if V8_LOG_SKIPPED_SYMBOLS:
                                print(f"V8 skipped invalid/no-data symbol {symbol}: {e}")
                        else:
                            print(f"Auto Signal Pro error for {symbol}: {e}")

            time.sleep(max(30, SIGNAL_SCAN_SECONDS))

        except Exception as e:
            print(f"Auto Signal Pro loop error: {e}")
            time.sleep(60)



# ============================================================
# V9 INSTITUTIONAL LAYER FREE 100%
# Backtest + News/Earnings Fallback + Sector/Breadth + Risk Engine + Options Hybrid Sim
# No paid API required. Primary free source: yfinance + local SQLite.
# ============================================================
V9_ENABLED = os.getenv("V9_ENABLED", "true").lower() == "true"
V9_BACKTEST_PERIOD = os.getenv("V9_BACKTEST_PERIOD", "1y")
V9_BACKTEST_INTERVAL = os.getenv("V9_BACKTEST_INTERVAL", "1d")
V9_BACKTEST_INITIAL_CAPITAL = float(os.getenv("V9_BACKTEST_INITIAL_CAPITAL", "10000"))
V9_RISK_PER_TRADE_PCT = float(os.getenv("V9_RISK_PER_TRADE_PCT", "1.0"))
V9_MAX_POSITION_PCT = float(os.getenv("V9_MAX_POSITION_PCT", "20.0"))
V9_MAX_DAILY_LOSS_PCT = float(os.getenv("V9_MAX_DAILY_LOSS_PCT", "3.0"))
V9_MAX_OPEN_POSITIONS = int(os.getenv("V9_MAX_OPEN_POSITIONS", "5"))
V9_OPTIONS_DTE = int(os.getenv("V9_OPTIONS_DTE", "14"))
V9_OPTIONS_IV_FALLBACK = float(os.getenv("V9_OPTIONS_IV_FALLBACK", "0.55"))
V9_SECTOR_BREADTH_SYMBOLS = env_list(
    "V9_SECTOR_BREADTH_SYMBOLS",
    "SPY,QQQ,IWM,XLK,XLF,XLE,XLV,XLY,XLP,XLI,XLC,XLU,XLB,SMH,ARKK"
)
V9_EARNINGS_WINDOW_DAYS = int(os.getenv("V9_EARNINGS_WINDOW_DAYS", "7"))

V9_SECTOR_MAP = {
    "NVDA":"SEMIS/AI", "AMD":"SEMIS/AI", "AVGO":"SEMIS/AI", "SMCI":"SEMIS/AI", "MU":"SEMIS/AI", "ARM":"SEMIS/AI", "TSM":"SEMIS/AI",
    "AAPL":"MEGA TECH", "MSFT":"MEGA TECH", "META":"MEGA TECH", "GOOGL":"MEGA TECH", "GOOG":"MEGA TECH", "AMZN":"MEGA TECH", "NFLX":"MEGA TECH",
    "TSLA":"EV/HIGH BETA", "RIVN":"EV/HIGH BETA", "NIO":"EV/HIGH BETA", "PLTR":"AI/SOFTWARE", "CRWD":"SOFTWARE", "SNOW":"SOFTWARE", "NET":"SOFTWARE", "DDOG":"SOFTWARE",
    "JPM":"FINANCIAL", "BAC":"FINANCIAL", "XOM":"ENERGY", "CVX":"ENERGY", "UNH":"HEALTHCARE", "LLY":"HEALTHCARE", "WMT":"CONSUMER",
    "QQQ":"NASDAQ ETF", "SPY":"S&P500 ETF", "IWM":"SMALL CAP ETF", "DIA":"DOW ETF", "SMH":"SEMIS ETF",
}


def v9_price_frame(symbol, period=None, interval=None):
    asset = normalize_asset(symbol)
    period = period or V9_BACKTEST_PERIOD
    interval = interval or V9_BACKTEST_INTERVAL
    data = yf.Ticker(asset["yf_symbol"]).history(period=period, interval=interval, auto_adjust=False)
    if data is None or data.empty:
        raise RuntimeError(f"V9: no yfinance data for {symbol}")
    data = data.dropna(subset=["Close"])
    return asset, data


def v9_point_signal(closes, highs, lows, volumes):
    if len(closes) < 55:
        return {"side":"WAIT", "score":50, "reason":"insufficient data"}
    price = closes[-1]
    e6, e12, e50 = ema(closes, 6), ema(closes, 12), ema(closes, 50)
    rsi = calc_rsi(closes, 14)
    atr = calc_atr(highs, lows, closes, 14)
    rvol = calc_rvol(volumes, 20) or 1.0
    score = 50
    reasons = []
    if e6 and e12 and e50:
        if price > e6 > e12 > e50:
            score += 22; reasons.append("price/EMA stack bullish")
        elif price < e6 < e12 < e50:
            score -= 22; reasons.append("price/EMA stack bearish")
        elif price > e50:
            score += 8; reasons.append("price above EMA50")
        elif price < e50:
            score -= 8; reasons.append("price below EMA50")
    if rsi is not None:
        if 52 <= rsi <= 68:
            score += 8; reasons.append("RSI momentum healthy")
        elif rsi >= 75:
            score -= 6; reasons.append("RSI extended")
        elif 32 <= rsi <= 48:
            score -= 6; reasons.append("RSI weak")
        elif rsi <= 25:
            score += 4; reasons.append("RSI oversold rebound watch")
    if rvol >= 1.3:
        score += 5 if score >= 50 else -5; reasons.append("relative volume confirms move")
    score = max(0, min(100, int(score)))
    side = "CALL" if score >= 72 else "PUT" if score <= 28 else "WAIT"
    return {"side":side, "score":score, "price":price, "ema6":e6, "ema12":e12, "ema50":e50, "rsi":rsi, "atr":atr, "rvol":rvol, "reason":"; ".join(reasons) or "mixed"}


def v9_backtest_symbol(symbol, period=None, interval=None):
    asset, data = v9_price_frame(symbol, period, interval)
    closes_all = [float(x) for x in data["Close"].tolist()]
    highs_all = [float(x) for x in data["High"].tolist()]
    lows_all = [float(x) for x in data["Low"].tolist()]
    vols_all = [float(x) for x in data["Volume"].fillna(0).tolist()]
    trades = []
    equity = V9_BACKTEST_INITIAL_CAPITAL
    peak = equity
    max_dd = 0.0
    position = None
    for i in range(60, len(closes_all)-1):
        closes, highs, lows, vols = closes_all[:i], highs_all[:i], lows_all[:i], vols_all[:i]
        sig = v9_point_signal(closes, highs, lows, vols)
        price = closes_all[i]
        next_price = closes_all[i+1]
        atr = sig.get("atr") or (price * 0.025)
        if position is None and sig["side"] in {"CALL", "PUT"}:
            side = "LONG" if sig["side"] == "CALL" else "SHORT"
            stop_dist = max(atr * 1.2, price * 0.01)
            risk_cash = equity * (V9_RISK_PER_TRADE_PCT / 100.0)
            qty_by_risk = risk_cash / stop_dist if stop_dist > 0 else 0
            qty_by_cap = (equity * V9_MAX_POSITION_PCT / 100.0) / price if price > 0 else 0
            qty = max(0, min(qty_by_risk, qty_by_cap))
            if qty > 0:
                position = {"side":side, "entry":price, "qty":qty, "score":sig["score"], "entry_i":i, "reason":sig["reason"]}
        elif position is not None:
            hold_days = i - position["entry_i"]
            side_mult = 1 if position["side"] == "LONG" else -1
            unreal = (price - position["entry"]) * side_mult / position["entry"]
            exit_now = False
            exit_reason = ""
            if unreal <= -0.035:
                exit_now = True; exit_reason = "stop"
            elif unreal >= 0.08:
                exit_now = True; exit_reason = "take_profit"
            elif hold_days >= 8:
                exit_now = True; exit_reason = "time_exit"
            elif (position["side"] == "LONG" and sig["side"] == "PUT") or (position["side"] == "SHORT" and sig["side"] == "CALL"):
                exit_now = True; exit_reason = "opposite_signal"
            if exit_now:
                pnl = (price - position["entry"]) * side_mult * position["qty"]
                equity += pnl
                peak = max(peak, equity)
                dd = (peak - equity) / peak * 100 if peak else 0
                max_dd = max(max_dd, dd)
                trades.append({"entry":position["entry"], "exit":price, "side":position["side"], "pnl":pnl, "pnl_pct":unreal*100, "days":hold_days, "exit_reason":exit_reason, "score":position["score"]})
                position = None
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    return {
        "symbol": symbol.upper(), "asset_type": asset["asset_type"], "period": period or V9_BACKTEST_PERIOD, "interval": interval or V9_BACKTEST_INTERVAL,
        "initial_capital": V9_BACKTEST_INITIAL_CAPITAL, "ending_equity": round(equity, 2), "return_pct": round((equity/V9_BACKTEST_INITIAL_CAPITAL-1)*100, 2),
        "trades": len(trades), "win_rate_pct": round(len(wins)/len(trades)*100, 2) if trades else 0,
        "profit_factor": round(gross_win/gross_loss, 2) if gross_loss else None,
        "max_drawdown_pct": round(max_dd, 2), "sample_trades": trades[-10:],
        "warning": "Backtest นี้เป็น daily-bar system simulation ไม่ใช่ fill จริง ไม่รวม slippage/commission/option spread"
    }


def v9_free_news_earnings_fallback(symbol):
    asset = normalize_asset(symbol)
    out = {"symbol": symbol.upper(), "news_source": "yfinance.news/free scrape fallback", "news": [], "earnings": None, "risk_flags": []}
    try:
        news = yf.Ticker(asset["yf_symbol"]).news or []
        for n in news[:6]:
            out["news"].append({"title": n.get("title"), "publisher": n.get("publisher"), "provider_publish_time": n.get("providerPublishTime"), "link": n.get("link")})
    except Exception as e:
        out["risk_flags"].append(f"news unavailable: {e}")
    try:
        cal = yf.Ticker(asset["yf_symbol"]).calendar
        if cal is not None:
            out["earnings"] = str(cal)
    except Exception as e:
        out["risk_flags"].append(f"earnings calendar unavailable: {e}")
    text = json.dumps(out, ensure_ascii=False).lower()
    for key in ["earnings", "guidance", "sec", "lawsuit", "downgrade", "investigation", "fed", "cpi", "fomc"]:
        if key in text:
            out["risk_flags"].append(f"keyword:{key}")
    if not out["news"]:
        out["risk_flags"].append("no free news returned; use technical-only mode")
    return out


def v9_sector_breadth():
    rows = []
    adv = dec = above_ema20 = above_ema50 = 0
    for s in V9_SECTOR_BREADTH_SYMBOLS:
        try:
            asset, data = v9_price_frame(s, period="3mo", interval="1d")
            closes = [float(x) for x in data["Close"].tolist()]
            chg = ((closes[-1] / closes[-2]) - 1) * 100 if len(closes) >= 2 and closes[-2] else 0
            e20, e50 = ema(closes, 20), ema(closes, 50)
            if chg > 0: adv += 1
            elif chg < 0: dec += 1
            if e20 and closes[-1] > e20: above_ema20 += 1
            if e50 and closes[-1] > e50: above_ema50 += 1
            rows.append({"symbol":s, "price":round(closes[-1],2), "change_pct":round(chg,2), "above_ema20":bool(e20 and closes[-1]>e20), "above_ema50":bool(e50 and closes[-1]>e50)})
        except Exception as e:
            rows.append({"symbol":s, "error":str(e)[:120]})
    valid = [r for r in rows if "error" not in r]
    n = len(valid) or 1
    score = int((adv/n)*40 + (above_ema20/n)*30 + (above_ema50/n)*30)
    regime = "RISK-ON" if score >= 65 else "RISK-OFF" if score <= 40 else "MIXED"
    return {"time_th": now_text(), "regime":regime, "breadth_score":score, "advancers":adv, "decliners":dec, "above_ema20_pct":round(above_ema20/n*100,2), "above_ema50_pct":round(above_ema50/n*100,2), "items":rows}


def v9_risk_engine(symbol, account_size=None, entry=None, stop=None):
    account_size = float(account_size or V9_BACKTEST_INITIAL_CAPITAL)
    asset, data = v9_price_frame(symbol, period="6mo", interval="1d")
    closes = [float(x) for x in data["Close"].tolist()]
    highs = [float(x) for x in data["High"].tolist()]
    lows = [float(x) for x in data["Low"].tolist()]
    price = float(entry or closes[-1])
    atr = calc_atr(highs, lows, closes, 14) or price * 0.025
    stop_price = float(stop) if stop else price - atr * 1.2
    risk_per_share = abs(price - stop_price)
    risk_cash = account_size * V9_RISK_PER_TRADE_PCT / 100.0
    qty_risk = risk_cash / risk_per_share if risk_per_share > 0 else 0
    qty_cap = (account_size * V9_MAX_POSITION_PCT / 100.0) / price if price > 0 else 0
    qty = int(max(0, min(qty_risk, qty_cap)))
    exposure = qty * price
    return {"symbol":symbol.upper(), "account_size":account_size, "entry":round(price,2), "atr14":round(atr,2), "suggested_stop":round(stop_price,2), "risk_per_trade_pct":V9_RISK_PER_TRADE_PCT, "risk_cash":round(risk_cash,2), "max_position_pct":V9_MAX_POSITION_PCT, "position_qty_underlying":qty, "estimated_exposure":round(exposure,2), "max_daily_loss_pct":V9_MAX_DAILY_LOSS_PCT, "max_open_positions":V9_MAX_OPEN_POSITIONS, "decision":"PASS" if qty>0 else "BLOCK", "note":"Risk Engine ใช้ ATR และ position sizing เชิงระบบ ไม่ใช่คำสั่งซื้อขายจริง"}


def v9_options_hybrid_sim(symbol, side=None, dte=None, iv=None):
    asset, data = v9_price_frame(symbol, period="6mo", interval="1d")
    closes = [float(x) for x in data["Close"].tolist()]
    highs = [float(x) for x in data["High"].tolist()]
    lows = [float(x) for x in data["Low"].tolist()]
    vols = [float(x) for x in data["Volume"].fillna(0).tolist()]
    sig = v9_point_signal(closes, highs, lows, vols)
    side = (side or sig["side"] or "CALL").upper()
    dte = int(dte or V9_OPTIONS_DTE)
    iv = float(iv or V9_OPTIONS_IV_FALLBACK)
    price = closes[-1]
    atr = sig.get("atr") or price * 0.025
    expected_move = price * iv * ((dte/365.0) ** 0.5)
    if side == "PUT":
        strike = round(price - expected_move * 0.35, 2)
        breakeven = round(strike - max(expected_move * 0.28, atr * 0.6), 2)
        invalid = round(price + atr * 0.9, 2)
    else:
        strike = round(price + expected_move * 0.35, 2)
        breakeven = round(strike + max(expected_move * 0.28, atr * 0.6), 2)
        invalid = round(price - atr * 0.9, 2)
    return {"symbol":symbol.upper(), "underlying_price":round(price,2), "system_side":side, "score":sig["score"], "dte":dte, "iv_used_fallback":iv, "expected_move":round(expected_move,2), "simulated_strike_zone":strike, "simulated_breakeven_zone":breakeven, "invalid_underlying_level":invalid, "atr14":round(atr,2), "strategy_bias":"debit option only when score extreme; otherwise wait/spread simulation", "warning":"Options Hybrid เป็นแบบจำลองจาก underlying/ATR/IV fallback ไม่ใช่ option chain จริงและไม่ใช่ราคา premium จริง"}


def v9_institutional_snapshot(symbol):
    asset = normalize_asset(symbol)
    quote, closes, highs, lows, opens, volumes = get_market_data(asset)
    analysis = analyze_signal(asset, quote, closes, highs, lows, opens, volumes)
    raw_side = signal_type_from_analysis(asset, analysis)
    backtest = v9_backtest_symbol(symbol)
    news = v9_free_news_earnings_fallback(symbol)
    breadth = v9_sector_breadth()
    risk = v9_risk_engine(symbol, entry=analysis.get("price"))
    opt = v9_options_hybrid_sim(symbol, side="CALL" if raw_side == "BUY" else "PUT" if raw_side == "SELL" else None)
    return {"version":"V9 Institutional Layer Free 100%", "symbol":symbol.upper(), "sector_group":V9_SECTOR_MAP.get(symbol.upper(), "UNMAPPED"), "technical":{"price":analysis.get("price"), "score":analysis.get("score"), "bias":analysis.get("bias"), "raw_signal":raw_side, "regime":analysis.get("regime"), "rvol":analysis.get("rvol")}, "backtest":backtest, "news_earnings_fallback":news, "sector_breadth":breadth, "risk_engine":risk, "options_hybrid_sim":opt, "final_note":"ฟรี 100% แต่ความแม่นขึ้นกับข้อมูล yfinance/free source; ใช้เป็น decision-support ไม่ใช่ execution system"}


@app.route("/v9-status", methods=["GET"])
def v9_status():
    return jsonify({"version":"V9 Institutional Layer Free 100%", "enabled":V9_ENABLED, "axes":["Backtest", "News/Earnings fallback", "Sector/Breadth", "Risk Engine", "Options Hybrid Sim"], "free_sources":["yfinance", "SQLite", "existing free fallbacks"], "routes":["/v9/<symbol>", "/v9/backtest/<symbol>", "/v9/news/<symbol>", "/v9/breadth", "/v9/risk/<symbol>", "/v9/options/<symbol>"]})


@app.route("/v9/<symbol>", methods=["GET"])
def v9_snapshot_route(symbol):
    return jsonify(v9_institutional_snapshot(symbol))


@app.route("/v9/backtest/<symbol>", methods=["GET"])
def v9_backtest_route(symbol):
    return jsonify(v9_backtest_symbol(symbol, request.args.get("period") or None, request.args.get("interval") or None))


@app.route("/v9/news/<symbol>", methods=["GET"])
def v9_news_route(symbol):
    return jsonify(v9_free_news_earnings_fallback(symbol))


@app.route("/v9/breadth", methods=["GET"])
def v9_breadth_route():
    return jsonify(v9_sector_breadth())


@app.route("/v9/risk/<symbol>", methods=["GET"])
def v9_risk_route(symbol):
    return jsonify(v9_risk_engine(symbol, request.args.get("account"), request.args.get("entry"), request.args.get("stop")))


@app.route("/v9/options/<symbol>", methods=["GET"])
def v9_options_route(symbol):
    return jsonify(v9_options_hybrid_sim(symbol, request.args.get("side"), request.args.get("dte"), request.args.get("iv")))



# ============================================================
# V10 ANALYST-GRADE LAYER FREE 100%
# Adds: Options Chain Lite, Signal Journal + Win Rate Tracker,
# True Market Breadth, Regime Filter, Explainable Score Breakdown
# ============================================================
import math

V10_ENABLED = os.getenv("V10_ENABLED", "true").lower() == "true"
V10_BREADTH_UNIVERSE = env_list(
    "V10_BREADTH_UNIVERSE",
    "AAPL,MSFT,NVDA,AMZN,META,GOOGL,AVGO,TSLA,COST,NFLX,AMD,ADBE,CRM,ORCL,INTC,CSCO,PEP,TMUS,LIN,AMGN,TXN,QCOM,INTU,AMAT,ISRG,BKNG,VRTX,REGN,ADP,MDLZ,LRCX,MU,PANW,KLAC,SNPS,CDNS,MELI,ADI,CRWD,MAR,ABNB,CSX,MRVL,PYPL,CHTR,WDAY,TEAM,SHOP,DDOG,QQQ,SPY,IWM,DIA"
)
V10_SECTOR_ETFS = env_list("V10_SECTOR_ETFS", "XLK,XLY,XLC,XLF,XLV,XLI,XLE,XLP,XLU,XLB,XLRE,SMH,SOXX")
V10_REGIME_SYMBOLS = env_list("V10_REGIME_SYMBOLS", "SPY,QQQ,IWM,DIA,TLT,UUP,GLD,XLK,XLF,XLE,XLV,SMH")
V10_RISK_FREE_RATE = float(os.getenv("V10_RISK_FREE_RATE", "0.045"))
V10_DEFAULT_DTE_MAX = int(os.getenv("V10_DEFAULT_DTE_MAX", "45"))
V10_MIN_OPTION_VOLUME = int(os.getenv("V10_MIN_OPTION_VOLUME", "10"))
V10_MIN_OPTION_OI = int(os.getenv("V10_MIN_OPTION_OI", "50"))
V10_MAX_SPREAD_PCT = float(os.getenv("V10_MAX_SPREAD_PCT", "25"))
V10_SIGNAL_FORWARD_BARS = int(os.getenv("V10_SIGNAL_FORWARD_BARS", "5"))


def v10_init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS v10_signal_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            price REAL,
            side TEXT,
            score INTEGER,
            regime TEXT,
            explanation TEXT,
            horizon_bars INTEGER,
            future_price REAL,
            result_pct REAL,
            win INTEGER
        )
    """)
    conn.commit()
    conn.close()


def _norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def v10_black_scholes_greeks(spot, strike, dte, iv, option_type="call", r=None):
    r = V10_RISK_FREE_RATE if r is None else float(r)
    spot = float(spot); strike = float(strike); iv = max(float(iv or 0.01), 0.01)
    t = max(float(dte), 1.0) / 365.0
    d1 = (math.log(spot / strike) + (r + 0.5 * iv * iv) * t) / (iv * math.sqrt(t))
    d2 = d1 - iv * math.sqrt(t)
    if option_type.lower().startswith("p"):
        price = strike * math.exp(-r * t) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)
        delta = _norm_cdf(d1) - 1
    else:
        price = spot * _norm_cdf(d1) - strike * math.exp(-r * t) * _norm_cdf(d2)
        delta = _norm_cdf(d1)
    gamma = _norm_pdf(d1) / (spot * iv * math.sqrt(t))
    theta = (-(spot * _norm_pdf(d1) * iv) / (2 * math.sqrt(t)))
    if option_type.lower().startswith("p"):
        theta += r * strike * math.exp(-r * t) * _norm_cdf(-d2)
    else:
        theta -= r * strike * math.exp(-r * t) * _norm_cdf(d2)
    theta = theta / 365.0
    vega = spot * _norm_pdf(d1) * math.sqrt(t) / 100.0
    return {"theoretical_price": round(price, 4), "delta": round(delta, 4), "gamma": round(gamma, 6), "theta_per_day": round(theta, 4), "vega_per_1pct": round(vega, 4)}


def v10_options_chain_lite(symbol, side=None, max_dte=None):
    asset = normalize_asset(symbol)
    yf_symbol = asset["yf_symbol"]
    tk = yf.Ticker(yf_symbol)
    hist = tk.history(period="5d", interval="1d")
    if hist is None or hist.empty:
        raise RuntimeError(f"No underlying price from yfinance for {symbol}")
    spot = float(hist["Close"].dropna().iloc[-1])
    expiries = list(getattr(tk, "options", []) or [])
    max_dte = int(max_dte or V10_DEFAULT_DTE_MAX)
    today = datetime.now(timezone.utc).date()
    usable = []
    for exp in expiries:
        try:
            dte = (datetime.strptime(exp, "%Y-%m-%d").date() - today).days
            if 1 <= dte <= max_dte:
                usable.append((exp, dte))
        except Exception:
            continue
    if not usable and expiries:
        try:
            exp = expiries[0]
            usable = [(exp, max(1, (datetime.strptime(exp, "%Y-%m-%d").date() - today).days))]
        except Exception:
            pass
    if not usable:
        return {"symbol": symbol.upper(), "underlying_price": round(spot, 2), "source": "yfinance option_chain", "available": False, "reason": "No option expirations returned by yfinance"}
    side = (side or "BOTH").upper()
    out_rows = []
    for exp, dte in usable[:3]:
        try:
            chain = tk.option_chain(exp)
            frames = []
            if side in {"CALL", "BOTH"}: frames.append(("CALL", chain.calls))
            if side in {"PUT", "BOTH"}: frames.append(("PUT", chain.puts))
            for opt_type, df in frames:
                if df is None or df.empty: continue
                df = df.copy()
                df["distance_pct"] = ((df["strike"] - spot).abs() / spot) * 100
                df = df.sort_values("distance_pct").head(12)
                for _, row in df.iterrows():
                    bid = float(row.get("bid") or 0); ask = float(row.get("ask") or 0)
                    mid = (bid + ask) / 2 if bid > 0 and ask > 0 else float(row.get("lastPrice") or 0)
                    spread_pct = ((ask - bid) / mid * 100) if mid and bid > 0 and ask > 0 else None
                    iv = float(row.get("impliedVolatility") or 0)
                    greeks = v10_black_scholes_greeks(spot, float(row.get("strike")), dte, iv if iv > 0 else V9_OPTIONS_IV_FALLBACK, opt_type.lower())
                    oi = int(row.get("openInterest") or 0); vol = int(row.get("volume") or 0)
                    quality = 0
                    if oi >= V10_MIN_OPTION_OI: quality += 30
                    if vol >= V10_MIN_OPTION_VOLUME: quality += 25
                    if spread_pct is not None and spread_pct <= V10_MAX_SPREAD_PCT: quality += 25
                    if 0.25 <= abs(greeks.get("delta", 0)) <= 0.65: quality += 20
                    out_rows.append({
                        "expiration": exp, "dte": dte, "type": opt_type, "contractSymbol": row.get("contractSymbol"),
                        "strike": round(float(row.get("strike")), 2), "last": round(float(row.get("lastPrice") or 0), 2),
                        "bid": round(bid, 2), "ask": round(ask, 2), "mid": round(mid, 2),
                        "spread_pct": round(spread_pct, 2) if spread_pct is not None else None,
                        "volume": vol, "open_interest": oi, "iv": round(iv, 4),
                        "moneyness_pct": round((float(row.get("strike")) / spot - 1) * 100, 2),
                        "liquidity_quality_score": quality, **greeks
                    })
        except Exception as e:
            out_rows.append({"expiration": exp, "error": str(e)[:160]})
    clean = [r for r in out_rows if "error" not in r]
    clean = sorted(clean, key=lambda r: (-(r.get("liquidity_quality_score") or 0), abs(r.get("moneyness_pct") or 99), r.get("dte", 999)))[:30]
    return {"symbol": symbol.upper(), "underlying_price": round(spot, 2), "source": "yfinance option_chain + local Black-Scholes greeks", "available": bool(clean), "max_dte": max_dte, "filters": {"min_volume": V10_MIN_OPTION_VOLUME, "min_open_interest": V10_MIN_OPTION_OI, "max_spread_pct": V10_MAX_SPREAD_PCT}, "contracts": clean, "warning": "ข้อมูล option จาก yfinance อาจ delay/incomplete; ใช้คัดกรอง ไม่ใช่ execution price"}


def v10_true_market_breadth(universe=None):
    symbols = universe or V10_BREADTH_UNIVERSE
    rows = []
    adv = dec = above20 = above50 = above200 = new20h = new20l = 0
    for s in symbols:
        try:
            asset, data = v9_price_frame(s, period="1y", interval="1d")
            closes = [float(x) for x in data["Close"].dropna().tolist()]
            if len(closes) < 60:
                rows.append({"symbol": s, "error": "not enough history"}); continue
            price = closes[-1]
            chg = (price / closes[-2] - 1) * 100 if closes[-2] else 0
            e20, e50, e200 = ema(closes, 20), ema(closes, 50), ema(closes, 200)
            is_adv = chg > 0; is_dec = chg < 0
            if is_adv: adv += 1
            if is_dec: dec += 1
            if e20 and price > e20: above20 += 1
            if e50 and price > e50: above50 += 1
            if e200 and price > e200: above200 += 1
            if price >= max(closes[-20:]): new20h += 1
            if price <= min(closes[-20:]): new20l += 1
            rows.append({"symbol": s, "price": round(price, 2), "change_pct": round(chg, 2), "above_ema20": bool(e20 and price > e20), "above_ema50": bool(e50 and price > e50), "above_ema200": bool(e200 and price > e200), "new_20d_high": price >= max(closes[-20:]), "new_20d_low": price <= min(closes[-20:])})
        except Exception as e:
            rows.append({"symbol": s, "error": str(e)[:120]})
    valid = [r for r in rows if "error" not in r]
    n = max(len(valid), 1)
    breadth_score = int((adv/n)*25 + (above20/n)*25 + (above50/n)*25 + (above200/n)*25)
    thrust = "BULLISH_BREADTH" if breadth_score >= 65 and adv > dec else "BEARISH_BREADTH" if breadth_score <= 40 or dec > adv*1.5 else "MIXED_BREADTH"
    return {"time_th": now_text(), "universe_size": len(symbols), "valid_symbols": len(valid), "breadth_score": breadth_score, "breadth_regime": thrust, "advancers": adv, "decliners": dec, "advance_decline_ratio": round(adv / max(dec, 1), 2), "above_ema20_pct": round(above20/n*100, 2), "above_ema50_pct": round(above50/n*100, 2), "above_ema200_pct": round(above200/n*100, 2), "new_20d_highs": new20h, "new_20d_lows": new20l, "items": rows[:200], "warning": "True breadth แบบฟรีใช้ universe ที่กำหนดเอง ไม่ใช่หุ้นทั้งตลาด 100%"}


def v10_regime_filter():
    detail = []
    score = 50
    for s in V10_REGIME_SYMBOLS:
        try:
            asset, data = v9_price_frame(s, period="1y", interval="1d")
            closes = [float(x) for x in data["Close"].dropna().tolist()]
            if len(closes) < 60: continue
            price = closes[-1]; e20, e50, e200 = ema(closes, 20), ema(closes, 50), ema(closes, 200)
            chg20 = (price / closes[-21] - 1) * 100 if len(closes) > 21 and closes[-21] else 0
            points = 0
            if e20 and price > e20: points += 1
            if e50 and price > e50: points += 1
            if e200 and price > e200: points += 1
            if chg20 > 0: points += 1
            weight = 1.5 if s in {"SPY", "QQQ"} else 1.0
            if s in {"TLT", "GLD"}: weight = 0.6
            score += (points - 2) * 3 * weight
            detail.append({"symbol": s, "price": round(price, 2), "above_ema20": bool(e20 and price>e20), "above_ema50": bool(e50 and price>e50), "above_ema200": bool(e200 and price>e200), "chg_20d_pct": round(chg20, 2), "points": points})
        except Exception as e:
            detail.append({"symbol": s, "error": str(e)[:120]})
    breadth = v10_true_market_breadth(V10_BREADTH_UNIVERSE[:30])
    score = int(max(0, min(100, score + (breadth["breadth_score"] - 50) * 0.4)))
    if score >= 70:
        regime = "RISK_ON_TREND"
        instruction = "CALL bias allowed; pullback entries preferred; avoid late chase."
    elif score <= 35:
        regime = "RISK_OFF_DEFENSIVE"
        instruction = "Reduce size; PUT/hedge bias only after confirmation; avoid weak liquidity."
    else:
        regime = "MIXED_CHOP"
        instruction = "Use smaller size; require VWAP/EMA confirmation; avoid marginal signals."
    return {"time_th": now_text(), "regime_score": score, "regime": regime, "trade_instruction": instruction, "breadth_summary": {k: breadth[k] for k in ["breadth_score", "breadth_regime", "advancers", "decliners", "above_ema50_pct", "above_ema200_pct"]}, "components": detail}


def v10_explainable_score(symbol):
    asset = normalize_asset(symbol)
    quote, closes, highs, lows, opens, volumes = get_market_data(asset)
    analysis = analyze_signal(asset, quote, closes, highs, lows, opens, volumes)
    price = float(analysis.get("price") or quote.get("price") or closes[-1])
    e6, e12, e20, e50 = ema(closes, 6), ema(closes, 12), ema(closes, 20), ema(closes, 50)
    rsi14 = calc_rsi(closes, 14)
    atr14 = calc_atr(highs, lows, closes, 14)
    avg_vol20 = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else 0
    rvol = (volumes[-1] / avg_vol20) if avg_vol20 else 0
    regime = v10_regime_filter()
    components = []
    def add(name, points, max_points, reason):
        components.append({"factor": name, "points": round(points, 2), "max_points": max_points, "reason": reason})
    trend_points = 0
    if e6 and e12 and e6 > e12: trend_points += 8
    if e20 and price > e20: trend_points += 6
    if e50 and price > e50: trend_points += 6
    add("trend_structure", trend_points, 20, f"EMA6/12/20/50 structure; price={round(price,2)}")
    mom_points = 0
    if rsi14 is not None:
        if 52 <= rsi14 <= 68: mom_points = 15
        elif 45 <= rsi14 < 52 or 68 < rsi14 <= 75: mom_points = 8
        elif rsi14 < 35: mom_points = -8
    add("momentum_rsi", mom_points, 15, f"RSI14={round(rsi14,2) if rsi14 is not None else None}")
    vol_points = 15 if rvol >= 1.5 else 10 if rvol >= 1.0 else 3 if rvol >= 0.7 else -5
    add("volume_confirmation", vol_points, 15, f"Relative volume approx={round(rvol,2)}")
    regime_points = 15 if regime["regime_score"] >= 70 else 5 if regime["regime_score"] >= 45 else -10
    add("market_regime", regime_points, 15, f"{regime['regime']} score={regime['regime_score']}")
    risk_points = 0
    if atr14 and price:
        atr_pct = atr14 / price * 100
        risk_points = 10 if atr_pct <= 4 else 5 if atr_pct <= 7 else -5
        risk_reason = f"ATR14%={round(atr_pct,2)}"
    else:
        risk_reason = "ATR unavailable"
    add("risk_volatility", risk_points, 10, risk_reason)
    opt_quality = 0; opt_note = "Not checked"
    try:
        chain = v10_options_chain_lite(symbol, side="BOTH", max_dte=35)
        contracts = chain.get("contracts") or []
        best = contracts[0] if contracts else None
        if best:
            opt_quality = min(10, (best.get("liquidity_quality_score") or 0) / 10)
            opt_note = f"Best contract quality={best.get('liquidity_quality_score')} spread={best.get('spread_pct')}% OI={best.get('open_interest')} Vol={best.get('volume')}"
        else:
            opt_quality = -3; opt_note = chain.get("reason", "No liquid chain")
    except Exception as e:
        opt_quality = -3; opt_note = f"Options unavailable: {str(e)[:80]}"
    add("options_liquidity_lite", opt_quality, 10, opt_note)
    raw_score = sum(c["points"] for c in components)
    normalized = int(max(0, min(100, 50 + raw_score)))
    if normalized >= 78:
        decision = "STRONG_CALL_WATCH" if trend_points >= 10 else "CALL_WATCH_WITH_CAUTION"
    elif normalized <= 30:
        decision = "PUT_OR_AVOID_WEAKNESS"
    else:
        decision = "WAIT_CONFIRMATION"
    explanation = {
        "symbol": symbol.upper(), "price": round(price, 2), "final_score": normalized,
        "decision": decision, "components": components,
        "regime": {"score": regime["regime_score"], "label": regime["regime"], "instruction": regime["trade_instruction"]},
        "technical_raw": {"existing_score": analysis.get("score"), "existing_bias": analysis.get("bias"), "rvol": analysis.get("rvol")},
        "note": "คะแนนอธิบายได้ ใช้เป็นตัวกรอง ไม่ใช่คำสั่งซื้อขาย"
    }
    return explanation


def v10_log_signal(symbol):
    ex = v10_explainable_score(symbol)
    side = "CALL" if "CALL" in ex["decision"] else "PUT" if "PUT" in ex["decision"] else "WAIT"
    conn = db()
    conn.execute("""
        INSERT INTO v10_signal_journal(created_at, symbol, price, side, score, regime, explanation, horizon_bars)
        VALUES(?,?,?,?,?,?,?,?)
    """, (datetime.now(timezone.utc).isoformat(), symbol.upper(), ex["price"], side, ex["final_score"], ex["regime"]["label"], json.dumps(ex, ensure_ascii=False), V10_SIGNAL_FORWARD_BARS))
    conn.commit(); conn.close()
    return {"logged": True, "signal": ex}


def v10_update_journal_results():
    conn = db(); cur = conn.cursor()
    rows = cur.execute("SELECT * FROM v10_signal_journal WHERE future_price IS NULL ORDER BY id ASC LIMIT 100").fetchall()
    updated = 0
    for r in rows:
        try:
            created = datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            min_age = timedelta(days=max(1, int(r["horizon_bars"] or V10_SIGNAL_FORWARD_BARS)))
            if datetime.now(timezone.utc) - created < min_age:
                continue
            asset, data = v9_price_frame(r["symbol"], period="2mo", interval="1d")
            closes = [float(x) for x in data["Close"].dropna().tolist()]
            if len(closes) <= V10_SIGNAL_FORWARD_BARS: continue
            future = closes[-1]
            entry = float(r["price"] or 0)
            if not entry: continue
            pct = (future / entry - 1) * 100
            side = (r["side"] or "WAIT").upper()
            win = 1 if (side == "CALL" and pct > 0) or (side == "PUT" and pct < 0) else 0 if side in {"CALL","PUT"} else None
            cur.execute("UPDATE v10_signal_journal SET future_price=?, result_pct=?, win=? WHERE id=?", (future, pct, win, r["id"]))
            updated += 1
        except Exception:
            continue
    conn.commit(); conn.close()
    return updated


def v10_journal_stats(symbol=None):
    updated = v10_update_journal_results()
    conn = db(); cur = conn.cursor()
    params = []
    where = "WHERE side IN ('CALL','PUT') AND win IS NOT NULL"
    if symbol:
        where += " AND symbol=?"; params.append(symbol.upper())
    rows = cur.execute(f"SELECT * FROM v10_signal_journal {where} ORDER BY id DESC LIMIT 500", params).fetchall()
    total = len(rows); wins = sum(1 for r in rows if r["win"] == 1)
    avg_pct = sum(float(r["result_pct"] or 0) for r in rows) / total if total else 0
    by_side = {}
    for side in ["CALL", "PUT"]:
        sr = [r for r in rows if r["side"] == side]
        by_side[side] = {"trades": len(sr), "win_rate_pct": round(sum(1 for r in sr if r["win"] == 1)/len(sr)*100,2) if sr else 0, "avg_result_pct": round(sum(float(r["result_pct"] or 0) for r in sr)/len(sr),2) if sr else 0}
    latest = cur.execute("SELECT id, created_at, symbol, price, side, score, regime, future_price, result_pct, win FROM v10_signal_journal ORDER BY id DESC LIMIT 30").fetchall()
    conn.close()
    return {"updated_results": updated, "symbol_filter": symbol.upper() if symbol else None, "closed_signals": total, "overall_win_rate_pct": round(wins/total*100,2) if total else 0, "avg_result_pct": round(avg_pct,2), "by_side": by_side, "latest": [dict(r) for r in latest], "warning": "สถิติจะน่าเชื่อถือเมื่อมี signal journal จำนวนมากและครบ horizon แล้ว"}


def v10_analyst_snapshot(symbol):
    return {
        "version": "V10 Analyst-Grade Layer Free 100%",
        "symbol": symbol.upper(),
        "explainable_score": v10_explainable_score(symbol),
        "options_chain_lite": v10_options_chain_lite(symbol),
        "regime_filter": v10_regime_filter(),
        "true_market_breadth": v10_true_market_breadth(),
        "journal_stats": v10_journal_stats(symbol),
        "final_note": "V10 เพิ่มความเป็น analyst-grade แต่ยังเป็นระบบฟรี/ข้อมูล delay/incomplete ได้ ไม่ใช่ institutional terminal จริง"
    }


@app.route("/v10-status", methods=["GET"])
def v10_status():
    return jsonify({"version": "V10 Analyst-Grade Layer Free 100%", "enabled": V10_ENABLED, "axes": ["Options Chain Lite from yfinance", "Signal Journal + Win Rate Tracker", "True Market Breadth", "Regime Filter", "Explainable Score Breakdown"], "routes": ["/v10/<symbol>", "/v10/options/<symbol>", "/v10/journal", "/v10/journal/log/<symbol>", "/v10/breadth", "/v10/regime", "/v10/explain/<symbol>"]})


@app.route("/v10/<symbol>", methods=["GET"])
def v10_snapshot_route(symbol):
    return jsonify(v10_analyst_snapshot(symbol))


@app.route("/v10/options/<symbol>", methods=["GET"])
def v10_options_route(symbol):
    return jsonify(v10_options_chain_lite(symbol, request.args.get("side"), request.args.get("max_dte")))


@app.route("/v10/journal", methods=["GET"])
def v10_journal_route():
    return jsonify(v10_journal_stats(request.args.get("symbol")))


@app.route("/v10/journal/log/<symbol>", methods=["GET", "POST"])
def v10_journal_log_route(symbol):
    return jsonify(v10_log_signal(symbol))


@app.route("/v10/breadth", methods=["GET"])
def v10_breadth_route():
    return jsonify(v10_true_market_breadth())


@app.route("/v10/regime", methods=["GET"])
def v10_regime_route():
    return jsonify(v10_regime_filter())


@app.route("/v10/explain/<symbol>", methods=["GET"])
def v10_explain_route(symbol):
    return jsonify(v10_explainable_score(symbol))


# ============================================================
# V11 INSTITUTIONAL PLUS LAYER - FREE 100%
# Adds: historical winrate journal, portfolio risk, multi-factor regime,
# unusual options activity, performance dashboard.
# ============================================================
V11_ENABLED = os.getenv("V11_ENABLED", "true").lower() == "true"
V11_DASHBOARD_UNIVERSE = env_list("V11_DASHBOARD_UNIVERSE", "NVDA,AAPL,TSLA,AMD,MSFT,META,QQQ,SPY,PLTR,AVGO,SMH,IWM")
V11_PORTFOLIO_POSITIONS = os.getenv("V11_PORTFOLIO_POSITIONS", "")  # Example: NVDA:1000,AAPL:800,QQQ:1200
V11_MAX_SYMBOL_RISK_PCT = float(os.getenv("V11_MAX_SYMBOL_RISK_PCT", "8"))
V11_MAX_PORTFOLIO_RISK_PCT = float(os.getenv("V11_MAX_PORTFOLIO_RISK_PCT", "25"))
V11_SIGNAL_HORIZON_DAYS = int(os.getenv("V11_SIGNAL_HORIZON_DAYS", "5"))


def v11_init_db():
    conn = db(); cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS v11_signal_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT,
            entry_price REAL,
            score INTEGER,
            regime TEXT,
            reason TEXT,
            horizon_days INTEGER,
            exit_price REAL,
            result_pct REAL,
            win INTEGER
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS v11_portfolio_positions (
            symbol TEXT PRIMARY KEY,
            market_value REAL NOT NULL DEFAULT 0,
            side TEXT NOT NULL DEFAULT 'LONG',
            risk_pct REAL NOT NULL DEFAULT 5,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit(); conn.close()


def v11_download(symbol, period="1y", interval="1d"):
    try:
        df = yf.download(symbol.upper(), period=period, interval=interval, progress=False, auto_adjust=True)
        if df is None or len(df) == 0:
            return None
        return df.dropna()
    except Exception as e:
        print("v11_download error", symbol, e)
        return None


def v11_last_close(symbol):
    df = v11_download(symbol, period="10d", interval="1d")
    if df is None or len(df) == 0:
        return None
    try:
        return float(df["Close"].iloc[-1])
    except Exception:
        return None


def v11_historical_signal_winrate(symbol, period="1y", horizon_days=None):
    """Simple free historical signal test. Not a full backtest: no slippage/fees/options pricing."""
    horizon_days = int(horizon_days or V11_SIGNAL_HORIZON_DAYS)
    sym = symbol.upper()
    df = v11_download(sym, period=period, interval="1d")
    if df is None or len(df) < 80:
        return {"symbol": sym, "error": "not enough historical data from yfinance"}
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    ema20 = close.ewm(span=20).mean()
    ema50 = close.ewm(span=50).mean()
    ret5 = close.pct_change(5)
    rng = ((high - low) / close).rolling(14).mean()
    signals = []
    # Skip recent bars that do not have future outcome yet.
    for i in range(60, len(df) - horizon_days):
        side = None
        score = 50
        reasons = []
        if close.iloc[i] > ema20.iloc[i] > ema50.iloc[i] and ret5.iloc[i] > 0.015:
            side = "CALL"; score += 25; reasons.append("price>EMA20>EMA50 and 5d momentum positive")
        elif close.iloc[i] < ema20.iloc[i] < ema50.iloc[i] and ret5.iloc[i] < -0.015:
            side = "PUT"; score -= 25; reasons.append("price<EMA20<EMA50 and 5d momentum negative")
        if side is None:
            continue
        if float(rng.iloc[i] or 0) > 0.045:
            reasons.append("high volatility regime")
        entry = float(close.iloc[i])
        exitp = float(close.iloc[i + horizon_days])
        result_pct = (exitp - entry) / entry * 100
        if side == "PUT":
            result_pct = -result_pct
        win = 1 if result_pct > 0 else 0
        signals.append({
            "date": str(df.index[i].date()), "side": side, "entry": round(entry, 4), "exit": round(exitp, 4),
            "result_pct": round(result_pct, 2), "win": win, "score": score, "reason": "; ".join(reasons)
        })
    total = len(signals)
    wins = sum(s["win"] for s in signals)
    avg = sum(s["result_pct"] for s in signals) / total if total else 0
    by_side = {}
    for side in ["CALL", "PUT"]:
        rows = [s for s in signals if s["side"] == side]
        by_side[side] = {
            "signals": len(rows),
            "win_rate_pct": round(sum(s["win"] for s in rows) / len(rows) * 100, 2) if rows else 0,
            "avg_result_pct": round(sum(s["result_pct"] for s in rows) / len(rows), 2) if rows else 0,
        }
    return {
        "symbol": sym,
        "period": period,
        "horizon_days": horizon_days,
        "closed_historical_signals": total,
        "win_rate_pct": round(wins / total * 100, 2) if total else 0,
        "avg_result_pct": round(avg, 2),
        "by_side": by_side,
        "latest_sample": signals[-20:],
        "limitation": "Free historical proxy: tests underlying movement only, not real option fills, bid/ask, IV crush, slippage or commissions."
    }


def v11_log_current_signal(symbol):
    sym = symbol.upper()
    ex = v10_explainable_score(sym)
    price = None
    try:
        price = float(ex.get("price")) if ex.get("price") is not None else v11_last_close(sym)
    except Exception:
        price = v11_last_close(sym)
    decision = str(ex.get("decision", "HOLD"))
    side = "CALL" if "CALL" in decision else "PUT" if "PUT" in decision else "WATCH"
    conn = db(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO v11_signal_journal(created_at, symbol, side, entry_price, score, regime, reason, horizon_days)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (now_text(), sym, side, price, int(ex.get("final_score", 50)), str(ex.get("regime", {}).get("regime", "UNKNOWN")), json.dumps(ex, ensure_ascii=False)[:4500], V11_SIGNAL_HORIZON_DAYS))
    conn.commit(); conn.close()
    return {"logged": True, "symbol": sym, "side": side, "entry_price": price, "score": ex.get("final_score"), "horizon_days": V11_SIGNAL_HORIZON_DAYS}


def v11_update_journal_results():
    conn = db(); cur = conn.cursor()
    rows = cur.execute("SELECT * FROM v11_signal_journal WHERE exit_price IS NULL ORDER BY id ASC LIMIT 200").fetchall()
    updated = 0
    for r in rows:
        try:
            created = datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00"))
        except Exception:
            continue
        if datetime.now(timezone.utc) - created.replace(tzinfo=timezone.utc) < timedelta(days=int(r["horizon_days"] or V11_SIGNAL_HORIZON_DAYS)):
            continue
        price = v11_last_close(r["symbol"])
        if not price or not r["entry_price"]:
            continue
        pct = (price - float(r["entry_price"])) / float(r["entry_price"]) * 100
        if r["side"] == "PUT":
            pct = -pct
        win = 1 if pct > 0 else 0
        cur.execute("UPDATE v11_signal_journal SET exit_price=?, result_pct=?, win=? WHERE id=?", (price, pct, win, r["id"]))
        updated += 1
    conn.commit(); conn.close()
    return updated


def v11_journal_stats(symbol=None):
    updated = v11_update_journal_results()
    conn = db(); cur = conn.cursor()
    params = []
    where = "WHERE win IS NOT NULL AND side IN ('CALL','PUT')"
    if symbol:
        where += " AND symbol=?"; params.append(symbol.upper())
    rows = cur.execute(f"SELECT * FROM v11_signal_journal {where} ORDER BY id DESC LIMIT 1000", params).fetchall()
    latest = cur.execute("SELECT id, created_at, symbol, side, entry_price, score, regime, exit_price, result_pct, win FROM v11_signal_journal ORDER BY id DESC LIMIT 50").fetchall()
    conn.close()
    total = len(rows); wins = sum(1 for r in rows if r["win"] == 1)
    avg = sum(float(r["result_pct"] or 0) for r in rows) / total if total else 0
    return {
        "updated_results": updated,
        "symbol_filter": symbol.upper() if symbol else None,
        "closed_signals": total,
        "win_rate_pct": round(wins / total * 100, 2) if total else 0,
        "avg_result_pct": round(avg, 2),
        "latest": [dict(r) for r in latest],
        "note": "Use /v11/journal/log/<symbol> to log a live signal; /v11/historical/<symbol> gives immediate historical proxy stats."
    }


def v11_parse_portfolio_env():
    positions = []
    raw = V11_PORTFOLIO_POSITIONS.strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                for p in data:
                    positions.append({"symbol": str(p.get("symbol", "")).upper(), "market_value": float(p.get("market_value", 0)), "side": str(p.get("side", "LONG")).upper(), "risk_pct": float(p.get("risk_pct", 5))})
                return [p for p in positions if p["symbol"]]
        except Exception:
            pass
        for part in raw.split(","):
            if ":" in part:
                s, v = part.split(":", 1)
                try:
                    positions.append({"symbol": s.strip().upper(), "market_value": float(v), "side": "LONG", "risk_pct": 5.0})
                except Exception:
                    pass
    if not positions:
        for s in V11_DASHBOARD_UNIVERSE[:6]:
            positions.append({"symbol": s, "market_value": 1000.0, "side": "LONG", "risk_pct": 5.0})
    return positions


def v11_portfolio_risk_engine():
    positions = v11_parse_portfolio_env()
    total_value = sum(abs(float(p.get("market_value", 0))) for p in positions)
    rows = []
    risk_dollars_total = 0
    sector_proxy = {"NVDA":"AI_SEMI", "AMD":"AI_SEMI", "AVGO":"AI_SEMI", "SMH":"AI_SEMI", "AAPL":"MEGA_TECH", "MSFT":"MEGA_TECH", "META":"MEGA_TECH", "GOOGL":"MEGA_TECH", "AMZN":"MEGA_TECH", "TSLA":"HIGH_BETA", "PLTR":"HIGH_BETA", "QQQ":"INDEX", "SPY":"INDEX", "IWM":"SMALL_CAP"}
    buckets = {}
    for p in positions:
        sym = p["symbol"]
        mv = float(p.get("market_value", 0))
        risk_pct = float(p.get("risk_pct", 5))
        risk_dollars = abs(mv) * risk_pct / 100
        risk_dollars_total += risk_dollars
        weight = abs(mv) / total_value * 100 if total_value else 0
        bucket = sector_proxy.get(sym, "OTHER")
        buckets[bucket] = buckets.get(bucket, 0) + weight
        rows.append({"symbol": sym, "market_value": mv, "side": p.get("side", "LONG"), "weight_pct": round(weight, 2), "risk_pct": risk_pct, "risk_dollars": round(risk_dollars, 2), "bucket": bucket})
    max_weight = max([r["weight_pct"] for r in rows], default=0)
    concentration = "HIGH" if max_weight > 35 or any(v > 55 for v in buckets.values()) else "MEDIUM" if max_weight > 20 or any(v > 40 for v in buckets.values()) else "LOW"
    portfolio_risk_pct = risk_dollars_total / total_value * 100 if total_value else 0
    allowed = portfolio_risk_pct <= V11_MAX_PORTFOLIO_RISK_PCT and max_weight <= 40
    return {
        "portfolio_value": round(total_value, 2),
        "estimated_risk_dollars": round(risk_dollars_total, 2),
        "estimated_risk_pct": round(portfolio_risk_pct, 2),
        "max_single_position_weight_pct": round(max_weight, 2),
        "concentration_level": concentration,
        "bucket_exposure_pct": {k: round(v, 2) for k, v in buckets.items()},
        "positions": rows,
        "risk_action": "ALLOW_NEW_RISK" if allowed else "REDUCE_SIZE_OR_SKIP_NEW_TRADES",
        "limits": {"max_portfolio_risk_pct": V11_MAX_PORTFOLIO_RISK_PCT, "max_symbol_risk_pct": V11_MAX_SYMBOL_RISK_PCT},
        "note": "Set V11_PORTFOLIO_POSITIONS='NVDA:2000,AAPL:1000,QQQ:1500' or JSON list in Railway Variables for real portfolio sizing."
    }


def v11_market_regime_multidim():
    inputs = {}
    def get_ret(sym, period="3mo"):
        df = v11_download(sym, period=period, interval="1d")
        if df is None or len(df) < 25:
            return None
        close = df["Close"]
        return {
            "last": round(float(close.iloc[-1]), 4),
            "ret_5d_pct": round((float(close.iloc[-1]) / float(close.iloc[-6]) - 1) * 100, 2) if len(close) > 6 else None,
            "ret_20d_pct": round((float(close.iloc[-1]) / float(close.iloc[-21]) - 1) * 100, 2) if len(close) > 21 else None,
            "above_ema20": bool(float(close.iloc[-1]) > float(close.ewm(span=20).mean().iloc[-1])),
            "above_ema50": bool(float(close.iloc[-1]) > float(close.ewm(span=50).mean().iloc[-1])) if len(close) > 50 else None,
        }
    symbols = {"SPY":"SPY", "QQQ":"QQQ", "IWM":"IWM", "VIX":"^VIX", "TNX_10Y_YIELD":"^TNX", "DOLLAR_PROXY":"DX-Y.NYB", "SMH":"SMH", "XLF":"XLF", "XLE":"XLE", "XLV":"XLV", "XLY":"XLY", "XLP":"XLP", "XLU":"XLU"}
    for k, sym in symbols.items():
        inputs[k] = get_ret(sym)
        if inputs[k] is None and k == "DOLLAR_PROXY":
            inputs[k] = get_ret("UUP")
    score = 50; reasons = []
    spy = inputs.get("SPY") or {}; qqq = inputs.get("QQQ") or {}; iwm = inputs.get("IWM") or {}; vix = inputs.get("VIX") or {}; tnx = inputs.get("TNX_10Y_YIELD") or {}; dollar = inputs.get("DOLLAR_PROXY") or {}
    if spy.get("above_ema20") and qqq.get("above_ema20"):
        score += 12; reasons.append("SPY and QQQ above EMA20")
    if spy.get("above_ema50") and qqq.get("above_ema50"):
        score += 10; reasons.append("SPY and QQQ above EMA50")
    if (vix.get("ret_5d_pct") or 0) > 10:
        score -= 14; reasons.append("VIX rising fast")
    elif (vix.get("ret_5d_pct") or 0) < -5:
        score += 6; reasons.append("VIX cooling")
    if (tnx.get("ret_20d_pct") or 0) > 6:
        score -= 7; reasons.append("10Y yield pressure rising")
    if (dollar.get("ret_20d_pct") or 0) > 3:
        score -= 5; reasons.append("Dollar proxy rising")
    if (iwm.get("ret_20d_pct") or -999) > (spy.get("ret_20d_pct") or 999):
        score += 6; reasons.append("Small caps outperform SPY")
    # Sector rotation scoring
    sector_keys = ["SMH","XLF","XLE","XLV","XLY","XLP","XLU"]
    sector_momentum = {k: (inputs.get(k) or {}).get("ret_20d_pct") for k in sector_keys}
    leadership = sorted([(k, v) for k, v in sector_momentum.items() if v is not None], key=lambda x: x[1], reverse=True)
    if leadership and leadership[0][0] in ["SMH", "XLY"]:
        score += 8; reasons.append("growth/risk-on sector leadership")
    if leadership and leadership[0][0] in ["XLU", "XLP", "XLV"]:
        score -= 6; reasons.append("defensive sector leadership")
    score = max(0, min(100, score))
    if score >= 75:
        regime = "RISK_ON_MULTI_FACTOR"
    elif score <= 35:
        regime = "RISK_OFF_MULTI_FACTOR"
    else:
        regime = "MIXED_MULTI_FACTOR"
    return {"regime": regime, "score": score, "reasons": reasons, "inputs": inputs, "sector_leadership_20d": leadership, "trade_instruction": "CALL bias allowed; avoid chasing" if score >= 65 else "Reduce size / wait for confirmation" if score <= 45 else "Mixed: trade only high quality setups"}


def v11_option_flow_unusual(symbol):
    sym = symbol.upper()
    try:
        t = yf.Ticker(sym)
        expiries = list(t.options or [])[:4]
        if not expiries:
            return {"symbol": sym, "error": "no options expirations from yfinance"}
        rows = []
        for exp in expiries:
            chain = t.option_chain(exp)
            for typ, df in [("CALL", chain.calls), ("PUT", chain.puts)]:
                if df is None or len(df) == 0:
                    continue
                for _, r in df.iterrows():
                    vol = int(r.get("volume") or 0)
                    oi = int(r.get("openInterest") or 0)
                    bid = float(r.get("bid") or 0); ask = float(r.get("ask") or 0); last = float(r.get("lastPrice") or 0)
                    if vol <= 0 and oi <= 0:
                        continue
                    spread = ask - bid if ask and bid else None
                    mid = (ask + bid) / 2 if ask and bid else last
                    unusual_score = 0
                    flags = []
                    if oi > 0 and vol / max(oi, 1) >= 0.5:
                        unusual_score += 35; flags.append("volume/OI >= 0.5")
                    if vol >= 1000:
                        unusual_score += 25; flags.append("volume >= 1000")
                    if oi >= 5000:
                        unusual_score += 15; flags.append("large open interest")
                    if spread is not None and mid and spread / max(mid, 0.01) <= 0.12:
                        unusual_score += 10; flags.append("tight spread")
                    if unusual_score >= 30:
                        rows.append({"contractSymbol": r.get("contractSymbol"), "type": typ, "expiration": exp, "strike": float(r.get("strike") or 0), "last": last, "bid": bid, "ask": ask, "volume": vol, "openInterest": oi, "vol_oi_ratio": round(vol / max(oi, 1), 2), "impliedVolatility": round(float(r.get("impliedVolatility") or 0), 4), "unusual_score": min(100, unusual_score), "flags": flags})
        rows = sorted(rows, key=lambda x: (x["unusual_score"], x["volume"]), reverse=True)[:40]
        call_count = sum(1 for r in rows if r["type"] == "CALL"); put_count = sum(1 for r in rows if r["type"] == "PUT")
        bias = "CALL_FLOW" if call_count > put_count * 1.3 else "PUT_FLOW" if put_count > call_count * 1.3 else "MIXED_FLOW"
        return {"symbol": sym, "bias": bias, "unusual_contracts": rows, "summary": {"count": len(rows), "calls": call_count, "puts": put_count}, "limitation": "Free yfinance chain can be delayed/incomplete; this is unusual activity proxy, not paid order-flow tape."}
    except Exception as e:
        return {"symbol": sym, "error": str(e)}


def v11_performance_dashboard():
    universe = V11_DASHBOARD_UNIVERSE[:20]
    regime = v11_market_regime_multidim()
    breadth = v10_true_market_breadth(universe)
    portfolio = v11_portfolio_risk_engine()
    journal = v11_journal_stats()
    leaders = []
    for s in universe[:12]:
        try:
            ex = v10_explainable_score(s)
            hist = v11_historical_signal_winrate(s, period="1y", horizon_days=V11_SIGNAL_HORIZON_DAYS)
            leaders.append({"symbol": s, "decision": ex.get("decision"), "score": ex.get("final_score"), "price": ex.get("price"), "historical_win_rate_pct": hist.get("win_rate_pct"), "historical_signals": hist.get("closed_historical_signals")})
        except Exception as e:
            leaders.append({"symbol": s, "error": str(e)})
    leaders = sorted(leaders, key=lambda x: x.get("score") if isinstance(x.get("score"), (int,float)) else -1, reverse=True)
    return {"version": "V11 Institutional Plus Free 100%", "time": now_text(), "market_regime_multidim": regime, "breadth": breadth, "portfolio_risk": portfolio, "journal": journal, "top_watchlist_scores": leaders, "dashboard_note": "This is a free analyst dashboard. Validate with broker data before trading."}


def v11_institutional_snapshot(symbol):
    sym = symbol.upper()
    return {"version": "V11 Institutional Plus Free 100%", "symbol": sym, "explainable_score": v10_explainable_score(sym), "historical_signal_winrate": v11_historical_signal_winrate(sym), "option_flow_unusual": v11_option_flow_unusual(sym), "portfolio_risk": v11_portfolio_risk_engine(), "market_regime_multidim": v11_market_regime_multidim(), "trade_note": "Use as decision support only; not investment advice."}


@app.route("/v11-status", methods=["GET"])
def v11_status_route():
    return jsonify({"version": "V11 Institutional Plus Free 100%", "enabled": V11_ENABLED, "axes": ["Signal Journal + historical win-rate proxy", "Portfolio Risk Engine", "Multi-dimensional Market Regime: VIX/Yield/Dollar/Sector", "Option Flow / Unusual Volume proxy", "Performance Dashboard"], "routes": ["/v11/<symbol>", "/v11/historical/<symbol>", "/v11/journal", "/v11/journal/log/<symbol>", "/v11/portfolio", "/v11/regime", "/v11/options-flow/<symbol>", "/v11/dashboard"]})


@app.route("/v11/<symbol>", methods=["GET"])
def v11_snapshot_route(symbol):
    return jsonify(v11_institutional_snapshot(symbol))


@app.route("/v11/historical/<symbol>", methods=["GET"])
def v11_historical_route(symbol):
    return jsonify(v11_historical_signal_winrate(symbol, request.args.get("period", "1y"), request.args.get("horizon_days")))


@app.route("/v11/journal", methods=["GET"])
def v11_journal_route():
    return jsonify(v11_journal_stats(request.args.get("symbol")))


@app.route("/v11/journal/log/<symbol>", methods=["GET", "POST"])
def v11_journal_log_route(symbol):
    return jsonify(v11_log_current_signal(symbol))


@app.route("/v11/portfolio", methods=["GET"])
def v11_portfolio_route():
    return jsonify(v11_portfolio_risk_engine())


@app.route("/v11/regime", methods=["GET"])
def v11_regime_route():
    return jsonify(v11_market_regime_multidim())


@app.route("/v11/options-flow/<symbol>", methods=["GET"])
def v11_options_flow_route(symbol):
    return jsonify(v11_option_flow_unusual(symbol))


@app.route("/v11/dashboard", methods=["GET"])
def v11_dashboard_route():
    return jsonify(v11_performance_dashboard())



# ============================================================
# V12 INSTITUTIONAL RESEARCH GRADE - FREE 100%
# ============================================================
V12_ENABLED = os.getenv("V12_ENABLED", "true").lower() == "true"
V12_DASHBOARD_UNIVERSE = env_list("V12_DASHBOARD_UNIVERSE", "NVDA,AAPL,TSLA,AMD,MSFT,META,AMZN,GOOGL,AVGO,PLTR,QQQ,SPY,IWM,SMH,XLF,XLE,XLK,TLT,HYG,GLD,USO")
V12_MONTE_CARLO_RUNS = int(os.getenv("V12_MONTE_CARLO_RUNS", "1000"))
V12_MONTE_CARLO_DAYS = int(os.getenv("V12_MONTE_CARLO_DAYS", "20"))
V12_VAR_LEVEL = float(os.getenv("V12_VAR_LEVEL", "0.05"))
V12_MAX_CORRELATED_EXPOSURE_PCT = float(os.getenv("V12_MAX_CORRELATED_EXPOSURE_PCT", "45"))
V12_MAX_SINGLE_THEME_PCT = float(os.getenv("V12_MAX_SINGLE_THEME_PCT", "40"))

V12_THEME_MAP = {
    "NVDA":"AI_SEMICON", "AMD":"AI_SEMICON", "AVGO":"AI_SEMICON", "SMCI":"AI_SEMICON", "SMH":"SEMICON_ETF", "TSM":"AI_SEMICON",
    "AAPL":"MEGA_CAP_TECH", "MSFT":"MEGA_CAP_TECH", "META":"MEGA_CAP_TECH", "GOOGL":"MEGA_CAP_TECH", "GOOG":"MEGA_CAP_TECH", "AMZN":"MEGA_CAP_TECH",
    "QQQ":"NASDAQ_BETA", "TQQQ":"NASDAQ_BETA", "SQQQ":"NASDAQ_BETA", "SPY":"SP500_BETA", "IWM":"SMALL_CAP_BETA",
    "TSLA":"EV_HIGH_BETA", "PLTR":"AI_SOFTWARE", "SNOW":"AI_SOFTWARE", "CRWD":"CYBER_SOFTWARE", "NET":"CYBER_SOFTWARE",
    "JPM":"FINANCIALS", "BAC":"FINANCIALS", "XLF":"FINANCIALS", "XOM":"ENERGY", "CVX":"ENERGY", "XLE":"ENERGY", "USO":"OIL",
    "TLT":"BONDS_DURATION", "HYG":"CREDIT_RISK", "GLD":"GOLD_DEFENSIVE", "GOLD":"GOLD_DEFENSIVE",
    "ADVANC":"THAI_TELECOM", "TRUE":"THAI_TELECOM", "SCB":"THAI_BANK", "KBANK":"THAI_BANK", "BBL":"THAI_BANK", "AOT":"THAI_TOURISM", "PTT":"THAI_ENERGY"
}

def v12_yf_symbol(symbol):
    s = resolve_delisted_symbol(symbol).upper().strip()
    if s in GOLD_WORDS or s == "GOLD":
        return "GC=F"
    if s.endswith(".BK") or s.endswith(".SET"):
        return s.replace(".SET", ".BK")
    if s in THAI_SYMBOLS or s in TH_WATCHLIST or s in TIER_C_WATCHLIST:
        return f"{s}.BK"
    return s

def v12_theme(symbol):
    s = resolve_delisted_symbol(symbol).upper().replace(".BK", "").replace(".SET", "")
    return V12_THEME_MAP.get(s, "OTHER")

def v12_download_prices(symbols, period="1y"):
    out = {}
    for s in symbols:
        yf_sym = v12_yf_symbol(s)
        try:
            df = yf.Ticker(yf_sym).history(period=period, interval="1d", auto_adjust=True)
            if df is not None and not df.empty and "Close" in df.columns:
                out[s] = df["Close"].dropna()
        except Exception:
            continue
    return out

def v12_last_return(symbol, days=20):
    try:
        ser = v12_download_prices([symbol], period="6mo").get(symbol)
        if ser is None or len(ser) < days + 2:
            return None
        return float((ser.iloc[-1] / ser.iloc[-days-1] - 1) * 100)
    except Exception:
        return None

def v12_macro_regime_research_grade():
    probes = {
        "SPY":"SPY", "QQQ":"QQQ", "IWM":"IWM", "VIX":"^VIX", "US10Y":"^TNX",
        "DOLLAR":"DX-Y.NYB", "TLT":"TLT", "HYG":"HYG", "GOLD":"GLD", "OIL":"USO",
        "SEMICON":"SMH", "TECH":"XLK", "FINANCIALS":"XLF", "ENERGY":"XLE"
    }
    score = 50
    signals = []
    data = {}
    for name, sym in probes.items():
        try:
            ser = yf.Ticker(sym).history(period="6mo", interval="1d", auto_adjust=True)["Close"].dropna()
            if len(ser) < 60:
                continue
            last = float(ser.iloc[-1])
            ma20 = float(ser.tail(20).mean())
            ma50 = float(ser.tail(50).mean())
            chg20 = float((ser.iloc[-1] / ser.iloc[-21] - 1) * 100) if len(ser) > 21 else None
            data[name] = {"symbol": sym, "last": round(last, 4), "above_ma20": last > ma20, "above_ma50": last > ma50, "chg20_pct": round(chg20, 2) if chg20 is not None else None}
        except Exception as e:
            data[name] = {"symbol": sym, "error": str(e)[:120]}

    def add(cond, pts, reason):
        nonlocal score
        if cond:
            score += pts
            signals.append(reason)

    add(data.get("SPY", {}).get("above_ma50"), 8, "SPY above 50D = equity risk-on")
    add(data.get("QQQ", {}).get("above_ma50"), 8, "QQQ above 50D = growth leadership")
    add(data.get("IWM", {}).get("above_ma50"), 5, "IWM above 50D = broader risk appetite")
    add(data.get("VIX", {}).get("last", 99) < 18, 9, "VIX below 18 = low stress")
    add(data.get("VIX", {}).get("last", 0) > 25, -15, "VIX above 25 = stress regime")
    add(data.get("HYG", {}).get("above_ma50"), 8, "HYG above 50D = credit risk-on")
    add(data.get("TLT", {}).get("chg20_pct", 0) < -3, -5, "TLT weak = rate pressure")
    add(data.get("US10Y", {}).get("chg20_pct", 0) > 8, -6, "10Y yield rising quickly = duration headwind")
    add(data.get("DOLLAR", {}).get("chg20_pct", 0) > 3, -5, "Dollar rising = liquidity headwind")
    add(data.get("SEMICON", {}).get("above_ma50"), 7, "Semiconductor leadership positive for AI/tech beta")
    add(data.get("FINANCIALS", {}).get("above_ma50"), 4, "Financials above 50D supports cyclicals")
    add(data.get("ENERGY", {}).get("chg20_pct", 0) > 5, -3, "Energy spike can pressure inflation expectations")
    add(data.get("GOLD", {}).get("chg20_pct", 0) > 6 and not data.get("SPY", {}).get("above_ma50"), -5, "Gold outperforming while equities weak = defensive stress")

    score = max(0, min(100, int(score)))
    if score >= 75:
        regime = "RISK_ON_INSTITUTIONAL"
    elif score >= 60:
        regime = "CONSTRUCTIVE_MIXED"
    elif score >= 40:
        regime = "NEUTRAL_DEFENSIVE"
    else:
        regime = "RISK_OFF_INSTITUTIONAL"
    return {"version":"V12 Institutional Research Grade", "time": now_text(), "macro_score": score, "macro_regime": regime, "signals": signals, "market_inputs": data, "instruction": "Favor long setups with pullback entries" if score >= 70 else "Reduce size and require confirmation" if score < 50 else "Selective trades only"}

def v12_correlation_exposure_engine():
    positions = v11_parse_portfolio_env()
    total = sum(float(p.get("value", 0)) for p in positions) or 1.0
    exposure_by_theme = {}
    rows = []
    for p in positions:
        sym = resolve_delisted_symbol(p.get("symbol", "")).replace(".BK", "").replace(".SET", "")
        val = float(p.get("value", 0))
        theme = v12_theme(sym)
        exposure_by_theme[theme] = exposure_by_theme.get(theme, 0) + val
        rows.append({"symbol": sym, "value": round(val, 2), "weight_pct": round(val / total * 100, 2), "theme": theme})
    theme_pct = {k: round(v / total * 100, 2) for k, v in exposure_by_theme.items()}
    max_theme = max(theme_pct.values()) if theme_pct else 0
    # Correlation proxy from historical returns for provided positions.
    corr_matrix = {}
    symbols = [r["symbol"] for r in rows][:12]
    prices = v12_download_prices(symbols, period="1y") if symbols else {}
    returns = {}
    for s, ser in prices.items():
        try:
            returns[s] = ser.pct_change().dropna().tail(120)
        except Exception:
            pass
    if len(returns) >= 2:
        keys = list(returns.keys())
        for a in keys:
            corr_matrix[a] = {}
            for b in keys:
                try:
                    joined = __import__('pandas').concat([returns[a], returns[b]], axis=1).dropna()
                    corr = float(joined.iloc[:,0].corr(joined.iloc[:,1])) if len(joined) > 10 else None
                    corr_matrix[a][b] = round(corr, 2) if corr is not None else None
                except Exception:
                    corr_matrix[a][b] = None
    warnings = []
    if max_theme > V12_MAX_SINGLE_THEME_PCT:
        warnings.append(f"Theme concentration {max_theme}% exceeds {V12_MAX_SINGLE_THEME_PCT}%")
    high_corr_pairs = []
    for a, inner in corr_matrix.items():
        for b, c in inner.items():
            if a < b and c is not None and c >= 0.75:
                high_corr_pairs.append({"pair": f"{a}/{b}", "corr": c})
    if high_corr_pairs:
        warnings.append("High correlation cluster detected")
    return {"version":"V12 Correlation & Exposure Engine", "positions": rows, "theme_exposure_pct": theme_pct, "max_theme_pct": max_theme, "correlation_matrix": corr_matrix, "high_corr_pairs": high_corr_pairs[:20], "warnings": warnings, "status": "OK" if not warnings else "REVIEW_REQUIRED", "note": "Set V11_PORTFOLIO_POSITIONS in Railway Variables for real portfolio exposure."}

def v12_monte_carlo_risk(symbol="SPY", days=None, runs=None):
    sym = resolve_delisted_symbol(symbol).upper()
    days = int(days or V12_MONTE_CARLO_DAYS)
    runs = int(runs or V12_MONTE_CARLO_RUNS)
    try:
        import random, statistics
        ser = v12_download_prices([sym], period="2y").get(sym)
        if ser is None or len(ser) < 80:
            return {"symbol": sym, "error": "not enough historical data"}
        rets = [float(x) for x in ser.pct_change().dropna().tail(252).values if x == x]
        last = float(ser.iloc[-1])
        finals = []
        max_dds = []
        for _ in range(max(100, min(runs, 5000))):
            price = last
            peak = price
            max_dd = 0.0
            for _d in range(days):
                r = random.choice(rets)
                price *= (1 + r)
                peak = max(peak, price)
                dd = (price / peak - 1)
                max_dd = min(max_dd, dd)
            finals.append((price / last - 1) * 100)
            max_dds.append(max_dd * 100)
        finals_sorted = sorted(finals)
        idx = max(0, min(len(finals_sorted)-1, int(len(finals_sorted) * V12_VAR_LEVEL)))
        prob_loss = sum(1 for x in finals if x < 0) / len(finals) * 100
        prob_loss_5 = sum(1 for x in finals if x <= -5) / len(finals) * 100
        return {"version":"V12 Monte Carlo Risk", "symbol": sym, "last_price": round(last, 4), "horizon_days": days, "runs": len(finals), "expected_return_pct": round(statistics.mean(finals), 2), "median_return_pct": round(statistics.median(finals), 2), "var_5pct_return_pct": round(finals_sorted[idx], 2), "worst_sim_return_pct": round(min(finals), 2), "best_sim_return_pct": round(max(finals), 2), "probability_loss_pct": round(prob_loss, 2), "probability_loss_gt_5pct": round(prob_loss_5, 2), "avg_max_drawdown_pct": round(statistics.mean(max_dds), 2), "note": "Bootstrap simulation from historical daily returns; not a prediction."}
    except Exception as e:
        return {"symbol": sym, "error": str(e)}

def v12_attribution_engine(symbol):
    sym = resolve_delisted_symbol(symbol).upper().replace(".BK", "").replace(".SET", "")
    ex = v10_explainable_score(sym)
    flow = v11_option_flow_unusual(sym) if classify_watchlist_symbol(sym) == "US_STOCK" else {"bias":"N/A", "summary":{}}
    hist = v11_historical_signal_winrate(sym)
    macro = v12_macro_regime_research_grade()
    components = ex.get("components", []) or []
    buckets = {"trend":0, "momentum":0, "volatility":0, "options_flow":0, "breadth_macro":0, "historical_edge":0}
    for c in components:
        fac = str(c.get("factor", "")).lower()
        pts = int(c.get("points", 0) or 0)
        if "trend" in fac or "ema" in fac:
            buckets["trend"] += pts
        elif "momentum" in fac or "rsi" in fac or "macd" in fac:
            buckets["momentum"] += pts
        elif "vol" in fac or "atr" in fac:
            buckets["volatility"] += pts
        else:
            buckets["momentum"] += pts
    if flow.get("summary", {}).get("count", 0):
        buckets["options_flow"] = min(15, int(flow.get("summary", {}).get("count", 0)))
    if macro.get("macro_score", 50) >= 70:
        buckets["breadth_macro"] = 12
    elif macro.get("macro_score", 50) <= 40:
        buckets["breadth_macro"] = -12
    if isinstance(hist.get("win_rate_pct"), (int,float)):
        buckets["historical_edge"] = int((hist.get("win_rate_pct") - 50) / 2)
    total_attr = sum(buckets.values())
    return {"version":"V12 Attribution Engine", "symbol": sym, "decision": ex.get("decision"), "final_score": ex.get("final_score"), "attribution_points": buckets, "attribution_total": total_attr, "option_flow_bias": flow.get("bias"), "historical_win_rate_pct": hist.get("win_rate_pct"), "macro_regime": macro.get("macro_regime"), "interpretation": "Strong multi-factor alignment" if total_attr >= 40 else "Mixed signal; require confirmation" if total_attr >= 15 else "Weak/low-conviction setup"}

def v12_executive_dashboard():
    universe = V12_DASHBOARD_UNIVERSE[:24]
    macro = v12_macro_regime_research_grade()
    exposure = v12_correlation_exposure_engine()
    breadth = v10_true_market_breadth(universe)
    watch = []
    risks = []
    for s in universe[:16]:
        try:
            att = v12_attribution_engine(s)
            mc = v12_monte_carlo_risk(s, days=10, runs=300)
            row = {"symbol": resolve_delisted_symbol(s), "decision": att.get("decision"), "score": att.get("final_score"), "attribution_total": att.get("attribution_total"), "historical_win_rate_pct": att.get("historical_win_rate_pct"), "mc_var_5pct_10d": mc.get("var_5pct_return_pct"), "mc_prob_loss_pct": mc.get("probability_loss_pct")}
            watch.append(row)
            if isinstance(mc.get("var_5pct_return_pct"), (int,float)) and mc.get("var_5pct_return_pct") <= -8:
                risks.append({"symbol": s, "risk": "High 10D VaR", "value": mc.get("var_5pct_return_pct")})
        except Exception as e:
            watch.append({"symbol": s, "error": str(e)[:120]})
    watch = sorted(watch, key=lambda x: x.get("score") if isinstance(x.get("score"), (int,float)) else -1, reverse=True)
    return {"version":"V12 Institutional Research Grade Free 100%", "time": now_text(), "executive_summary": {"macro_regime": macro.get("macro_regime"), "macro_score": macro.get("macro_score"), "breadth_regime": breadth.get("breadth_regime"), "portfolio_status": exposure.get("status"), "key_risks": risks[:8]}, "top_opportunities": watch[:10], "macro": macro, "breadth": breadth, "portfolio_exposure": exposure, "note": "Research-grade decision support using free data only; validate with broker/official data before trading."}

def v12_research_snapshot(symbol):
    sym = resolve_delisted_symbol(symbol)
    return {"version":"V12 Institutional Research Grade Free 100%", "symbol": sym, "v11_snapshot": v11_institutional_snapshot(sym), "macro_regime": v12_macro_regime_research_grade(), "correlation_exposure": v12_correlation_exposure_engine(), "monte_carlo": v12_monte_carlo_risk(sym), "attribution": v12_attribution_engine(sym), "trade_note": "Use as research support only; not investment advice."}

@app.route("/v12-status", methods=["GET"])
def v12_status_route():
    return jsonify({"version":"V12 Institutional Research Grade Free 100%", "enabled": V12_ENABLED, "intuch_fix":"INTUCH/INTUCH.BK is redirected to ADVANC/ADVANC.BK and removed from market-leader watchlist", "axes":["Multi-Asset Macro Regime: VIX, Yield, Dollar, Bonds, Credit, Gold, Oil, Sectors", "Correlation & Exposure Engine", "Monte Carlo Risk Engine", "Attribution Engine", "Executive Dashboard"], "routes":["/v12/<symbol>", "/v12/dashboard", "/v12/macro", "/v12/exposure", "/v12/monte-carlo/<symbol>", "/v12/attribution/<symbol>", "/v12/intuch-fix"]})

@app.route("/v12/<symbol>", methods=["GET"])
def v12_snapshot_route(symbol):
    return jsonify(v12_research_snapshot(symbol))

@app.route("/v12/dashboard", methods=["GET"])
def v12_dashboard_route():
    return jsonify(v12_executive_dashboard())

@app.route("/v12/macro", methods=["GET"])
def v12_macro_route():
    return jsonify(v12_macro_regime_research_grade())

@app.route("/v12/exposure", methods=["GET"])
def v12_exposure_route():
    return jsonify(v12_correlation_exposure_engine())

@app.route("/v12/monte-carlo/<symbol>", methods=["GET"])
def v12_monte_carlo_route(symbol):
    return jsonify(v12_monte_carlo_risk(symbol, request.args.get("days"), request.args.get("runs")))

@app.route("/v12/attribution/<symbol>", methods=["GET"])
def v12_attribution_route(symbol):
    return jsonify(v12_attribution_engine(symbol))

@app.route("/v12/intuch-fix", methods=["GET"])
def v12_intuch_fix_route():
    return jsonify({"status":"fixed", "mapping": DELISTED_SYMBOL_ALIASES, "INTUCH_normalized": normalize_asset("INTUCH"), "INTUCH_BK_normalized": normalize_asset("INTUCH.BK"), "note":"INTUCH is redirected to ADVANC to avoid Yahoo Finance no-data errors."})


# ============================================================
# V12.1 INSTITUTIONAL INTERNALS PACK - FREE 100%
# Market Internals, Expected Move, Liquidity Score, Opportunity Ranking
# ============================================================
V121_ENABLED = os.getenv("V121_ENABLED", "true").lower() == "true"
V121_RANK_UNIVERSE = env_list(
    "V121_RANK_UNIVERSE",
    os.getenv("V12_DASHBOARD_UNIVERSE", os.getenv("US_WATCHLIST", "NVDA,AAPL,TSLA,AMD,QQQ,SPY,META,MSFT,PLTR,AVGO,AMZN,GOOGL,COIN,MSTR,SMCI,ARM,CRWD,NET,DDOG,SHOP"))
)
V121_MAX_RANK_SYMBOLS = int(os.getenv("V121_MAX_RANK_SYMBOLS", "30"))
V121_MIN_OPTION_VOLUME = int(os.getenv("V121_MIN_OPTION_VOLUME", "20"))
V121_MAX_OPTION_SPREAD_PCT = float(os.getenv("V121_MAX_OPTION_SPREAD_PCT", "18"))


def _safe_float(x, default=None):
    try:
        if x is None:
            return default
        v = float(x)
        if v != v:
            return default
        return v
    except Exception:
        return default


def _pct_change_from_history(symbol, period="5d"):
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period=period, interval="1d", auto_adjust=False)
        if hist is None or len(hist) < 2:
            return None
        last = _safe_float(hist["Close"].iloc[-1])
        prev = _safe_float(hist["Close"].iloc[-2])
        if not last or not prev:
            return None
        return (last / prev - 1) * 100
    except Exception:
        return None


def v121_market_internals():
    """Free-data market internals proxy. Uses yfinance-supported indices/ETFs plus V10 breadth fallback.
    Real $ADD/$TICK/$TRIN feeds are usually paid; this is a transparent proxy, not a paid tape feed.
    """
    proxies = {
        "SPY": "S&P 500 ETF proxy",
        "QQQ": "Nasdaq 100 ETF proxy",
        "IWM": "Russell 2000 ETF proxy",
        "DIA": "Dow ETF proxy",
        "^VIX": "VIX volatility index",
        "HYG": "High-yield credit ETF proxy",
        "TLT": "Long-duration treasury ETF proxy",
        "UUP": "US Dollar ETF proxy"
    }
    moves = {}
    for sym, label in proxies.items():
        moves[sym] = {"label": label, "pct_change": _pct_change_from_history(sym)}
    universe = V121_RANK_UNIVERSE[:max(10, min(60, len(V121_RANK_UNIVERSE)))]
    try:
        breadth = v10_true_market_breadth(universe)
    except Exception as e:
        breadth = {"error": str(e)}
    score = 50
    reasons = []
    def add(points, reason):
        nonlocal score
        score += points
        reasons.append({"points": points, "reason": reason})
    spy = moves.get("SPY", {}).get("pct_change")
    qqq = moves.get("QQQ", {}).get("pct_change")
    iwm = moves.get("IWM", {}).get("pct_change")
    vix = moves.get("^VIX", {}).get("pct_change")
    hyg = moves.get("HYG", {}).get("pct_change")
    tlt = moves.get("TLT", {}).get("pct_change")
    if spy is not None:
        add(10 if spy > 0.35 else -10 if spy < -0.35 else 0, f"SPY daily move {spy:.2f}%")
    if qqq is not None:
        add(10 if qqq > 0.45 else -10 if qqq < -0.45 else 0, f"QQQ daily move {qqq:.2f}%")
    if iwm is not None:
        add(6 if iwm > 0.35 else -6 if iwm < -0.35 else 0, f"IWM small-cap move {iwm:.2f}%")
    if vix is not None:
        add(10 if vix < -2 else -12 if vix > 3 else 0, f"VIX move {vix:.2f}%")
    if hyg is not None:
        add(7 if hyg > 0.15 else -7 if hyg < -0.15 else 0, f"HYG credit-risk proxy {hyg:.2f}%")
    if tlt is not None and spy is not None:
        add(3 if (spy > 0 and tlt <= 0.5) else -3 if (spy < 0 and tlt > 0.5) else 0, f"TLT duration proxy {tlt:.2f}%")
    if isinstance(breadth, dict):
        bscore = breadth.get("breadth_score")
        if isinstance(bscore, (int, float)):
            add(12 if bscore >= 65 else -12 if bscore <= 40 else 0, f"Breadth score {bscore}")
    score = max(0, min(100, int(score)))
    if score >= 75:
        regime = "INTERNALS_RISK_ON"
    elif score <= 35:
        regime = "INTERNALS_RISK_OFF"
    else:
        regime = "INTERNALS_MIXED"
    return {"version":"V12.1 Market Internals Free Proxy", "time":now_text(), "internals_score":score, "internals_regime":regime, "proxy_moves":moves, "breadth":breadth, "score_breakdown":reasons, "important_note":"Free proxy only. Real $ADD/$TICK/$TRIN usually require paid/live market data feeds."}


def _nearest_atm_option_row(symbol, expiry=None):
    sym = resolve_delisted_symbol(symbol).upper().replace(".BK", "").replace(".SET", "")
    tk = yf.Ticker(sym)
    hist = tk.history(period="5d", interval="1d", auto_adjust=False)
    if hist is None or hist.empty:
        return {"symbol": sym, "error": "no underlying price"}
    price = _safe_float(hist["Close"].iloc[-1])
    expirations = list(getattr(tk, "options", []) or [])
    if not expirations:
        return {"symbol": sym, "underlying_price": price, "error": "no option expirations from yfinance"}
    exp = expiry if expiry in expirations else expirations[0]
    chain = tk.option_chain(exp)
    calls = chain.calls.copy()
    puts = chain.puts.copy()
    if calls is None or puts is None or calls.empty or puts.empty:
        return {"symbol": sym, "underlying_price": price, "expiration": exp, "error": "empty option chain"}
    calls["dist"] = (calls["strike"] - price).abs()
    puts["dist"] = (puts["strike"] - price).abs()
    call = calls.sort_values("dist").iloc[0].to_dict()
    put = puts.sort_values("dist").iloc[0].to_dict()
    return {"symbol": sym, "underlying_price": price, "expiration": exp, "call": call, "put": put, "expirations_available": expirations[:8]}


def v121_expected_move_engine(symbol, expiry=None):
    data = _nearest_atm_option_row(symbol, expiry)
    if data.get("error"):
        return {"version":"V12.1 Expected Move Engine", **data}
    price = data.get("underlying_price")
    call = data.get("call", {})
    put = data.get("put", {})
    call_mid = None
    put_mid = None
    for row, name in [(call, "call"), (put, "put")]:
        bid = _safe_float(row.get("bid"), 0) or 0
        ask = _safe_float(row.get("ask"), 0) or 0
        last = _safe_float(row.get("lastPrice"), 0) or 0
        mid = (bid + ask) / 2 if bid > 0 and ask > 0 else last
        if name == "call":
            call_mid = mid
        else:
            put_mid = mid
    straddle = (call_mid or 0) + (put_mid or 0)
    expected_pct = (straddle / price * 100) if price and straddle else None
    return {"version":"V12.1 Expected Move Engine", "symbol":data.get("symbol"), "underlying_price":round(price, 4), "expiration":data.get("expiration"), "atm_call":{"contractSymbol":call.get("contractSymbol"), "strike":_safe_float(call.get("strike")), "bid":_safe_float(call.get("bid")), "ask":_safe_float(call.get("ask")), "lastPrice":_safe_float(call.get("lastPrice")), "volume":_safe_float(call.get("volume")), "openInterest":_safe_float(call.get("openInterest")), "impliedVolatility":_safe_float(call.get("impliedVolatility"))}, "atm_put":{"contractSymbol":put.get("contractSymbol"), "strike":_safe_float(put.get("strike")), "bid":_safe_float(put.get("bid")), "ask":_safe_float(put.get("ask")), "lastPrice":_safe_float(put.get("lastPrice")), "volume":_safe_float(put.get("volume")), "openInterest":_safe_float(put.get("openInterest")), "impliedVolatility":_safe_float(put.get("impliedVolatility"))}, "expected_move_abs":round(straddle, 4) if straddle else None, "expected_move_pct":round(expected_pct, 2) if expected_pct is not None else None, "expected_range":{"low":round(price - straddle, 2) if straddle else None, "high":round(price + straddle, 2) if straddle else None}, "method":"ATM call mid + ATM put mid for nearest/selected expiry. Free yfinance data may be delayed/incomplete."}


def v121_liquidity_score(symbol, expiry=None):
    data = _nearest_atm_option_row(symbol, expiry)
    if data.get("error"):
        return {"version":"V12.1 Liquidity Score", **data}
    rows = [("call", data.get("call", {})), ("put", data.get("put", {}))]
    details = []
    score = 50
    for side, row in rows:
        bid = _safe_float(row.get("bid"), 0) or 0
        ask = _safe_float(row.get("ask"), 0) or 0
        last = _safe_float(row.get("lastPrice"), 0) or 0
        vol = _safe_float(row.get("volume"), 0) or 0
        oi = _safe_float(row.get("openInterest"), 0) or 0
        mid = (bid + ask) / 2 if bid > 0 and ask > 0 else last
        spread_pct = ((ask - bid) / mid * 100) if bid > 0 and ask > 0 and mid > 0 else None
        pts = 0
        if spread_pct is not None:
            pts += 18 if spread_pct <= 5 else 10 if spread_pct <= 10 else 3 if spread_pct <= V121_MAX_OPTION_SPREAD_PCT else -12
        else:
            pts -= 8
        pts += 12 if vol >= 1000 else 8 if vol >= 300 else 4 if vol >= V121_MIN_OPTION_VOLUME else -6
        pts += 12 if oi >= 3000 else 8 if oi >= 1000 else 4 if oi >= 200 else -4
        score += pts / 2
        details.append({"side":side, "contractSymbol":row.get("contractSymbol"), "strike":_safe_float(row.get("strike")), "bid":bid, "ask":ask, "mid":round(mid, 4) if mid else None, "spread_pct":round(spread_pct, 2) if spread_pct is not None else None, "volume":vol, "openInterest":oi, "points":round(pts, 2)})
    score = int(max(0, min(100, score)))
    grade = "A" if score >= 82 else "B" if score >= 68 else "C" if score >= 50 else "D"
    return {"version":"V12.1 Liquidity Score", "symbol":data.get("symbol"), "underlying_price":round(data.get("underlying_price"), 4), "expiration":data.get("expiration"), "liquidity_score":score, "liquidity_grade":grade, "details":details, "interpretation":"Tradable liquidity" if score >= 68 else "Use caution; spreads/volume may be weak" if score >= 50 else "Avoid or use limit orders only; liquidity is poor", "note":"Scored from ATM option spread, volume, and open interest using free yfinance chain."}


def v121_opportunity_ranking(limit=None):
    try:
        n = int(limit or request.args.get("limit", 20)) if 'request' in globals() else int(limit or 20)
    except Exception:
        n = 20
    n = max(5, min(n, 50))
    universe = V121_RANK_UNIVERSE[:max(n, min(V121_MAX_RANK_SYMBOLS, len(V121_RANK_UNIVERSE)))]
    internals = v121_market_internals()
    call_rows = []
    put_rows = []
    errors = []
    for sym in universe:
        try:
            s = resolve_delisted_symbol(sym).upper().replace(".BK", "").replace(".SET", "")
            if classify_watchlist_symbol(s) != "US_STOCK":
                continue
            ex = v10_explainable_score(s)
            liq = v121_liquidity_score(s)
            em = v121_expected_move_engine(s)
            attr = v12_attribution_engine(s)
            final_score = ex.get("final_score") if isinstance(ex.get("final_score"), (int, float)) else ex.get("score", 50)
            liq_score = liq.get("liquidity_score") if isinstance(liq.get("liquidity_score"), (int, float)) else 40
            attr_total = attr.get("attribution_total") if isinstance(attr.get("attribution_total"), (int, float)) else 0
            internals_score = internals.get("internals_score") if isinstance(internals.get("internals_score"), (int, float)) else 50
            expected_pct = em.get("expected_move_pct") if isinstance(em.get("expected_move_pct"), (int, float)) else None
            call_score = int(max(0, min(100, final_score * 0.45 + liq_score * 0.20 + max(0, attr_total) * 0.20 + internals_score * 0.15)))
            put_score = int(max(0, min(100, (100 - final_score) * 0.45 + liq_score * 0.20 + max(0, -attr_total) * 0.20 + (100 - internals_score) * 0.15)))
            base = {"symbol":s, "signal_score":final_score, "liquidity_grade":liq.get("liquidity_grade"), "liquidity_score":liq_score, "expected_move_pct":expected_pct, "attribution_total":attr_total, "internals_score":internals_score, "decision":ex.get("decision"), "why":[f"signal={final_score}", f"liquidity={liq_score}/{liq.get('liquidity_grade')}", f"attribution={attr_total}", f"internals={internals_score}"]}
            call_rows.append({**base, "rank_score":call_score, "side":"CALL"})
            put_rows.append({**base, "rank_score":put_score, "side":"PUT"})
        except Exception as e:
            errors.append({"symbol": sym, "error": str(e)[:160]})
    call_rows = sorted(call_rows, key=lambda x: x.get("rank_score", 0), reverse=True)[:n]
    put_rows = sorted(put_rows, key=lambda x: x.get("rank_score", 0), reverse=True)[:n]
    return {"version":"V12.1 Opportunity Ranking", "time":now_text(), "market_internals":{"regime":internals.get("internals_regime"), "score":internals.get("internals_score")}, "top_call_watchlist":call_rows, "top_put_watchlist":put_rows, "errors":errors[:10], "method":"Ranks free-data setups using explainable score, liquidity, attribution, expected move context, and market internals. Research support only."}


def v121_dashboard():
    internals = v121_market_internals()
    ranking = v121_opportunity_ranking(limit=10)
    return {"version":"V12.1 Institutional Internals Pack Free 100%", "time":now_text(), "executive_summary":{"internals_regime":internals.get("internals_regime"), "internals_score":internals.get("internals_score"), "best_call":(ranking.get("top_call_watchlist") or [{}])[0], "best_put":(ranking.get("top_put_watchlist") or [{}])[0]}, "market_internals":internals, "opportunity_ranking":ranking, "routes":["/v12-1/status", "/v12-1/dashboard", "/v12-1/internals", "/v12-1/expected-move/<symbol>", "/v12-1/liquidity/<symbol>", "/v12-1/ranking"]}


@app.route("/v12-1/status", methods=["GET"])
def v121_status_route():
    return jsonify({"version":"V12.1 Institutional Internals Pack Free 100%", "enabled":V121_ENABLED, "modules":["Market Internals Free Proxy", "Expected Move Engine", "Liquidity Score", "Opportunity Ranking"], "routes":["/v12-1/dashboard", "/v12-1/internals", "/v12-1/expected-move/<symbol>", "/v12-1/liquidity/<symbol>", "/v12-1/ranking"], "note":"Uses free yfinance/proxy data. Real $ADD/$TICK/$TRIN and professional option flow usually require paid feeds."})

@app.route("/v12-1/dashboard", methods=["GET"])
def v121_dashboard_route():
    return jsonify(v121_dashboard())

@app.route("/v12-1/internals", methods=["GET"])
def v121_internals_route():
    return jsonify(v121_market_internals())

@app.route("/v12-1/expected-move/<symbol>", methods=["GET"])
def v121_expected_move_route(symbol):
    return jsonify(v121_expected_move_engine(symbol, request.args.get("expiry")))

@app.route("/v12-1/liquidity/<symbol>", methods=["GET"])
def v121_liquidity_route(symbol):
    return jsonify(v121_liquidity_score(symbol, request.args.get("expiry")))

@app.route("/v12-1/ranking", methods=["GET"])
def v121_ranking_route():
    return jsonify(v121_opportunity_ranking(request.args.get("limit")))



# ============================================================
# V13.1 SIGNAL QUALITY + INSTITUTIONAL ANALYTICS LAYER
# ============================================================
V131_ENABLED = os.getenv("V131_ENABLED", "true").lower() == "true"
V131_ACCOUNT_SIZE = float(os.getenv("V131_ACCOUNT_SIZE", "10000"))
V131_RISK_PER_TRADE_PCT = float(os.getenv("V131_RISK_PER_TRADE_PCT", "1.0"))
V131_RANKING_UNIVERSE = [
    x.strip().upper()
    for x in os.getenv(
        "V131_RANKING_UNIVERSE",
        os.getenv("TOP5_UNIVERSE", "NVDA,AAPL,TSLA,AMD,MSFT,META,QQQ,SPY,PLTR,AVGO,AMZN,GOOGL,SMCI,MSTR,COIN,ARM,MU,CRWD,NET,HOOD,RKLB,IREN")
    ).split(",")
    if x.strip()
]

def v131_now_iso():
    return datetime.now(timezone.utc).isoformat()

def v131_parse_created_at(value):
    if not value:
        return None
    for fmt in ("%d/%m/%Y %H:%M", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(str(value), fmt)
        except Exception:
            pass
    return None

def v131_init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS signal_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            created_ts REAL NOT NULL,
            symbol TEXT NOT NULL,
            asset_type TEXT,
            entry_price REAL,
            score INTEGER,
            bias TEXT,
            signal_type TEXT,
            strategy TEXT,
            regime TEXT,
            probability INTEGER,
            report TEXT,
            price_1d REAL,
            price_3d REAL,
            price_5d REAL,
            return_1d REAL,
            return_3d REAL,
            return_5d REAL,
            result_1d TEXT,
            result_3d TEXT,
            result_5d TEXT,
            updated_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS v131_performance_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            scope TEXT,
            payload TEXT
        )
    """)
    conn.commit()
    conn.close()

def v131_infer_strategy(score, bias, signal_type, regime, report):
    text = f"{bias or ''} {signal_type or ''} {regime or ''} {report or ''}".upper()
    try:
        score = int(score or 50)
    except Exception:
        score = 50
    if "VWAP" in text:
        return "VWAP_RECLAIM"
    if "PULLBACK" in text or "ย่อ" in text:
        return "PULLBACK"
    if "BREAKOUT" in text or "ทะลุ" in text:
        return "BREAKOUT"
    if "MOMENTUM" in text or score >= 85 or score <= 20:
        return "MOMENTUM"
    if "RANGE" in text:
        return "RANGE_REVERSAL"
    return "CORE_TREND"

def save_signal_audit(symbol, asset_type, price, score, bias, signal_type, regime, probability, report):
    if not V131_ENABLED:
        return
    try:
        if price is None:
            return
        strategy = v131_infer_strategy(score, bias, signal_type, regime, report)
        conn = db()
        conn.execute(
            """INSERT INTO signal_audit
               (created_at, created_ts, symbol, asset_type, entry_price, score, bias, signal_type, strategy, regime, probability, report, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                now_text(), time.time(), str(symbol).upper(), asset_type, safe_float(price), int(score or 0),
                bias, signal_type, strategy, regime, int(probability or 0), str(report or "")[:3000], v131_now_iso()
            ),
        )
        conn.commit()
        conn.close()
        # V14: mirror emitted signals into a true trade journal for outcome tracking.
        try:
            if "v14_auto_log_trade" in globals():
                v14_auto_log_trade(symbol, asset_type, price, score, bias, signal_type, regime, probability, report, source="signal_audit")
        except Exception as v14_error:
            print("V14 auto trade journal error:", v14_error)
    except Exception as e:
        print("V13.1 save_signal_audit error:", e)

def v131_current_price(symbol, asset_type=None):
    try:
        asset = normalize_asset(symbol)
        quote, closes, highs, lows, opens, volumes = get_market_data(asset)
        return safe_float(quote.get("close"))
    except Exception:
        try:
            data = yf.Ticker(symbol).history(period="5d", interval="1d", auto_adjust=False)
            if data is not None and not data.empty:
                return float(data["Close"].dropna().iloc[-1])
        except Exception:
            pass
    return None

def v131_result_for_return(signal_type, bias, ret):
    if ret is None:
        return None
    direction = "CALL"
    txt = f"{signal_type or ''} {bias or ''}".upper()
    if "PUT" in txt or "BEAR" in txt or "ขาย" in txt:
        direction = "PUT"
    win = ret > 0 if direction == "CALL" else ret < 0
    return "WIN" if win else "LOSS"

def v131_update_audit_results(limit=300):
    if not V131_ENABLED:
        return {"updated": 0, "enabled": False}
    now_ts = time.time()
    updated = 0
    conn = db()
    rows = conn.execute(
        """SELECT * FROM signal_audit
           WHERE (return_1d IS NULL OR return_3d IS NULL OR return_5d IS NULL)
           ORDER BY id DESC LIMIT ?""",
        (int(limit),),
    ).fetchall()
    for row in rows:
        try:
            age_days = (now_ts - float(row["created_ts"])) / 86400.0
            if age_days < 0.95:
                continue
            price_now = v131_current_price(row["symbol"], row["asset_type"])
            entry = safe_float(row["entry_price"])
            if not price_now or not entry:
                continue
            ret = (price_now - entry) / entry * 100.0
            fields = {}
            if age_days >= 0.95 and row["return_1d"] is None:
                fields.update({"price_1d": price_now, "return_1d": ret, "result_1d": v131_result_for_return(row["signal_type"], row["bias"], ret)})
            if age_days >= 2.95 and row["return_3d"] is None:
                fields.update({"price_3d": price_now, "return_3d": ret, "result_3d": v131_result_for_return(row["signal_type"], row["bias"], ret)})
            if age_days >= 4.95 and row["return_5d"] is None:
                fields.update({"price_5d": price_now, "return_5d": ret, "result_5d": v131_result_for_return(row["signal_type"], row["bias"], ret)})
            if fields:
                fields["updated_at"] = v131_now_iso()
                sets = ", ".join([f"{k}=?" for k in fields.keys()])
                conn.execute(f"UPDATE signal_audit SET {sets} WHERE id=?", list(fields.values()) + [row["id"]])
                updated += 1
        except Exception as e:
            print("V13.1 audit update row error:", e)
    conn.commit()
    conn.close()
    return {"updated": updated, "checked": len(rows), "enabled": True}

def v131_metrics_from_rows(rows, horizon="5d"):
    ret_key = f"return_{horizon}"
    result_key = f"result_{horizon}"
    vals = [safe_float(r[ret_key]) for r in rows if r[ret_key] is not None]
    wins = [v for v in vals if v > 0]
    losses = [v for v in vals if v < 0]
    n = len(vals)
    win_rate = (len(wins) / n * 100.0) if n else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_win / gross_loss) if gross_loss else (999 if gross_win > 0 else 0)
    expectancy = (win_rate/100.0 * avg_win) + ((1-win_rate/100.0) * avg_loss)
    return {
        "signals_evaluated": n,
        "win_rate": round(win_rate, 2),
        "avg_win_pct": round(avg_win, 3),
        "avg_loss_pct": round(avg_loss, 3),
        "profit_factor": round(profit_factor, 3) if profit_factor != 999 else 999,
        "expectancy_pct": round(expectancy, 3),
        "sample_warning": "Need more evaluated signals for statistical confidence" if n < 30 else ""
    }

def v131_get_audit_rows(limit=500):
    conn = db()
    rows = conn.execute("SELECT * FROM signal_audit ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
    conn.close()
    return rows

def v131_historical_winrate(symbol=None, strategy=None, horizon="5d"):
    v131_update_audit_results()
    conn = db()
    q = "SELECT * FROM signal_audit WHERE 1=1"
    params = []
    if symbol:
        q += " AND symbol=?"
        params.append(symbol.upper())
    if strategy:
        q += " AND strategy=?"
        params.append(strategy.upper())
    q += " ORDER BY id DESC LIMIT 1000"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    metrics = v131_metrics_from_rows(rows, horizon)
    by_strategy = {}
    for s in sorted(set([r["strategy"] for r in rows if r["strategy"]])):
        sr = [r for r in rows if r["strategy"] == s]
        by_strategy[s] = v131_metrics_from_rows(sr, horizon)
    by_symbol = {}
    for sym in sorted(set([r["symbol"] for r in rows if r["symbol"]]))[:80]:
        sr = [r for r in rows if r["symbol"] == sym]
        by_symbol[sym] = v131_metrics_from_rows(sr, horizon)
    return {"scope": {"symbol": symbol, "strategy": strategy, "horizon": horizon}, "overall": metrics, "by_strategy": by_strategy, "by_symbol": by_symbol}

def v131_false_signal_detector(horizon="5d"):
    v131_update_audit_results()
    rows = v131_get_audit_rows(1000)
    loss_rows = [r for r in rows if r[f"result_{horizon}"] == "LOSS"]
    total_eval = len([r for r in rows if r[f"result_{horizon}"] is not None])
    buckets = {}
    for r in loss_rows:
        keys = [
            f"strategy:{r['strategy'] or 'UNKNOWN'}",
            f"regime:{r['regime'] or 'UNKNOWN'}",
            f"score_band:{(int(r['score'] or 0)//10)*10}"
        ]
        for k in keys:
            buckets.setdefault(k, {"loss_count": 0, "examples": []})
            buckets[k]["loss_count"] += 1
            if len(buckets[k]["examples"]) < 5:
                buckets[k]["examples"].append({"symbol": r["symbol"], "score": r["score"], "return": r[f"return_{horizon}"], "created_at": r["created_at"]})
    ranked = []
    for k, v in buckets.items():
        ranked.append({"pattern": k, "loss_count": v["loss_count"], "loss_share_pct": round(v["loss_count"]/total_eval*100, 2) if total_eval else 0, "examples": v["examples"]})
    ranked.sort(key=lambda x: x["loss_count"], reverse=True)
    return {"horizon": horizon, "evaluated_signals": total_eval, "loss_signals": len(loss_rows), "top_false_signal_patterns": ranked[:20]}

def v131_strategy_leaderboard(horizon="5d"):
    data = v131_historical_winrate(horizon=horizon)
    items = []
    for strategy, metrics in data["by_strategy"].items():
        items.append({"strategy": strategy, **metrics})
    items.sort(key=lambda x: (x.get("expectancy_pct", 0), x.get("profit_factor", 0), x.get("signals_evaluated", 0)), reverse=True)
    return {"horizon": horizon, "leaderboard": items}

def v131_adaptive_thresholds(regime=None, breadth_score=None):
    regime_text = str(regime or "").upper()
    call_threshold = STRICT_CALL_SCORE
    put_threshold = STRICT_PUT_SCORE
    if "RISK_ON" in regime_text or "UPTREND" in regime_text:
        call_threshold = max(82, STRICT_CALL_SCORE - 5)
        put_threshold = min(18, STRICT_PUT_SCORE + 3)
    elif "RISK_OFF" in regime_text or "DOWNTREND" in regime_text or "BEAR" in regime_text:
        call_threshold = min(94, STRICT_CALL_SCORE + 4)
        put_threshold = max(10, STRICT_PUT_SCORE - 4)
    try:
        b = float(breadth_score) if breadth_score is not None else None
        if b is not None and b < 45:
            call_threshold += 3
        elif b is not None and b > 65:
            call_threshold -= 2
    except Exception:
        pass
    return {"call_threshold": int(call_threshold), "put_threshold": int(put_threshold)}

def v131_analyze_symbol(symbol):
    asset = normalize_asset(symbol)
    quote, closes, highs, lows, opens, volumes = get_market_data(asset)
    analysis = analyze_signal(asset, quote, closes, highs, lows, opens, volumes)
    strategy = v131_infer_strategy(analysis.get("score"), analysis.get("bias"), "", analysis.get("regime"), " ".join(analysis.get("reasons", [])))
    thresholds = v131_adaptive_thresholds(analysis.get("regime"), None)
    score = int(analysis.get("score") or 0)
    decision = "WAIT"
    if score >= thresholds["call_threshold"]:
        decision = "CALL_WATCH"
    elif score <= thresholds["put_threshold"]:
        decision = "PUT_WATCH"
    return {"symbol": asset["symbol"], "display": asset["display"], "asset_type": asset["asset_type"], "score": score, "strategy": strategy, "decision": decision, "adaptive_thresholds": thresholds, "analysis": analysis}

def v131_mtf_consensus(symbol):
    asset = normalize_asset(symbol)
    frames = get_mtf(asset)
    details = []
    bulls = bears = mixed = 0
    for label, closes, highs, lows, volumes in frames:
        state = trend_state(closes)
        if state == "BULLISH":
            bulls += 1
        elif state == "BEARISH":
            bears += 1
        else:
            mixed += 1
        details.append({"timeframe": label, "state": state, "last_close": closes[-1] if closes else None})
    total = len(details)
    score = round((bulls - bears) / total * 100, 2) if total else 0
    return {"symbol": symbol.upper(), "timeframes": details, "bullish": bulls, "bearish": bears, "mixed": mixed, "consensus_score": score}

def v131_relative_strength(symbol, benchmark="QQQ", period="3mo"):
    try:
        s = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=False)
        b = yf.Ticker(benchmark).history(period=period, interval="1d", auto_adjust=False)
        if s is None or b is None or s.empty or b.empty:
            return None
        sret = (float(s["Close"].dropna().iloc[-1]) / float(s["Close"].dropna().iloc[0]) - 1) * 100
        bret = (float(b["Close"].dropna().iloc[-1]) / float(b["Close"].dropna().iloc[0]) - 1) * 100
        return {"symbol": symbol, "benchmark": benchmark, "symbol_return_pct": round(sret, 2), "benchmark_return_pct": round(bret, 2), "relative_strength_pct": round(sret - bret, 2)}
    except Exception:
        return None

def v131_market_internals():
    def one(sym):
        try:
            data = yf.Ticker(sym).history(period="3mo", interval="1d", auto_adjust=False)
            if data is None or data.empty:
                return None
            close = data["Close"].dropna()
            last = float(close.iloc[-1])
            prev = float(close.iloc[-2]) if len(close) > 1 else last
            ema20 = float(close.ewm(span=20).mean().iloc[-1]) if len(close) >= 20 else None
            return {"symbol": sym, "last": round(last, 4), "change_pct": round((last-prev)/prev*100, 2) if prev else 0, "above_ema20": bool(ema20 and last > ema20)}
        except Exception:
            return None
    proxies = {
        "vix": "^VIX",
        "dxy": "DX-Y.NYB",
        "tnx": "^TNX",
        "spy": "SPY",
        "qqq": "QQQ",
        "hyg": "HYG",
        "tlt": "TLT",
        "oil": "CL=F",
        "gold": "GC=F"
    }
    data = {k: one(v) for k, v in proxies.items()}
    risk_score = 50
    notes = []
    if data.get("vix") and data["vix"]["change_pct"] > 3:
        risk_score -= 10; notes.append("VIX rising")
    if data.get("qqq") and data["qqq"]["above_ema20"]:
        risk_score += 10; notes.append("QQQ above EMA20")
    if data.get("spy") and data["spy"]["above_ema20"]:
        risk_score += 10; notes.append("SPY above EMA20")
    if data.get("hyg") and data["hyg"]["change_pct"] < -0.5:
        risk_score -= 8; notes.append("Credit proxy weak")
    if data.get("tlt") and data.get("tnx") and data["tnx"]["change_pct"] > 2:
        risk_score -= 5; notes.append("Yield pressure")
    regime = "RISK_ON" if risk_score >= 65 else ("RISK_OFF" if risk_score <= 40 else "MIXED")
    breadth = None
    try:
        if "v121_market_internals" in globals():
            breadth = v121_market_internals()
    except Exception:
        breadth = None
    return {"regime": regime, "risk_score": max(0, min(100, risk_score)), "notes": notes, "proxies": data, "market_breadth": breadth}

def v131_sector_rotation():
    sectors = {
        "XLK_TECH": "XLK", "SMH_SEMIS": "SMH", "XLF_FINANCIALS": "XLF", "XLE_ENERGY": "XLE",
        "XLV_HEALTHCARE": "XLV", "XLY_CONSUMER_DISC": "XLY", "XLP_STAPLES": "XLP",
        "XLI_INDUSTRIALS": "XLI", "XLU_UTILITIES": "XLU", "IYR_REITS": "IYR"
    }
    out = []
    for name, sym in sectors.items():
        rs = v131_relative_strength(sym, "SPY", "3mo")
        if rs:
            out.append({"sector": name, **rs})
    out.sort(key=lambda x: x["relative_strength_pct"], reverse=True)
    return {"leaders": out[:5], "laggards": out[-5:], "all": out}

def v131_opportunity_ranking(limit=20, mode="daily"):
    items = []
    universe = V131_RANKING_UNIVERSE[:80]
    benchmark = "QQQ"
    for sym in universe:
        try:
            res = v131_analyze_symbol(sym)
            rs = v131_relative_strength(sym, benchmark, "3mo") or {}
            mtf = v131_mtf_consensus(sym)
            quality = res["score"] + (rs.get("relative_strength_pct", 0) * 0.35) + (mtf.get("consensus_score", 0) * 0.10)
            if mode == "intraday":
                quality += 3 if res["strategy"] in ("MOMENTUM", "VWAP_RECLAIM") else 0
            if mode == "swing":
                quality += 3 if res["strategy"] in ("CORE_TREND", "PULLBACK") else 0
            items.append({
                "symbol": sym, "score": res["score"], "quality_score": round(quality, 2), "decision": res["decision"],
                "strategy": res["strategy"], "relative_strength_pct": rs.get("relative_strength_pct"),
                "mtf_consensus_score": mtf.get("consensus_score")
            })
        except Exception as e:
            continue
    items.sort(key=lambda x: x["quality_score"], reverse=True)
    put_items = sorted(items, key=lambda x: x["quality_score"])
    return {"mode": mode, "top": items[:int(limit)], "weakest": put_items[:5], "universe_count": len(universe), "generated_at": now_text()}

def v131_parse_portfolio_positions():
    raw = os.getenv("PORTFOLIO_POSITIONS", "")
    # Format: NVDA:10,TSLA:5,QQQ:20 or JSON {"NVDA":10}
    positions = {}
    try:
        if raw.strip().startswith("{"):
            obj = json.loads(raw)
            return {str(k).upper(): float(v) for k, v in obj.items()}
    except Exception:
        pass
    for part in raw.split(","):
        if ":" in part:
            k, v = part.split(":", 1)
            try:
                positions[k.strip().upper()] = float(v.strip())
            except Exception:
                pass
    return positions

def v131_correlation_matrix(symbols=None, period="6mo"):
    symbols = symbols or list(v131_parse_portfolio_positions().keys()) or V131_RANKING_UNIVERSE[:8]
    series = {}
    for sym in symbols[:20]:
        try:
            data = yf.Ticker(sym).history(period=period, interval="1d", auto_adjust=False)
            if data is not None and not data.empty:
                close = data["Close"].dropna()
                rets = close.pct_change().dropna()
                series[sym] = rets
        except Exception:
            pass
    matrix = {}
    keys = list(series.keys())
    for a in keys:
        matrix[a] = {}
        for b in keys:
            try:
                joined = series[a].align(series[b], join="inner")
                corr = joined[0].corr(joined[1])
                matrix[a][b] = round(float(corr), 3) if corr == corr else None
            except Exception:
                matrix[a][b] = None
    return {"symbols": keys, "correlation_matrix": matrix}

def v131_position_sizing(symbol, account_size=None, risk_pct=None):
    account_size = float(account_size or V131_ACCOUNT_SIZE)
    risk_pct = float(risk_pct or V131_RISK_PER_TRADE_PCT)
    try:
        asset = normalize_asset(symbol)
        quote, closes, highs, lows, opens, volumes = get_market_data(asset)
        atr = calc_atr(highs, lows, closes) or (safe_float(quote.get("close")) * 0.02)
        price = safe_float(quote.get("close"))
        risk_dollars = account_size * (risk_pct/100)
        stop_distance = atr * 1.2 if atr else price * 0.02
        shares = int(risk_dollars / stop_distance) if stop_distance else 0
        notional = shares * price if price else 0
        return {"symbol": symbol.upper(), "account_size": account_size, "risk_pct": risk_pct, "risk_dollars": round(risk_dollars, 2), "price": price, "atr": atr, "stop_distance": stop_distance, "suggested_shares": shares, "notional": round(notional, 2), "portfolio_pct": round(notional/account_size*100, 2) if account_size else 0}
    except Exception as e:
        return {"symbol": symbol.upper(), "error": str(e)}

def v131_portfolio_heat():
    positions = v131_parse_portfolio_positions()
    if not positions:
        return {"configured": False, "message": "Set PORTFOLIO_POSITIONS as NVDA:10,TSLA:5,QQQ:20 to enable portfolio heat."}
    details = []
    total_value = 0.0
    for sym, qty in positions.items():
        price = v131_current_price(sym) or 0
        value = price * qty
        total_value += value
        details.append({"symbol": sym, "qty": qty, "price": price, "value": value})
    for d in details:
        d["weight_pct"] = round(d["value"]/total_value*100, 2) if total_value else 0
    concentration = max([d["weight_pct"] for d in details], default=0)
    heat = "HIGH" if concentration > 35 else ("MEDIUM" if concentration > 20 else "LOW")
    corr = v131_correlation_matrix(list(positions.keys()))
    return {"configured": True, "total_value": round(total_value, 2), "concentration_max_pct": concentration, "portfolio_heat": heat, "positions": details, "correlation": corr}

def v131_performance_dashboard():
    v131_update_audit_results()
    winrate = v131_historical_winrate(horizon="5d")
    false_signals = v131_false_signal_detector(horizon="5d")
    leaderboard = v131_strategy_leaderboard(horizon="5d")
    internals = v131_market_internals()
    rotation = v131_sector_rotation()
    ranking_daily = v131_opportunity_ranking(20, "daily")
    ranking_intraday = v131_opportunity_ranking(5, "intraday")
    ranking_swing = v131_opportunity_ranking(5, "swing")
    portfolio = v131_portfolio_heat()
    return {
        "version": "V13.1 Signal Quality + Institutional Analytics Free 100%",
        "time": now_text(),
        "performance": winrate["overall"],
        "strategy_leaderboard": leaderboard["leaderboard"][:10],
        "false_signal_detector": false_signals["top_false_signal_patterns"][:10],
        "institutional_internals": internals,
        "sector_rotation": {"leaders": rotation["leaders"], "laggards": rotation["laggards"]},
        "opportunity_ranking": {
            "top_20_daily": ranking_daily["top"],
            "top_5_intraday": ranking_intraday["top"],
            "top_5_swing": ranking_swing["top"]
        },
        "portfolio_engine": portfolio,
        "note": "Win-rate/expectancy becomes meaningful only after enough real signals are audited over time."
    }

@app.route("/v13-1/status", methods=["GET"])
def v131_status_route():
    return jsonify({
        "version": "V13.1 Signal Quality + Institutional Analytics Free 100%",
        "enabled": V131_ENABLED,
        "modules": [
            "Signal Audit Engine", "Historical Win Rate", "Expectancy", "False Signal Detector",
            "Strategy Leaderboard", "VIX/DXY/TNX Internals", "Market Breadth", "Sector Rotation",
            "Top 20 Daily", "Top 5 Intraday", "Top 5 Swing", "Correlation Matrix",
            "Position Sizing", "Portfolio Heat", "Performance Dashboard"
        ],
        "routes": [
            "/v13-1/dashboard", "/v13-1/audit", "/v13-1/winrate", "/v13-1/false-signals",
            "/v13-1/leaderboard", "/v13-1/internals", "/v13-1/sector-rotation",
            "/v13-1/ranking/daily", "/v13-1/ranking/intraday", "/v13-1/ranking/swing",
            "/v13-1/correlation", "/v13-1/position-size/<symbol>", "/v13-1/portfolio-heat",
            "/v13-1/mtf/<symbol>", "/v13-1/rs/<symbol>"
        ]
    })

@app.route("/v13-1/dashboard", methods=["GET"])
def v131_dashboard_route():
    return jsonify(v131_performance_dashboard())

@app.route("/v13-1/audit", methods=["GET"])
def v131_audit_route():
    limit = int(request.args.get("limit", "100"))
    v131_update_audit_results()
    rows = v131_get_audit_rows(limit)
    return jsonify({"count": len(rows), "rows": [dict(r) for r in rows]})

@app.route("/v13-1/winrate", methods=["GET"])
def v131_winrate_route():
    return jsonify(v131_historical_winrate(request.args.get("symbol"), request.args.get("strategy"), request.args.get("horizon", "5d")))

@app.route("/v13-1/false-signals", methods=["GET"])
def v131_false_signals_route():
    return jsonify(v131_false_signal_detector(request.args.get("horizon", "5d")))

@app.route("/v13-1/leaderboard", methods=["GET"])
def v131_leaderboard_route():
    return jsonify(v131_strategy_leaderboard(request.args.get("horizon", "5d")))

@app.route("/v13-1/internals", methods=["GET"])
def v131_internals_route():
    return jsonify(v131_market_internals())

@app.route("/v13-1/sector-rotation", methods=["GET"])
def v131_sector_rotation_route():
    return jsonify(v131_sector_rotation())

@app.route("/v13-1/ranking/<mode>", methods=["GET"])
def v131_ranking_route(mode):
    limit = int(request.args.get("limit", "20" if mode == "daily" else "5"))
    return jsonify(v131_opportunity_ranking(limit, mode))

@app.route("/v13-1/correlation", methods=["GET"])
def v131_correlation_route():
    symbols = request.args.get("symbols", "")
    symbols = [x.strip().upper() for x in symbols.split(",") if x.strip()] if symbols else None
    return jsonify(v131_correlation_matrix(symbols))

@app.route("/v13-1/position-size/<symbol>", methods=["GET"])
def v131_position_size_route(symbol):
    return jsonify(v131_position_sizing(symbol, request.args.get("account"), request.args.get("risk_pct")))

@app.route("/v13-1/portfolio-heat", methods=["GET"])
def v131_portfolio_heat_route():
    return jsonify(v131_portfolio_heat())

@app.route("/v13-1/mtf/<symbol>", methods=["GET"])
def v131_mtf_route(symbol):
    return jsonify(v131_mtf_consensus(symbol))

@app.route("/v13-1/rs/<symbol>", methods=["GET"])
def v131_rs_route(symbol):
    return jsonify(v131_relative_strength(symbol.upper(), request.args.get("benchmark", "QQQ")) or {"error": "no data"})

@app.route("/v13-1/analyze/<symbol>", methods=["GET"])
def v131_analyze_route(symbol):
    return jsonify(v131_analyze_symbol(symbol))



# ============================================================
# V14 TRADE JOURNAL + OUTCOME TRACKING + EXPECTANCY + ADAPTIVE SCORING
# Purpose: turn V13.1 analytics into a measurable trade-research journal.
# Free 100%: SQLite + yfinance + existing signal engine. No paid API required.
# ============================================================
V14_ENABLED = os.getenv("V14_ENABLED", "true").lower() == "true"
V14_HORIZONS = [int(x) for x in os.getenv("V14_HORIZONS", "1,3,5,10,20").split(",") if str(x).strip().isdigit()]
V14_MIN_SAMPLE = int(os.getenv("V14_MIN_SAMPLE", "10"))
V14_AUTO_LOG_SIGNALS = os.getenv("V14_AUTO_LOG_SIGNALS", "true").lower() == "true"
V14_DEDUP_MINUTES = int(os.getenv("V14_DEDUP_MINUTES", "30"))


def v14_init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trade_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            created_ts REAL NOT NULL,
            source TEXT,
            symbol TEXT NOT NULL,
            asset_type TEXT,
            side TEXT,
            strategy TEXT,
            entry_price REAL,
            stop_loss REAL,
            take_profit REAL,
            size REAL,
            score INTEGER,
            adaptive_score INTEGER,
            quality_score INTEGER,
            regime TEXT,
            status TEXT DEFAULT 'OPEN',
            notes TEXT,
            result_1d TEXT,
            return_1d REAL,
            price_1d REAL,
            result_3d TEXT,
            return_3d REAL,
            price_3d REAL,
            result_5d TEXT,
            return_5d REAL,
            price_5d REAL,
            result_10d TEXT,
            return_10d REAL,
            price_10d REAL,
            result_20d TEXT,
            return_20d REAL,
            price_20d REAL,
            updated_at TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_trade_journal_symbol ON trade_journal(symbol)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_trade_journal_created ON trade_journal(created_ts)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_trade_journal_strategy ON trade_journal(strategy)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_trade_journal_status ON trade_journal(status)")
    conn.commit()
    conn.close()


def v14_side_from_text(side=None, signal_type=None, bias=None, score=None):
    txt = f"{side or ''} {signal_type or ''} {bias or ''}".upper()
    if "CALL" in txt or "BUY" in txt or "BULL" in txt or "ซื้อ" in txt:
        return "CALL"
    if "PUT" in txt or "SELL" in txt or "BEAR" in txt or "ขาย" in txt:
        return "PUT"
    try:
        sc = int(score or 50)
        if sc >= 75:
            return "CALL"
        if sc <= 35:
            return "PUT"
    except Exception:
        pass
    return "WAIT"


def v14_infer_strategy(score=None, bias=None, signal_type=None, regime=None, report=None):
    try:
        if "v131_infer_strategy" in globals():
            return v131_infer_strategy(score, bias, signal_type, regime, report)
    except Exception:
        pass
    txt = f"{bias or ''} {signal_type or ''} {regime or ''} {report or ''}".upper()
    try:
        sc = int(score or 50)
    except Exception:
        sc = 50
    if "VWAP" in txt:
        return "VWAP_RECLAIM"
    if "PULLBACK" in txt or "ย่อ" in txt:
        return "PULLBACK"
    if "BREAKOUT" in txt or "ทะลุ" in txt:
        return "BREAKOUT"
    if "MOMENTUM" in txt or sc >= 85 or sc <= 20:
        return "MOMENTUM"
    if "RANGE" in txt:
        return "RANGE_REVERSAL"
    return "CORE_TREND"


def v14_current_price(symbol):
    try:
        return v131_current_price(symbol)
    except Exception:
        pass
    try:
        asset = normalize_asset(symbol)
        quote, closes, highs, lows, opens, volumes = get_market_data(asset)
        return safe_float(quote.get("close"))
    except Exception:
        return None


def v14_result_for_return(side, ret):
    if ret is None:
        return None
    side = str(side or "CALL").upper()
    if side == "PUT":
        return "WIN" if ret < 0 else "LOSS"
    if side == "CALL":
        return "WIN" if ret > 0 else "LOSS"
    return "FLAT" if abs(ret) < 0.05 else "UNTRACKED"


def v14_dedupe_exists(symbol, side, strategy, created_ts=None):
    created_ts = created_ts or time.time()
    window = max(1, V14_DEDUP_MINUTES) * 60
    try:
        conn = db()
        row = conn.execute(
            """SELECT id FROM trade_journal
               WHERE symbol=? AND side=? AND strategy=? AND ABS(created_ts - ?) <= ?
               ORDER BY id DESC LIMIT 1""",
            (str(symbol).upper(), side, strategy, float(created_ts), window),
        ).fetchone()
        conn.close()
        return bool(row)
    except Exception:
        return False


def v14_log_trade(symbol, side=None, entry_price=None, strategy=None, source="manual", asset_type=None,
                  score=None, adaptive_score=None, quality_score=None, regime=None, stop_loss=None,
                  take_profit=None, size=None, notes=None, created_ts=None):
    if not V14_ENABLED:
        return {"logged": False, "reason": "V14_DISABLED"}
    sym = resolve_delisted_symbol(symbol).upper().replace(".SET", ".BK")
    side = v14_side_from_text(side=side, score=score)
    strategy = (strategy or v14_infer_strategy(score, side, side, regime, notes)).upper()
    created_ts = float(created_ts or time.time())
    if entry_price is None:
        entry_price = v14_current_price(sym)
    entry = safe_float(entry_price)
    if entry is None or entry <= 0:
        return {"logged": False, "reason": "NO_ENTRY_PRICE", "symbol": sym}
    if v14_dedupe_exists(sym.replace(".BK", ""), side, strategy, created_ts):
        return {"logged": False, "reason": "DUPLICATE_WITHIN_WINDOW", "symbol": sym, "side": side, "strategy": strategy}
    try:
        conn = db()
        conn.execute(
            """INSERT INTO trade_journal
               (created_at, created_ts, source, symbol, asset_type, side, strategy, entry_price,
                stop_loss, take_profit, size, score, adaptive_score, quality_score, regime, status, notes, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)""",
            (
                now_text(), created_ts, source, sym.replace(".BK", ""), asset_type, side, strategy, entry,
                safe_float(stop_loss), safe_float(take_profit), safe_float(size), int(score or 0) if score is not None else None,
                int(adaptive_score or 0) if adaptive_score is not None else None,
                int(quality_score or 0) if quality_score is not None else None,
                regime, str(notes or "")[:2000], v131_now_iso() if "v131_now_iso" in globals() else datetime.now(timezone.utc).isoformat(),
            ),
        )
        journal_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        conn.commit(); conn.close()
        return {"logged": True, "id": journal_id, "symbol": sym.replace(".BK", ""), "side": side, "strategy": strategy, "entry_price": entry}
    except Exception as e:
        return {"logged": False, "error": str(e)[:240]}


def v14_auto_log_trade(symbol, asset_type, price, score, bias, signal_type, regime, probability, report, source="signal"):
    if not (V14_ENABLED and V14_AUTO_LOG_SIGNALS):
        return {"logged": False, "reason": "AUTO_LOG_DISABLED"}
    side = v14_side_from_text(signal_type=signal_type, bias=bias, score=score)
    if side == "WAIT":
        return {"logged": False, "reason": "WAIT_SIGNAL"}
    strategy = v14_infer_strategy(score, bias, signal_type, regime, report)
    adaptive_score = None
    quality_score = None
    try:
        if "v131_analyze_symbol" in globals():
            snap = v131_analyze_symbol(str(symbol).upper().replace(".BK", ""))
            adaptive_score = snap.get("score")
            quality_score = snap.get("quality_score") or snap.get("score")
    except Exception:
        pass
    return v14_log_trade(
        symbol=symbol, side=side, entry_price=price, strategy=strategy, source=source,
        asset_type=asset_type, score=score, adaptive_score=adaptive_score, quality_score=quality_score,
        regime=regime, notes=str(report or "")[:1000]
    )


def v14_backfill_from_signal_audit(limit=500):
    """Copy old V13.1 signal_audit rows into trade_journal once, so V14 is not empty."""
    copied = 0
    skipped = 0
    try:
        conn = db()
        rows = conn.execute("SELECT * FROM signal_audit ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
        conn.close()
        for r in rows:
            side = v14_side_from_text(signal_type=r["signal_type"], bias=r["bias"], score=r["score"])
            if side == "WAIT":
                skipped += 1
                continue
            res = v14_log_trade(
                symbol=r["symbol"], side=side, entry_price=r["entry_price"], strategy=r["strategy"],
                source="backfill_signal_audit", asset_type=r["asset_type"], score=r["score"],
                adaptive_score=r["score"], quality_score=r["score"], regime=r["regime"],
                notes=(r["report"] or "")[:1000], created_ts=safe_float(r["created_ts"], time.time())
            )
            copied += 1 if res.get("logged") else 0
            skipped += 0 if res.get("logged") else 1
        return {"copied": copied, "skipped": skipped, "checked": len(rows)}
    except Exception as e:
        return {"copied": copied, "skipped": skipped, "error": str(e)[:240]}


def v14_update_outcomes(limit=500):
    if not V14_ENABLED:
        return {"updated": 0, "enabled": False}
    now_ts = time.time()
    updated = 0
    checked = 0
    conn = db()
    rows = conn.execute("SELECT * FROM trade_journal WHERE status!='CLOSED' ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
    for r in rows:
        checked += 1
        try:
            age_days = (now_ts - float(r["created_ts"] or now_ts)) / 86400.0
            px = v14_current_price(r["symbol"])
            entry = safe_float(r["entry_price"])
            if not px or not entry:
                continue
            ret = (px - entry) / entry * 100.0
            fields = {}
            max_done = 0
            for h in V14_HORIZONS:
                if age_days >= (h - 0.05) and r[f"return_{h}d"] is None:
                    fields[f"price_{h}d"] = px
                    fields[f"return_{h}d"] = ret
                    fields[f"result_{h}d"] = v14_result_for_return(r["side"], ret)
                if r[f"return_{h}d"] is not None or f"return_{h}d" in fields:
                    max_done = max(max_done, h)
            if max_done >= max(V14_HORIZONS):
                fields["status"] = "CLOSED"
            if fields:
                fields["updated_at"] = v131_now_iso() if "v131_now_iso" in globals() else datetime.now(timezone.utc).isoformat()
                sets = ", ".join([f"{k}=?" for k in fields.keys()])
                conn.execute(f"UPDATE trade_journal SET {sets} WHERE id=?", list(fields.values()) + [r["id"]])
                updated += 1
        except Exception as e:
            print("V14 outcome update row error:", e)
    conn.commit(); conn.close()
    return {"updated": updated, "checked": checked, "horizons": V14_HORIZONS, "enabled": True}


def v14_get_journal_rows(symbol=None, strategy=None, status=None, limit=500):
    conn = db()
    q = "SELECT * FROM trade_journal WHERE 1=1"
    params = []
    if symbol:
        q += " AND symbol=?"; params.append(resolve_delisted_symbol(symbol).upper().replace(".BK", ""))
    if strategy:
        q += " AND strategy=?"; params.append(str(strategy).upper())
    if status:
        q += " AND status=?"; params.append(str(status).upper())
    q += " ORDER BY id DESC LIMIT ?"; params.append(int(limit))
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return rows


def v14_metrics_from_rows(rows, horizon="5d"):
    ret_key = f"return_{horizon}"
    result_key = f"result_{horizon}"
    eval_rows = [r for r in rows if r[ret_key] is not None]
    vals = [safe_float(r[ret_key], 0) for r in eval_rows]
    wins = [v for r, v in zip(eval_rows, vals) if str(r[result_key]).upper() == "WIN"]
    losses = [v for r, v in zip(eval_rows, vals) if str(r[result_key]).upper() == "LOSS"]
    n = len(vals)
    win_rate = len(wins) / n * 100 if n else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    gross_win = sum(abs(v) for v in wins)
    gross_loss = sum(abs(v) for v in losses)
    profit_factor = gross_win / gross_loss if gross_loss else (999 if gross_win > 0 else 0)
    p_win = win_rate / 100.0
    expectancy = (p_win * avg_win) - ((1 - p_win) * abs(avg_loss))
    return {
        "signals_total": len(rows),
        "signals_evaluated": n,
        "open_signals": sum(1 for r in rows if str(r["status"]).upper() == "OPEN"),
        "win_rate_pct": round(win_rate, 2),
        "avg_win_pct": round(avg_win, 3),
        "avg_loss_pct": round(avg_loss, 3),
        "profit_factor": round(profit_factor, 3) if profit_factor != 999 else 999,
        "expectancy_pct": round(expectancy, 3),
        "sample_quality": "LOW" if n < V14_MIN_SAMPLE else "OK",
        "sample_warning": f"Need at least {V14_MIN_SAMPLE} evaluated trades for confidence" if n < V14_MIN_SAMPLE else ""
    }


def v14_expectancy(symbol=None, strategy=None, horizon="5d"):
    v14_update_outcomes()
    rows = v14_get_journal_rows(symbol=symbol, strategy=strategy, limit=2000)
    overall = v14_metrics_from_rows(rows, horizon)
    by_strategy = {}
    for st in sorted(set([r["strategy"] for r in rows if r["strategy"]])):
        sr = [r for r in rows if r["strategy"] == st]
        by_strategy[st] = v14_metrics_from_rows(sr, horizon)
    by_symbol = {}
    for sym in sorted(set([r["symbol"] for r in rows if r["symbol"]])):
        sr = [r for r in rows if r["symbol"] == sym]
        by_symbol[sym] = v14_metrics_from_rows(sr, horizon)
    by_side = {}
    for sd in sorted(set([r["side"] for r in rows if r["side"]])):
        sr = [r for r in rows if r["side"] == sd]
        by_side[sd] = v14_metrics_from_rows(sr, horizon)
    return {"version": "V14 Expectancy Engine", "scope": {"symbol": symbol, "strategy": strategy, "horizon": horizon}, "overall": overall, "by_strategy": by_strategy, "by_symbol": by_symbol, "by_side": by_side}


def v14_strategy_modifier(strategy=None, horizon="5d"):
    if not strategy:
        return {"modifier": 0, "reason": "No strategy"}
    exp = v14_expectancy(strategy=strategy, horizon=horizon)["overall"]
    n = int(exp.get("signals_evaluated") or 0)
    expectancy = float(exp.get("expectancy_pct") or 0)
    pf = float(exp.get("profit_factor") or 0)
    wr = float(exp.get("win_rate_pct") or 0)
    if n < V14_MIN_SAMPLE:
        return {"modifier": 0, "reason": "Insufficient sample", "metrics": exp}
    modifier = 0
    reasons = []
    if expectancy >= 2.0 and pf >= 1.5:
        modifier += 10; reasons.append("Strong positive expectancy")
    elif expectancy >= 0.75:
        modifier += 5; reasons.append("Positive expectancy")
    elif expectancy <= -1.0 or pf < 0.8:
        modifier -= 10; reasons.append("Negative expectancy / weak profit factor")
    elif expectancy < 0:
        modifier -= 5; reasons.append("Slightly negative expectancy")
    if wr >= 65:
        modifier += 3; reasons.append("High win rate")
    elif wr <= 40:
        modifier -= 3; reasons.append("Low win rate")
    return {"modifier": int(max(-15, min(15, modifier))), "reason": "; ".join(reasons) or "Neutral historical edge", "metrics": exp}


def v14_adaptive_score(symbol):
    base = v131_analyze_symbol(symbol) if "v131_analyze_symbol" in globals() else {}
    strategy = base.get("strategy") or "CORE_TREND"
    score = safe_float(base.get("score"), 50)
    mod = v14_strategy_modifier(strategy)
    adaptive = int(max(0, min(100, score + mod.get("modifier", 0))))
    decision = "CALL_WATCH" if adaptive >= 75 else "PUT_WATCH" if adaptive <= 30 else "WAIT"
    return {
        "version": "V14 Adaptive Scoring",
        "symbol": symbol.upper(),
        "base_score": score,
        "strategy": strategy,
        "historical_modifier": mod,
        "adaptive_score": adaptive,
        "decision": decision,
        "note": "Adaptive score = current setup score + historical expectancy modifier. It becomes stronger after enough journal outcomes."
    }


def v14_leaderboard(horizon="5d"):
    exp = v14_expectancy(horizon=horizon)
    rows = []
    for strategy, metrics in exp.get("by_strategy", {}).items():
        rows.append({"strategy": strategy, **metrics})
    rows.sort(key=lambda x: (x.get("expectancy_pct", 0), x.get("profit_factor", 0), x.get("signals_evaluated", 0)), reverse=True)
    return {"version": "V14 Strategy Leaderboard", "horizon": horizon, "leaderboard": rows}


def v14_dashboard():
    exp = v14_expectancy(horizon=request.args.get("horizon", "5d"))
    journal = v14_get_journal_rows(limit=50)
    leaderboard = v14_leaderboard(request.args.get("horizon", "5d"))
    return {
        "version": "V14 Trade Journal + Outcome Tracking + Expectancy + Adaptive Scoring Free 100%",
        "time": now_text(),
        "summary": exp.get("overall"),
        "best_strategy": (leaderboard.get("leaderboard") or [{}])[0],
        "worst_strategy": (leaderboard.get("leaderboard") or [{}])[-1] if leaderboard.get("leaderboard") else {},
        "strategy_leaderboard": leaderboard.get("leaderboard"),
        "latest_trades": [dict(r) for r in journal[:20]],
        "routes": ["/v14/status", "/v14/journal", "/v14/journal/log/<symbol>", "/v14/update-outcomes", "/v14/expectancy", "/v14/leaderboard", "/v14/adaptive/<symbol>", "/v14/backfill", "/v14/dashboard"]
    }


@app.route("/v14/status", methods=["GET"])
def v14_status_route():
    return jsonify({
        "version": "V14 Trade Journal + Outcome Tracking + Expectancy + Adaptive Scoring Free 100%",
        "enabled": V14_ENABLED,
        "auto_log_signals": V14_AUTO_LOG_SIGNALS,
        "horizons_days": V14_HORIZONS,
        "modules": ["Trade Journal", "Outcome Tracking", "Expectancy", "Adaptive Scoring"],
        "routes": ["/v14/dashboard", "/v14/journal", "/v14/journal/log/<symbol>", "/v14/update-outcomes", "/v14/expectancy", "/v14/leaderboard", "/v14/adaptive/<symbol>", "/v14/backfill"]
    })


@app.route("/v14/dashboard", methods=["GET"])
def v14_dashboard_route():
    return jsonify(v14_dashboard())


@app.route("/v14/journal", methods=["GET", "POST"])
def v14_journal_route():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        res = v14_log_trade(
            symbol=payload.get("symbol"), side=payload.get("side"), entry_price=payload.get("entry_price"),
            strategy=payload.get("strategy"), source="manual_post", score=payload.get("score"),
            stop_loss=payload.get("stop_loss"), take_profit=payload.get("take_profit"),
            size=payload.get("size"), notes=payload.get("notes")
        )
        return jsonify(res)
    rows = v14_get_journal_rows(request.args.get("symbol"), request.args.get("strategy"), request.args.get("status"), request.args.get("limit", 200))
    return jsonify({"count": len(rows), "rows": [dict(r) for r in rows]})


@app.route("/v14/journal/log/<symbol>", methods=["GET", "POST"])
def v14_journal_log_symbol_route(symbol):
    payload = request.get_json(silent=True) or {}
    side = payload.get("side") or request.args.get("side")
    entry = payload.get("entry_price") or request.args.get("entry") or request.args.get("entry_price")
    strategy = payload.get("strategy") or request.args.get("strategy")
    notes = payload.get("notes") or request.args.get("notes")
    score = payload.get("score") or request.args.get("score")
    res = v14_log_trade(symbol=symbol, side=side, entry_price=entry, strategy=strategy, source="manual_route", score=score, notes=notes)
    return jsonify(res)


@app.route("/v14/update-outcomes", methods=["GET", "POST"])
def v14_update_outcomes_route():
    return jsonify(v14_update_outcomes(request.args.get("limit", 500)))


@app.route("/v14/expectancy", methods=["GET"])
def v14_expectancy_route():
    return jsonify(v14_expectancy(request.args.get("symbol"), request.args.get("strategy"), request.args.get("horizon", "5d")))


@app.route("/v14/leaderboard", methods=["GET"])
def v14_leaderboard_route():
    return jsonify(v14_leaderboard(request.args.get("horizon", "5d")))


@app.route("/v14/adaptive/<symbol>", methods=["GET"])
def v14_adaptive_route(symbol):
    return jsonify(v14_adaptive_score(symbol))


@app.route("/v14/backfill", methods=["GET", "POST"])
def v14_backfill_route():
    return jsonify(v14_backfill_from_signal_audit(request.args.get("limit", 500)))


init_db()
v131_init_db()
v14_init_db()
v10_init_db()
v11_init_db()



# ============================================================
# V14.1 SIGNAL LOGIC PATCH STATUS
# ============================================================
@app.route("/v14-1/status", methods=["GET"])
def v141_status_route():
    return jsonify({
        "version": "V14.1 Signal Logic Fix Free 100%",
        "enabled": True,
        "fixes": [
            "Dividend Yield sanity filter: suppress unrealistic ETF/unit glitches such as QQQ 42%",
            "Bull/Bear spread strike width guard: prevents Buy 730C / Sell 730C zero-width spread",
            "ATR-based TP1/TP2/TP3 widened to 1R/2R/3R proxy",
            "Volume reason conflict fixed: high volume on red bar no longer says bullish confirmation",
            "Oversold SELL/PUT protection: reduces size and forces wait-for-rebound sell logic",
            "Range/Low Vol note added for options entries"
        ],
        "test_routes": ["/v14/status", "/v14/dashboard", "/v14-1/status", "/v10/options/NVDA", "/v13-1/ranking/daily"]
    })

if __name__ == "__main__":
    if ENABLE_AUTO_ALERTS and ALERT_USER_IDS:
        threading.Thread(target=auto_alert_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
