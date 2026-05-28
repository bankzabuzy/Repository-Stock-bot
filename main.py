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


# ============================================================
# V15 RESEARCH DASHBOARD LAYER - HTML TERMINAL UI
# ============================================================
# Purpose: turn the JSON API engine into a readable institutional-style dashboard.
# No extra dependency. Uses existing V10/V12/V13.1/V14 engines.

V15_VERSION = "V15 Research Dashboard Layer Free 100%"


def v15_escape(value):
    text = "" if value is None else str(value)
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&#39;"))


def v15_num(value, digits=2):
    try:
        if value is None:
            return "N/A"
        return f"{float(value):,.{digits}f}"
    except Exception:
        return v15_escape(value)


def v15_pct(value, digits=2):
    try:
        if value is None:
            return "N/A"
        return f"{float(value):,.{digits}f}%"
    except Exception:
        return v15_escape(value)


def v15_badge_class(value):
    text = str(value or "").upper()
    if any(x in text for x in ["CALL", "BULL", "RISK_ON", "WIN", "STRONG", "LOW", "BUY"]):
        return "good"
    if any(x in text for x in ["PUT", "BEAR", "RISK_OFF", "LOSS", "HIGH", "SELL"]):
        return "bad"
    if any(x in text for x in ["WAIT", "MIXED", "NEUTRAL", "RANGE"]):
        return "warn"
    return "neutral"


def v15_card(title, value, subtitle="", klass=""):
    return f"""
    <div class=\"card {klass}\">
      <div class=\"card-title\">{v15_escape(title)}</div>
      <div class=\"card-value\">{v15_escape(value)}</div>
      <div class=\"card-subtitle\">{v15_escape(subtitle)}</div>
    </div>
    """


def v15_badge(text):
    return f"<span class='badge {v15_badge_class(text)}'>{v15_escape(text)}</span>"


def v15_table(rows, columns, empty="No data yet"):
    if not rows:
        return f"<div class='empty'>{v15_escape(empty)}</div>"
    head = "".join(f"<th>{v15_escape(label)}</th>" for key, label in columns)
    body = []
    for r in rows:
        tds = []
        for key, label in columns:
            val = r.get(key) if isinstance(r, dict) else getattr(r, key, None)
            if key in {"decision", "strategy", "side", "signal_type", "status", "regime", "breadth_regime"}:
                cell = v15_badge(val)
            elif isinstance(val, float):
                cell = v15_num(val)
            else:
                cell = v15_escape(val)
            tds.append(f"<td>{cell}</td>")
        body.append("<tr>" + "".join(tds) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def v15_layout(title, body, active="dashboard", refresh=False):
    refresh_tag = "<meta http-equiv='refresh' content='180'>" if refresh else ""
    nav = [
        ("Dashboard", "/v15/dashboard", "dashboard"),
        ("Ranking", "/v15/ranking", "ranking"),
        ("Journal", "/v15/journal", "journal"),
        ("Portfolio", "/v15/portfolio", "portfolio"),
        ("Correlation", "/v15/correlation", "correlation"),
        ("Terminal", "/v15", "terminal"),
    ]
    links = "".join(
        f"<a class='nav-link {'active' if active == key else ''}' href='{href}'>{label}</a>"
        for label, href, key in nav
    )
    html = f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
{refresh_tag}
<title>{v15_escape(title)}</title>
<style>
:root {{
  --bg:#080b12; --panel:#111827; --panel2:#0f172a; --text:#e5e7eb; --muted:#94a3b8;
  --line:#1f2937; --good:#22c55e; --bad:#ef4444; --warn:#f59e0b; --blue:#38bdf8; --purple:#a78bfa;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:linear-gradient(180deg,#070a12,#0b1020); color:var(--text); font-family:Arial, Helvetica, sans-serif; }}
a {{ color:inherit; text-decoration:none; }}
.header {{ position:sticky; top:0; z-index:10; display:flex; align-items:center; justify-content:space-between; padding:14px 18px; background:rgba(8,11,18,.92); border-bottom:1px solid var(--line); backdrop-filter: blur(8px); }}
.brand {{ display:flex; gap:12px; align-items:center; }}
.logo {{ width:36px; height:36px; border-radius:12px; background:linear-gradient(135deg,var(--blue),var(--purple)); display:flex; align-items:center; justify-content:center; font-weight:800; }}
.brand h1 {{ font-size:17px; margin:0; }}
.brand p {{ font-size:12px; margin:2px 0 0; color:var(--muted); }}
.nav {{ display:flex; gap:8px; flex-wrap:wrap; }}
.nav-link {{ padding:8px 10px; border:1px solid var(--line); border-radius:999px; color:var(--muted); font-size:13px; }}
.nav-link.active, .nav-link:hover {{ color:white; border-color:#334155; background:#111827; }}
.container {{ max-width:1280px; margin:0 auto; padding:18px; }}
.grid {{ display:grid; gap:14px; }}
.grid-4 {{ grid-template-columns:repeat(4,minmax(0,1fr)); }}
.grid-3 {{ grid-template-columns:repeat(3,minmax(0,1fr)); }}
.grid-2 {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
.card {{ background:linear-gradient(180deg,var(--panel),var(--panel2)); border:1px solid var(--line); border-radius:18px; padding:16px; box-shadow:0 16px 40px rgba(0,0,0,.22); }}
.card-title {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.08em; }}
.card-value {{ font-size:25px; font-weight:800; margin-top:8px; }}
.card-subtitle {{ color:var(--muted); font-size:12px; margin-top:6px; line-height:1.35; }}
.section {{ margin-top:16px; background:rgba(17,24,39,.66); border:1px solid var(--line); border-radius:18px; overflow:hidden; }}
.section h2 {{ margin:0; padding:14px 16px; border-bottom:1px solid var(--line); font-size:16px; }}
.section-body {{ padding:14px; overflow:auto; }}
table {{ width:100%; border-collapse:collapse; min-width:760px; }}
th,td {{ padding:10px 9px; text-align:left; border-bottom:1px solid #1e293b; font-size:13px; vertical-align:top; }}
th {{ color:#cbd5e1; font-size:12px; text-transform:uppercase; letter-spacing:.04em; background:#0b1220; position:sticky; top:0; }}
.badge {{ display:inline-flex; align-items:center; padding:4px 8px; border-radius:999px; font-size:12px; font-weight:700; border:1px solid #334155; }}
.badge.good {{ color:#86efac; background:rgba(34,197,94,.11); border-color:rgba(34,197,94,.35); }}
.badge.bad {{ color:#fecaca; background:rgba(239,68,68,.12); border-color:rgba(239,68,68,.35); }}
.badge.warn {{ color:#fde68a; background:rgba(245,158,11,.12); border-color:rgba(245,158,11,.35); }}
.badge.neutral {{ color:#cbd5e1; background:rgba(148,163,184,.10); }}
.empty {{ color:var(--muted); padding:20px; border:1px dashed #334155; border-radius:14px; }}
.actions {{ display:flex; gap:10px; flex-wrap:wrap; margin:10px 0 0; }}
.button {{ background:#172554; border:1px solid #1d4ed8; color:#bfdbfe; padding:8px 11px; border-radius:10px; font-size:13px; }}
.code {{ font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; color:#d1d5db; background:#020617; border:1px solid var(--line); border-radius:12px; padding:12px; overflow:auto; white-space:pre-wrap; }}
.footer {{ color:var(--muted); font-size:12px; text-align:center; padding:22px; }}
@media(max-width:900px) {{ .grid-4,.grid-3,.grid-2 {{ grid-template-columns:1fr; }} .header {{ align-items:flex-start; flex-direction:column; gap:12px; }} table {{ min-width:680px; }} }}
</style>
</head>
<body>
<div class=\"header\">
  <div class=\"brand\"><div class=\"logo\">V15</div><div><h1>Research Dashboard Terminal</h1><p>{v15_escape(V15_VERSION)} · {v15_escape(now_text())}</p></div></div>
  <div class=\"nav\">{links}</div>
</div>
<div class=\"container\">{body}</div>
<div class=\"footer\">Free data stack. Not investment advice. Use as research cockpit only.</div>
</body>
</html>"""
    return Response(html, mimetype="text/html")


def v15_safe_call(fn, default=None):
    try:
        return fn()
    except Exception as e:
        return default if default is not None else {"error": str(e)[:300]}


def v15_get_status_snapshot():
    return {
        "v14": v15_safe_call(lambda: v14_dashboard(), {}),
        "v131": v15_safe_call(lambda: v131_performance_dashboard(), {}),
        "internals": v15_safe_call(lambda: v131_market_internals(), {}),
        "ranking_daily": v15_safe_call(lambda: v131_opportunity_ranking(20, "daily"), {}),
        "ranking_intraday": v15_safe_call(lambda: v131_opportunity_ranking(5, "intraday"), {}),
        "ranking_swing": v15_safe_call(lambda: v131_opportunity_ranking(5, "swing"), {}),
        "portfolio_heat": v15_safe_call(lambda: v131_portfolio_heat(), {}),
    }


def v15_dashboard_body():
    snap = v15_get_status_snapshot()
    exp = v15_safe_call(lambda: v14_expectancy(horizon=request.args.get("horizon", "5d")), {})
    overall = exp.get("overall", {}) if isinstance(exp, dict) else {}
    internals = snap.get("internals", {}) or {}
    breadth = internals.get("market_breadth") or internals.get("breadth") or {}
    macro = internals.get("macro", {}) or internals.get("macro_proxies", {}) or {}
    ranking = (snap.get("ranking_daily", {}) or {}).get("top") or (snap.get("ranking_daily", {}) or {}).get("ranking") or []
    leaderboard = v15_safe_call(lambda: v14_leaderboard(request.args.get("horizon", "5d")), {}).get("leaderboard", [])

    cards = "<div class='grid grid-4'>"
    cards += v15_card("Win Rate", v15_pct(overall.get("win_rate")), f"Signals evaluated: {overall.get('signals_evaluated', 0)}")
    cards += v15_card("Expectancy", v15_pct(overall.get("expectancy_pct")), f"Profit Factor: {v15_num(overall.get('profit_factor'))}")
    cards += v15_card("Market Breadth", breadth.get("breadth_regime") or breadth.get("regime") or "N/A", f"Score: {breadth.get('breadth_score', 'N/A')}")
    cards += v15_card("Top Daily", (ranking[0].get("symbol") if ranking else "N/A"), f"Quality: {(ranking[0].get('quality_score') if ranking else 'N/A')}")
    cards += "</div>"

    body = cards
    body += "<div class='actions'><a class='button' href='/v15/ranking'>Open Ranking</a><a class='button' href='/v15/journal'>Open Journal</a><a class='button' href='/v15/portfolio'>Open Portfolio</a><a class='button' href='/v15/correlation'>Open Correlation</a><a class='button' href='/v14/update-outcomes'>Update Outcomes</a></div>"
    body += "<div class='grid grid-2'>"
    body += "<div class='section'><h2>Top 20 Daily Opportunities</h2><div class='section-body'>" + v15_table(ranking[:20], [("symbol","Symbol"),("decision","Decision"),("quality_score","Quality"),("score","Score"),("strategy","Strategy"),("relative_strength_pct","RS %"),("mtf_consensus_score","MTF")], "No ranking data") + "</div></div>"
    body += "<div class='section'><h2>Strategy Leaderboard</h2><div class='section-body'>" + v15_table(leaderboard[:15], [("strategy","Strategy"),("signals_evaluated","Signals"),("win_rate","Win Rate"),("avg_win_pct","Avg Win"),("avg_loss_pct","Avg Loss"),("profit_factor","PF"),("expectancy_pct","Expectancy")], "No strategy results yet") + "</div></div>"
    body += "</div>"
    body += "<div class='section'><h2>Market Internals Snapshot</h2><div class='section-body'><div class='code'>" + v15_escape(json.dumps(internals, ensure_ascii=False, indent=2)[:6000]) + "</div></div></div>"
    return body


def v15_ranking_body():
    mode = request.args.get("mode", "daily")
    data = v15_safe_call(lambda: v131_opportunity_ranking(20 if mode == "daily" else 5, mode), {})
    rows = data.get("top") or data.get("ranking") or []
    body = "<div class='grid grid-3'>"
    for m in ["daily", "intraday", "swing"]:
        body += v15_card(f"{m.title()} Ranking", "Open", f"/v15/ranking?mode={m}")
    body += "</div>"
    body += f"<div class='actions'><a class='button' href='/v15/ranking?mode=daily'>Daily</a><a class='button' href='/v15/ranking?mode=intraday'>Intraday</a><a class='button' href='/v15/ranking?mode=swing'>Swing</a></div>"
    body += f"<div class='section'><h2>Opportunity Ranking · {v15_escape(mode)}</h2><div class='section-body'>"
    body += v15_table(rows, [("symbol","Symbol"),("decision","Decision"),("quality_score","Quality"),("score","Base Score"),("strategy","Strategy"),("relative_strength_pct","Relative Strength"),("mtf_consensus_score","MTF"),("regime","Regime")], "No opportunity ranking available")
    body += "</div></div>"
    return body


def v15_journal_body():
    v15_safe_call(lambda: v14_update_outcomes(), {})
    exp = v15_safe_call(lambda: v14_expectancy(horizon=request.args.get("horizon", "5d")), {})
    overall = exp.get("overall", {}) if isinstance(exp, dict) else {}
    rows = v15_safe_call(lambda: v14_get_journal_rows(limit=300), []) or []
    rows = [dict(r) for r in rows]
    body = "<div class='grid grid-4'>"
    body += v15_card("Signals Evaluated", overall.get("signals_evaluated", 0), "Closed journal rows")
    body += v15_card("Win Rate", v15_pct(overall.get("win_rate")), "Selected horizon")
    body += v15_card("Profit Factor", v15_num(overall.get("profit_factor")), "Avg win / Avg loss")
    body += v15_card("Expectancy", v15_pct(overall.get("expectancy_pct")), "Expected return per signal")
    body += "</div>"
    body += "<div class='actions'><a class='button' href='/v14/journal/log/NVDA?side=CALL&entry=212&strategy=MOMENTUM'>Test Log NVDA</a><a class='button' href='/v14/update-outcomes'>Update Outcomes</a><a class='button' href='/v14/expectancy'>Raw Expectancy JSON</a></div>"
    body += "<div class='section'><h2>Trade Journal</h2><div class='section-body'>"
    body += v15_table(rows[:100], [("created_at","Created"),("symbol","Symbol"),("side","Side"),("strategy","Strategy"),("entry_price","Entry"),("score","Score"),("status","Status"),("return_5d","Return 5D"),("result_5d","Result 5D")], "No journal rows yet. Run /v14/backfill or wait for new alerts.")
    body += "</div></div>"
    return body


def v15_portfolio_body():
    heat = v15_safe_call(lambda: v131_portfolio_heat(), {})
    sizing_symbol = request.args.get("symbol", "NVDA")
    sizing = v15_safe_call(lambda: v131_position_sizing(sizing_symbol), {})
    body = "<div class='grid grid-3'>"
    body += v15_card("Portfolio Heat", heat.get("portfolio_heat", heat.get("message", "N/A")), "Set PORTFOLIO_POSITIONS=NVDA:10,TSLA:5,QQQ:20")
    body += v15_card("Sizing Symbol", sizing.get("symbol", sizing_symbol), f"Suggested shares: {sizing.get('suggested_shares', 'N/A')}")
    body += v15_card("Risk Dollars", v15_num(sizing.get("risk_dollars")), f"Account: {v15_num(sizing.get('account_size'))}")
    body += "</div>"
    body += "<div class='section'><h2>Portfolio Heat Details</h2><div class='section-body'><div class='code'>" + v15_escape(json.dumps(heat, ensure_ascii=False, indent=2)[:6000]) + "</div></div></div>"
    body += "<div class='section'><h2>Position Sizing</h2><div class='section-body'><div class='code'>" + v15_escape(json.dumps(sizing, ensure_ascii=False, indent=2)[:4000]) + "</div></div></div>"
    return body


def v15_correlation_body():
    corr = v15_safe_call(lambda: v131_correlation_matrix(), {})
    symbols = corr.get("symbols") or []
    matrix = corr.get("correlation_matrix") or corr.get("matrix") or {}
    rows = []
    for s in symbols:
        row = {"symbol": s}
        vals = matrix.get(s, {}) if isinstance(matrix, dict) else {}
        for t in symbols:
            row[t] = vals.get(t)
        rows.append(row)
    columns = [("symbol","Symbol")] + [(s, s) for s in symbols]
    body = "<div class='section'><h2>Correlation Matrix</h2><div class='section-body'>"
    body += v15_table(rows, columns, "No correlation data available")
    body += "</div></div>"
    body += "<div class='section'><h2>Raw Correlation Data</h2><div class='section-body'><div class='code'>" + v15_escape(json.dumps(corr, ensure_ascii=False, indent=2)[:5000]) + "</div></div></div>"
    return body


@app.route("/v15/status", methods=["GET"])
def v15_status_route():
    return jsonify({
        "version": V15_VERSION,
        "enabled": True,
        "purpose": "HTML dashboard layer over existing V13.1/V14 research engines",
        "modules": ["Executive Dashboard", "Opportunity Ranking Table", "Trade Journal UI", "Portfolio Heat UI", "Correlation Matrix UI", "Research Terminal"],
        "routes": ["/v15", "/v15/dashboard", "/v15/ranking", "/v15/journal", "/v15/portfolio", "/v15/correlation", "/v15/api/snapshot"]
    })


@app.route("/v15", methods=["GET"])
def v15_terminal_route():
    return v15_layout("V15 Research Terminal", v15_dashboard_body(), active="terminal", refresh=request.args.get("refresh") == "1")


@app.route("/v15/dashboard", methods=["GET"])
def v15_dashboard_route():
    return v15_layout("V15 Dashboard", v15_dashboard_body(), active="dashboard", refresh=request.args.get("refresh") == "1")


@app.route("/v15/ranking", methods=["GET"])
def v15_ranking_route():
    return v15_layout("V15 Opportunity Ranking", v15_ranking_body(), active="ranking", refresh=request.args.get("refresh") == "1")


@app.route("/v15/journal", methods=["GET"])
def v15_journal_route():
    return v15_layout("V15 Trade Journal", v15_journal_body(), active="journal", refresh=request.args.get("refresh") == "1")


@app.route("/v15/portfolio", methods=["GET"])
def v15_portfolio_route():
    return v15_layout("V15 Portfolio", v15_portfolio_body(), active="portfolio", refresh=request.args.get("refresh") == "1")


@app.route("/v15/correlation", methods=["GET"])
def v15_correlation_route():
    return v15_layout("V15 Correlation", v15_correlation_body(), active="correlation", refresh=request.args.get("refresh") == "1")


@app.route("/v15/api/snapshot", methods=["GET"])
def v15_api_snapshot_route():
    return jsonify(v15_get_status_snapshot())


# ============================================================
# V16 INSTITUTIONAL RESEARCH TERMINAL + SIGNAL GOVERNANCE
# ============================================================
V16_VERSION = "V16 Institutional Research Terminal Free 100%"


def v16_clamp(value, low=0, high=100):
    try:
        return max(low, min(high, float(value)))
    except Exception:
        return 0


def v16_get_nested(d, *keys, default=None):
    cur = d
    try:
        for k in keys:
            if cur is None:
                return default
            if isinstance(cur, dict):
                cur = cur.get(k)
            else:
                return default
        return cur if cur is not None else default
    except Exception:
        return default


def v16_market_context():
    internals = v15_safe_call(lambda: v131_market_internals(), {}) if "v15_safe_call" in globals() else {}
    breadth = internals.get("market_breadth") or internals.get("breadth") or {}
    regime = internals.get("regime") or v16_get_nested(breadth, "regime") or v16_get_nested(breadth, "breadth_regime") or "UNKNOWN"
    risk_score = safe_float(internals.get("risk_score"), None)
    breadth_score = safe_float(v16_get_nested(breadth, "breadth_score"), None)
    if breadth_score is None:
        breadth_score = safe_float(v16_get_nested(breadth, "breadth_summary", "breadth_score"), None)
    return {"internals": internals, "breadth": breadth, "regime": str(regime), "risk_score": risk_score, "breadth_score": breadth_score}


def v16_regime_penalty(row, context=None):
    """Institutional regime filter. Applies real score haircuts so quality does not blindly favor calls."""
    context = context or v16_market_context()
    decision = str(row.get("decision") or "").upper()
    regime = str(context.get("regime") or "").upper()
    breadth_score = context.get("breadth_score")
    risk_score = context.get("risk_score")
    penalty = 0
    reasons = []

    if "CALL" in decision:
        if "RISK_OFF" in regime or "BEAR" in regime:
            penalty -= 14; reasons.append("CALL haircut: risk-off/bearish regime")
        elif "MIXED" in regime or "RANGE" in regime:
            penalty -= 5; reasons.append("CALL haircut: mixed/range regime")
        if breadth_score is not None and breadth_score < 45:
            penalty -= 10; reasons.append("CALL haircut: weak breadth")
        if risk_score is not None and risk_score < 45:
            penalty -= 8; reasons.append("CALL haircut: macro risk weak")
    elif "PUT" in decision:
        if "RISK_ON" in regime:
            penalty -= 10; reasons.append("PUT haircut: risk-on regime")
        if breadth_score is not None and breadth_score > 65:
            penalty -= 8; reasons.append("PUT haircut: strong breadth")
    else:
        if "RISK_OFF" in regime or "MIXED" in regime:
            penalty += 2; reasons.append("WAIT supported by uncertain regime")

    return {"penalty": int(penalty), "reasons": reasons, "regime": context.get("regime"), "breadth_score": breadth_score, "risk_score": risk_score}


def v16_adjust_ranking_rows(rows, context=None):
    context = context or v16_market_context()
    adjusted = []
    for raw in rows or []:
        row = dict(raw)
        base_q = safe_float(row.get("quality_score"), safe_float(row.get("quality"), safe_float(row.get("score"), 0)))
        reg = v16_regime_penalty(row, context)
        strategy = str(row.get("strategy") or "").upper()
        strategy_mod = 0
        try:
            if "v14_strategy_modifier" in globals() and strategy:
                strategy_mod = int((v14_strategy_modifier(strategy).get("modifier") or 0))
        except Exception:
            strategy_mod = 0
        adjusted_q = v16_clamp(base_q + reg["penalty"] + strategy_mod)
        row["raw_quality"] = round(base_q, 2)
        row["regime_penalty"] = reg["penalty"]
        row["strategy_modifier"] = strategy_mod
        row["quality_score"] = round(adjusted_q, 2)
        row["quality_clamped"] = True
        row["regime_filter_notes"] = "; ".join(reg["reasons"]) or "No regime haircut"
        adjusted.append(row)
    adjusted.sort(key=lambda x: safe_float(x.get("quality_score"), 0), reverse=True)
    return adjusted


def v16_opportunity_ranking(limit=20, mode="daily"):
    raw = v15_safe_call(lambda: v131_opportunity_ranking(max(limit, 20), mode), {}) if "v15_safe_call" in globals() else {}
    rows = raw.get("top") or raw.get("ranking") or []
    context = v16_market_context()
    adjusted = v16_adjust_ranking_rows(rows, context)
    return {"version": V16_VERSION, "mode": mode, "top": adjusted[:int(limit)], "context": {"regime": context.get("regime"), "risk_score": context.get("risk_score"), "breadth_score": context.get("breadth_score")}, "quality_rule": "quality_score is clamped to 0-100 and adjusted by regime/breadth/strategy history"}


def v16_strategy_leaderboard(horizon="5d"):
    lb = v15_safe_call(lambda: v14_leaderboard(horizon), {}) if "v15_safe_call" in globals() else {}
    rows = lb.get("leaderboard") or []
    live = v16_opportunity_ranking(40, "daily").get("top", [])
    live_counts = {}
    for r in live:
        st = r.get("strategy") or "UNKNOWN"
        live_counts.setdefault(st, {"strategy": st, "live_setups": 0, "avg_quality": 0.0, "call_watch": 0, "put_watch": 0, "wait": 0, "_sum": 0.0})
        live_counts[st]["live_setups"] += 1
        live_counts[st]["_sum"] += safe_float(r.get("quality_score"), 0)
        d = str(r.get("decision") or "").upper()
        if "CALL" in d:
            live_counts[st]["call_watch"] += 1
        elif "PUT" in d:
            live_counts[st]["put_watch"] += 1
        else:
            live_counts[st]["wait"] += 1
    live_rows = []
    for v in live_counts.values():
        n = v.get("live_setups") or 1
        v["avg_quality"] = round(v.pop("_sum") / n, 2)
        live_rows.append(v)
    live_rows.sort(key=lambda x: x.get("avg_quality", 0), reverse=True)
    return {"version": V16_VERSION, "horizon": horizon, "historical_leaderboard": rows, "live_strategy_distribution": live_rows, "note": "Historical leaderboard uses closed journal outcomes. Live distribution is not win rate; it only explains current setup concentration."}


def v16_market_internals_cards():
    ctx = v16_market_context()
    internals = ctx.get("internals") or {}
    proxies = internals.get("proxies") or {}
    def proxy_card(key, label):
        p = proxies.get(key) or {}
        if not p:
            return v15_card(label, "N/A", "No proxy data")
        value = p.get("last")
        chg = p.get("change_pct")
        ema = "Above EMA20" if p.get("above_ema20") else "Below EMA20"
        return v15_card(label, value, f"{chg}% · {ema}")
    body = "<div class='grid grid-4'>"
    body += v15_card("Market Regime", ctx.get("regime", "N/A"), f"Risk score: {ctx.get('risk_score', 'N/A')}")
    body += v15_card("Breadth Score", ctx.get("breadth_score", "N/A"), "Regime-adjusted ranking input")
    body += proxy_card("vix", "VIX")
    body += proxy_card("tnx", "TNX / 10Y Yield")
    body += proxy_card("dxy", "DXY")
    body += proxy_card("spy", "SPY")
    body += proxy_card("qqq", "QQQ")
    body += proxy_card("hyg", "HYG Credit Proxy")
    body += "</div>"
    return body


def v16_portfolio_heat_card():
    heat = v15_safe_call(lambda: v131_portfolio_heat(), {}) if "v15_safe_call" in globals() else {}
    if not heat or heat.get("configured") is False:
        return "<div class='grid grid-3'>" + v15_card("Portfolio Heat", "Not configured", "Set PORTFOLIO_POSITIONS=NVDA:10,TSLA:5,QQQ:20") + v15_card("Risk Budget", "N/A", "Waiting for portfolio weights") + v15_card("Concentration", "N/A", "No exposure data") + "</div>"
    heat_val = heat.get("portfolio_heat") or heat.get("heat_score") or heat.get("risk_level") or "N/A"
    exposures = heat.get("sector_exposure") or heat.get("theme_exposure") or heat.get("exposures") or {}
    top_exp = "N/A"
    try:
        if isinstance(exposures, dict) and exposures:
            top_exp = max(exposures.items(), key=lambda kv: safe_float(kv[1], 0))
            top_exp = f"{top_exp[0]} {top_exp[1]}%"
    except Exception:
        pass
    return "<div class='grid grid-3'>" + v15_card("Portfolio Heat", heat_val, heat.get("message", "Portfolio risk snapshot")) + v15_card("Top Exposure", top_exp, "Largest sector/theme concentration") + v15_card("Configured", str(heat.get("configured", True)), "PORTFOLIO_POSITIONS detected") + "</div>"


def v16_performance_snapshot(horizon="5d"):
    try:
        if "v14_update_outcomes" in globals():
            v14_update_outcomes()
    except Exception:
        pass
    exp = v15_safe_call(lambda: v14_expectancy(horizon=horizon), {}) if "v15_safe_call" in globals() else {}
    overall = exp.get("overall", {}) if isinstance(exp, dict) else {}
    lb = v16_strategy_leaderboard(horizon)
    return {"expectancy": exp, "overall": overall, "leaderboard": lb}


def v16_dashboard_body():
    horizon = request.args.get("horizon", "5d")
    perf = v16_performance_snapshot(horizon)
    overall = perf.get("overall", {})
    ranking = v16_opportunity_ranking(20, "daily").get("top", [])
    lb = perf.get("leaderboard", {})
    hist_rows = lb.get("historical_leaderboard") or []
    live_rows = lb.get("live_strategy_distribution") or []

    body = "<div class='grid grid-4'>"
    body += v15_card("Win Rate", v15_pct(overall.get("win_rate_pct", overall.get("win_rate"))), f"Evaluated: {overall.get('signals_evaluated', 0)}")
    body += v15_card("Profit Factor", v15_num(overall.get("profit_factor")), "Closed journal outcomes")
    body += v15_card("Expectancy", v15_pct(overall.get("expectancy_pct")), f"Horizon: {horizon}")
    body += v15_card("Top Setup", ranking[0].get("symbol") if ranking else "N/A", f"Quality: {ranking[0].get('quality_score') if ranking else 'N/A'}")
    body += "</div>"
    body += "<div class='section'><h2>Market Internals</h2><div class='section-body'>" + v16_market_internals_cards() + "</div></div>"
    body += "<div class='section'><h2>Portfolio Heat</h2><div class='section-body'>" + v16_portfolio_heat_card() + "</div></div>"
    body += "<div class='grid grid-2'>"
    body += "<div class='section'><h2>Top 20 Daily Opportunities · Regime Adjusted</h2><div class='section-body'>" + v15_table(ranking, [("symbol","Symbol"),("decision","Decision"),("quality_score","Quality 0-100"),("raw_quality","Raw"),("regime_penalty","Regime"),("strategy_modifier","History"),("score","Base"),("strategy","Strategy")], "No ranking data") + "</div></div>"
    body += "<div class='section'><h2>Strategy Leaderboard · Real Outcomes</h2><div class='section-body'>" + v15_table(hist_rows[:20], [("strategy","Strategy"),("signals_evaluated","Signals"),("win_rate_pct","Win Rate"),("avg_win_pct","Avg Win"),("avg_loss_pct","Avg Loss"),("profit_factor","PF"),("expectancy_pct","Expectancy")], "No closed strategy outcomes yet. Use Journal/Outcome tracking to build the real leaderboard.") + "</div></div>"
    body += "</div>"
    body += "<div class='section'><h2>Live Strategy Distribution</h2><div class='section-body'>" + v15_table(live_rows, [("strategy","Strategy"),("live_setups","Live Setups"),("avg_quality","Avg Quality"),("call_watch","CALL"),("put_watch","PUT"),("wait","WAIT")], "No live strategy distribution") + "</div></div>"
    return body


def v16_ranking_body():
    mode = request.args.get("mode", "daily")
    limit = int(request.args.get("limit", "20"))
    data = v16_opportunity_ranking(limit, mode)
    rows = data.get("top", [])
    body = "<div class='grid grid-3'>" + v15_card("Mode", mode, "daily / intraday / swing") + v15_card("Regime", data.get("context", {}).get("regime"), "Ranking haircut source") + v15_card("Breadth", data.get("context", {}).get("breadth_score"), "Ranking haircut source") + "</div>"
    body += "<div class='actions'><a class='button' href='/v16/ranking?mode=daily'>Daily</a><a class='button' href='/v16/ranking?mode=intraday&limit=5'>Intraday</a><a class='button' href='/v16/ranking?mode=swing&limit=5'>Swing</a></div>"
    body += "<div class='section'><h2>Regime-Adjusted Opportunity Ranking</h2><div class='section-body'>" + v15_table(rows, [("symbol","Symbol"),("decision","Decision"),("quality_score","Quality 0-100"),("raw_quality","Raw"),("regime_penalty","Regime Penalty"),("strategy_modifier","History Mod"),("regime_filter_notes","Notes"),("strategy","Strategy"),("relative_strength_pct","RS")], "No ranking data") + "</div></div>"
    return body


def v16_leaderboard_body():
    data = v16_strategy_leaderboard(request.args.get("horizon", "5d"))
    body = "<div class='section'><h2>Historical Strategy Leaderboard</h2><div class='section-body'>" + v15_table(data.get("historical_leaderboard", []), [("strategy","Strategy"),("signals_evaluated","Signals"),("win_rate_pct","Win Rate"),("avg_win_pct","Avg Win"),("avg_loss_pct","Avg Loss"),("profit_factor","PF"),("expectancy_pct","Expectancy")], "No closed outcomes yet. This remains empty until journal trades are evaluated.") + "</div></div>"
    body += "<div class='section'><h2>Live Strategy Distribution</h2><div class='section-body'>" + v15_table(data.get("live_strategy_distribution", []), [("strategy","Strategy"),("live_setups","Live Setups"),("avg_quality","Avg Quality"),("call_watch","CALL"),("put_watch","PUT"),("wait","WAIT")], "No live distribution") + "</div></div>"
    return body


def v16_portfolio_body():
    heat = v15_safe_call(lambda: v131_portfolio_heat(), {}) if "v15_safe_call" in globals() else {}
    body = v16_portfolio_heat_card()
    body += "<div class='section'><h2>Raw Portfolio Heat</h2><div class='section-body'><div class='code'>" + v15_escape(json.dumps(heat, ensure_ascii=False, indent=2)[:6000]) + "</div></div></div>"
    return body


def v16_snapshot():
    return {
        "version": V16_VERSION,
        "time": now_text(),
        "performance": v16_performance_snapshot(),
        "market_context": v16_market_context(),
        "ranking_daily": v16_opportunity_ranking(20, "daily"),
        "ranking_intraday": v16_opportunity_ranking(5, "intraday"),
        "ranking_swing": v16_opportunity_ranking(5, "swing"),
        "strategy_leaderboard": v16_strategy_leaderboard(),
        "portfolio_heat": v15_safe_call(lambda: v131_portfolio_heat(), {}) if "v15_safe_call" in globals() else {},
        "quality_controls": ["Quality clamp 0-100", "Regime/breadth haircut", "Historical strategy modifier", "Portfolio heat panel", "Market internals card"]
    }


def v16_layout(title, body, active="dashboard", refresh=False):
    # Reuse V15 CSS/HTML primitives but present V16 navigation and branding.
    refresh_tag = "<meta http-equiv='refresh' content='180'>" if refresh else ""
    nav = [
        ("Dashboard", "/v16/dashboard", "dashboard"),
        ("Ranking", "/v16/ranking", "ranking"),
        ("Leaderboard", "/v16/leaderboard", "leaderboard"),
        ("Internals", "/v16/internals", "internals"),
        ("Portfolio", "/v16/portfolio", "portfolio"),
        ("JSON", "/v16/api/snapshot", "json"),
    ]
    links = "".join(f"<a class='nav-link {'active' if active == key else ''}' href='{href}'>{label}</a>" for label, href, key in nav)
    # Use v15_layout source style by adapting minimal shell.
    html = v15_layout(title, body, active="", refresh=refresh).get_data(as_text=True)
    html = html.replace("<div class=\"logo\">V15</div>", "<div class=\"logo\">V16</div>")
    html = html.replace("Research Dashboard Terminal", "Institutional Research Terminal")
    html = html.replace(v15_escape(V15_VERSION), v15_escape(V16_VERSION))
    # Replace nav section between <div class=\"nav\"> and </div> after header brand.
    html = re.sub(r"<div class=\"nav\">.*?</div>\s*</div>\s*<div class=\"container\">", f"<div class=\"nav\">{links}</div>\n</div>\n<div class=\"container\">", html, count=1, flags=re.S)
    return Response(html, mimetype="text/html")


@app.route("/v16/status", methods=["GET"])
def v16_status_route():
    return jsonify({
        "version": V16_VERSION,
        "enabled": True,
        "adds": ["Historical Analytics Dashboard", "Real Strategy Leaderboard", "Market Internals Card", "Portfolio Heat Card", "Quality Clamp 0-100", "Regime Filter Score Haircut"],
        "routes": ["/v16", "/v16/dashboard", "/v16/ranking", "/v16/leaderboard", "/v16/internals", "/v16/portfolio", "/v16/api/snapshot"],
        "quality_rule": "Ranking quality is clamped to 0-100 after regime/breadth/strategy modifiers."
    })


@app.route("/v16", methods=["GET"])
def v16_terminal_route():
    return v16_layout("V16 Institutional Research Terminal", v16_dashboard_body(), active="dashboard", refresh=request.args.get("refresh") == "1")


@app.route("/v16/dashboard", methods=["GET"])
def v16_dashboard_route():
    return v16_layout("V16 Dashboard", v16_dashboard_body(), active="dashboard", refresh=request.args.get("refresh") == "1")


@app.route("/v16/ranking", methods=["GET"])
def v16_ranking_route():
    return v16_layout("V16 Regime-Adjusted Ranking", v16_ranking_body(), active="ranking", refresh=request.args.get("refresh") == "1")


@app.route("/v16/leaderboard", methods=["GET"])
def v16_leaderboard_route():
    return v16_layout("V16 Strategy Leaderboard", v16_leaderboard_body(), active="leaderboard", refresh=request.args.get("refresh") == "1")


@app.route("/v16/internals", methods=["GET"])
def v16_internals_route():
    body = "<div class='section'><h2>Market Internals Card</h2><div class='section-body'>" + v16_market_internals_cards() + "</div></div>"
    body += "<div class='section'><h2>Raw Internals</h2><div class='section-body'><div class='code'>" + v15_escape(json.dumps(v16_market_context(), ensure_ascii=False, indent=2)[:8000]) + "</div></div></div>"
    return v16_layout("V16 Market Internals", body, active="internals", refresh=request.args.get("refresh") == "1")


@app.route("/v16/portfolio", methods=["GET"])
def v16_portfolio_route():
    return v16_layout("V16 Portfolio Heat", v16_portfolio_body(), active="portfolio", refresh=request.args.get("refresh") == "1")


@app.route("/v16/api/snapshot", methods=["GET"])
def v16_api_snapshot_route():
    return jsonify(v16_snapshot())


# ============================================================
# V17 TRUE INSTITUTIONAL RESEARCH & PORTFOLIO TERMINAL
# ============================================================
V17_VERSION = "V17 True Institutional Research & Portfolio Terminal Free 100%"
V17_MIN_SAMPLE = int(os.getenv("V17_MIN_SAMPLE", os.getenv("V14_MIN_SAMPLE", "10")))
V17_DEFAULT_HORIZON = os.getenv("V17_DEFAULT_HORIZON", "5d")


def v17_safe(fn, default=None):
    try:
        return fn()
    except Exception as e:
        return default if default is not None else {"error": str(e)[:300]}


def v17_clamp(value, low=0, high=100):
    try:
        return max(low, min(high, float(value)))
    except Exception:
        return low


def v17_round(value, n=2):
    try:
        return round(float(value), n)
    except Exception:
        return value


def v17_get_closed_rows(horizon=None, limit=5000):
    horizon = horizon or V17_DEFAULT_HORIZON
    try:
        if "v14_update_outcomes" in globals():
            v14_update_outcomes()
        rows = v14_get_journal_rows(limit=limit) if "v14_get_journal_rows" in globals() else []
        return [dict(r) for r in rows if r[f"return_{horizon}"] is not None]
    except Exception:
        return []


def v17_pnl_for_row(row, horizon=None):
    horizon = horizon or V17_DEFAULT_HORIZON
    ret = safe_float(row.get(f"return_{horizon}"), None)
    if ret is None:
        return None
    result = str(row.get(f"result_{horizon}") or "").upper()
    # Underlying return is inverted for PUT winners/losses. Convert to signal PnL sign.
    if result == "WIN":
        return abs(ret)
    if result == "LOSS":
        return -abs(ret)
    return ret


def v17_performance_metrics(rows=None, horizon=None):
    horizon = horizon or V17_DEFAULT_HORIZON
    rows = rows if rows is not None else v17_get_closed_rows(horizon)
    pnls = [v17_pnl_for_row(r, horizon) for r in rows]
    pnls = [p for p in pnls if p is not None]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    n = len(pnls)
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    win_rate = len(wins) / n * 100 if n else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    profit_factor = gross_win / gross_loss if gross_loss else (999 if gross_win > 0 else 0)
    p_win = win_rate / 100.0
    expectancy = p_win * avg_win - (1 - p_win) * abs(avg_loss)
    return {
        "signals_evaluated": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(win_rate, 2),
        "avg_win_pct": round(avg_win, 3),
        "avg_loss_pct": round(avg_loss, 3),
        "profit_factor": round(profit_factor, 3) if profit_factor != 999 else 999,
        "expectancy_pct": round(expectancy, 3),
        "sample_quality": "LOW" if n < V17_MIN_SAMPLE else "OK",
        "sample_warning": f"Need at least {V17_MIN_SAMPLE} closed outcomes" if n < V17_MIN_SAMPLE else "",
    }


def v17_equity_curve(horizon=None, starting_equity=100.0):
    horizon = horizon or V17_DEFAULT_HORIZON
    rows = v17_get_closed_rows(horizon)
    rows.sort(key=lambda r: safe_float(r.get("created_ts"), 0))
    equity = float(starting_equity)
    curve = []
    peak = equity
    max_dd = 0.0
    for r in rows:
        pnl_pct = v17_pnl_for_row(r, horizon)
        if pnl_pct is None:
            continue
        equity *= (1 + pnl_pct / 100.0)
        peak = max(peak, equity)
        dd = (equity - peak) / peak * 100.0 if peak else 0.0
        max_dd = min(max_dd, dd)
        curve.append({
            "id": r.get("id"),
            "created_at": r.get("created_at"),
            "symbol": r.get("symbol"),
            "strategy": r.get("strategy"),
            "pnl_pct": round(pnl_pct, 3),
            "equity": round(equity, 3),
            "drawdown_pct": round(dd, 3),
        })
    total_return = (equity - starting_equity) / starting_equity * 100.0 if starting_equity else 0.0
    return {"horizon": horizon, "starting_equity": starting_equity, "ending_equity": round(equity, 3), "total_return_pct": round(total_return, 3), "max_drawdown_pct": round(max_dd, 3), "points": curve[-200:]}


def v17_drawdown_analytics(horizon=None):
    curve = v17_equity_curve(horizon)
    points = curve.get("points", [])
    dds = [safe_float(p.get("drawdown_pct"), 0) for p in points]
    return {
        "horizon": curve.get("horizon"),
        "max_drawdown_pct": curve.get("max_drawdown_pct"),
        "current_drawdown_pct": round(dds[-1], 3) if dds else 0,
        "worst_5_drawdowns": sorted(dds)[:5],
        "ending_equity": curve.get("ending_equity"),
        "total_return_pct": curve.get("total_return_pct"),
    }


def v17_kelly_sizing(strategy=None, horizon=None):
    horizon = horizon or V17_DEFAULT_HORIZON
    rows = v17_get_closed_rows(horizon)
    if strategy:
        rows = [r for r in rows if str(r.get("strategy") or "").upper() == str(strategy).upper()]
    m = v17_performance_metrics(rows, horizon)
    p = safe_float(m.get("win_rate_pct"), 0) / 100.0
    avg_win = abs(safe_float(m.get("avg_win_pct"), 0))
    avg_loss = abs(safe_float(m.get("avg_loss_pct"), 0))
    b = avg_win / avg_loss if avg_loss else 0
    if b <= 0 or m.get("signals_evaluated", 0) < V17_MIN_SAMPLE:
        kelly = 0.0
        note = "Insufficient sample or no loss data; use minimum risk only."
    else:
        kelly = p - (1 - p) / b
        note = "Use fractional Kelly only; cap hard to avoid overbetting."
    half_kelly = max(0.0, min(0.10, kelly / 2.0))
    quarter_kelly = max(0.0, min(0.05, kelly / 4.0))
    return {"strategy": strategy or "ALL", "horizon": horizon, "metrics": m, "kelly_fraction": round(kelly, 4), "half_kelly_cap": round(half_kelly, 4), "quarter_kelly_cap": round(quarter_kelly, 4), "note": note}


def v17_monte_carlo(horizon=None, trials=500, steps=50):
    import random
    horizon = horizon or V17_DEFAULT_HORIZON
    rows = v17_get_closed_rows(horizon)
    returns = [v17_pnl_for_row(r, horizon) for r in rows]
    returns = [r for r in returns if r is not None]
    if len(returns) < 5:
        # Conservative fallback, not a claim of real edge.
        returns = [0.6, -0.5, 0.8, -0.7, 1.0, -0.6, 0.4, -0.4]
        sample_note = "fallback synthetic small-return set; collect journal outcomes for real Monte Carlo"
    else:
        sample_note = "bootstrap from closed journal outcomes"
    finals = []
    maxdds = []
    for _ in range(int(trials)):
        equity = 100.0
        peak = 100.0
        maxdd = 0.0
        for _ in range(int(steps)):
            r = random.choice(returns)
            equity *= (1 + r / 100.0)
            peak = max(peak, equity)
            dd = (equity - peak) / peak * 100.0
            maxdd = min(maxdd, dd)
        finals.append(equity)
        maxdds.append(maxdd)
    finals.sort(); maxdds.sort()
    def pct(arr, q):
        if not arr:
            return None
        idx = max(0, min(len(arr)-1, int(len(arr)*q)))
        return round(arr[idx], 3)
    return {
        "horizon": horizon,
        "trials": int(trials),
        "steps": int(steps),
        "sample_size": len(returns),
        "sample_note": sample_note,
        "ending_equity_p10": pct(finals, 0.10),
        "ending_equity_p50": pct(finals, 0.50),
        "ending_equity_p90": pct(finals, 0.90),
        "max_drawdown_p10": pct(maxdds, 0.10),
        "max_drawdown_p50": pct(maxdds, 0.50),
    }


def v17_quality_distribution(rows=None):
    rows = rows if rows is not None else v17_opportunity_ranking(50, "daily").get("top", [])
    bins = {"90-100": 0, "80-89": 0, "70-79": 0, "60-69": 0, "0-59": 0}
    for r in rows:
        q = safe_float(r.get("quality_score"), 0)
        if q >= 90:
            bins["90-100"] += 1
        elif q >= 80:
            bins["80-89"] += 1
        elif q >= 70:
            bins["70-79"] += 1
        elif q >= 60:
            bins["60-69"] += 1
        else:
            bins["0-59"] += 1
    return bins


def v17_market_context():
    ctx = v17_safe(lambda: v16_market_context(), {}) if "v16_market_context" in globals() else {}
    breadth = ctx.get("breadth_score") or v17_get_breadth_score(ctx)
    regime = ctx.get("regime") or "UNKNOWN"
    return {**ctx, "breadth_score": breadth, "regime": regime}


def v17_get_breadth_score(ctx=None):
    ctx = ctx or {}
    b = ctx.get("breadth") or ctx.get("internals", {}).get("breadth") or ctx.get("internals", {}).get("market_breadth") or {}
    for key in ["breadth_score", "score"]:
        if isinstance(b, dict) and b.get(key) is not None:
            return safe_float(b.get(key), 50)
    return safe_float(ctx.get("breadth_score"), 50)


def v17_regime_penalty(row, ctx=None):
    ctx = ctx or v17_market_context()
    regime = str(ctx.get("regime") or "UNKNOWN").upper()
    breadth = safe_float(ctx.get("breadth_score"), 50)
    decision = str(row.get("decision") or "").upper()
    strategy = str(row.get("strategy") or "").upper()
    penalty = 0
    notes = []
    if "RISK_OFF" in regime:
        if "CALL" in decision:
            penalty -= 22; notes.append("RISK_OFF haircut for long/CALL")
        if strategy in {"MOMENTUM", "BREAKOUT"}:
            penalty -= 8; notes.append("Risk-off weakens momentum/breakout")
        if "PUT" in decision:
            penalty += 5; notes.append("RISK_OFF supports bearish setups")
    elif "RISK_ON" in regime:
        if "PUT" in decision:
            penalty -= 15; notes.append("RISK_ON haircut for PUT")
        if "CALL" in decision and strategy in {"MOMENTUM", "CORE_TREND"}:
            penalty += 3; notes.append("RISK_ON modest support")
    if breadth < 45 and "CALL" in decision:
        penalty -= 12; notes.append("Weak breadth haircut")
    if breadth > 65 and "PUT" in decision:
        penalty -= 10; notes.append("Strong breadth haircut for PUT")
    return {"penalty": int(max(-35, min(10, penalty))), "notes": "; ".join(notes) or "No regime haircut"}


def v17_strategy_history_modifier(strategy, horizon=None):
    horizon = horizon or V17_DEFAULT_HORIZON
    try:
        mod = v14_strategy_modifier(strategy, horizon) if "v14_strategy_modifier" in globals() else {"modifier": 0, "reason": "No v14"}
        return {"modifier": int(mod.get("modifier") or 0), "reason": mod.get("reason"), "metrics": mod.get("metrics")}
    except Exception as e:
        return {"modifier": 0, "reason": str(e)[:120]}


def v17_institutional_score(row, ctx=None):
    ctx = ctx or v17_market_context()
    base = safe_float(row.get("score"), 50)
    rs = safe_float(row.get("relative_strength_pct"), 0)
    mtf = safe_float(row.get("mtf_consensus_score"), 0)
    q = safe_float(row.get("quality_score"), base)
    breadth = safe_float(ctx.get("breadth_score"), 50)
    regime_score = safe_float(ctx.get("risk_score"), 50)
    # Normalize RS roughly from -100..+130 into 0..100.
    rs_norm = v17_clamp(50 + rs / 2.0)
    trend_norm = v17_clamp(base)
    mtf_norm = v17_clamp(mtf)
    volume_norm = v17_clamp(q)
    breadth_norm = v17_clamp(breadth)
    regime_norm = v17_clamp(regime_score)
    score = (trend_norm*0.30 + rs_norm*0.20 + volume_norm*0.15 + mtf_norm*0.15 + breadth_norm*0.10 + regime_norm*0.10)
    return round(v17_clamp(score), 2)


def v17_opportunity_ranking(limit=20, mode="daily"):
    limit = int(limit or 20)
    ctx = v17_market_context()
    raw_data = v17_safe(lambda: v131_opportunity_ranking(max(limit, 40), mode), {}) if "v131_opportunity_ranking" in globals() else {}
    rows = raw_data.get("top") or raw_data.get("ranking") or []
    adjusted = []
    for r in rows:
        row = dict(r)
        raw_quality = safe_float(row.get("quality_score"), row.get("score", 50))
        reg = v17_regime_penalty(row, ctx)
        hist = v17_strategy_history_modifier(row.get("strategy"), V17_DEFAULT_HORIZON)
        inst = v17_institutional_score(row, ctx)
        final_quality = raw_quality + reg.get("penalty", 0) + safe_float(hist.get("modifier"), 0)
        # Blend with institutional composite so 100s do not dominate blindly.
        final_quality = final_quality*0.65 + inst*0.35
        row["raw_quality"] = round(raw_quality, 2)
        row["regime_penalty"] = reg.get("penalty")
        row["history_modifier"] = hist.get("modifier")
        row["regime_filter_notes"] = reg.get("notes")
        row["institutional_score"] = inst
        row["quality_score"] = round(v17_clamp(final_quality), 2)
        # Reclassify decision after final quality.
        q = row["quality_score"]
        old_dec = str(row.get("decision") or "").upper()
        if q >= 82 and "PUT" not in old_dec:
            row["decision"] = "CALL_WATCH"
        elif q <= 28:
            row["decision"] = "PUT_WATCH"
        elif "PUT" in old_dec and q <= 45:
            row["decision"] = "PUT_WATCH"
        else:
            row["decision"] = "WAIT"
        adjusted.append(row)
    adjusted.sort(key=lambda x: safe_float(x.get("quality_score"), 0), reverse=True)
    return {"version": V17_VERSION, "mode": mode, "context": ctx, "top": adjusted[:limit], "quality_distribution": v17_quality_distribution(adjusted)}


def v17_strategy_leaderboard(horizon=None):
    horizon = horizon or V17_DEFAULT_HORIZON
    hist = v17_safe(lambda: v14_leaderboard(horizon), {"leaderboard": []}) if "v14_leaderboard" in globals() else {"leaderboard": []}
    hist_rows = hist.get("leaderboard") or []
    live = v17_opportunity_ranking(50, "daily").get("top", [])
    live_map = {}
    for r in live:
        st = str(r.get("strategy") or "UNKNOWN").upper()
        live_map.setdefault(st, {"strategy": st, "live_setups": 0, "avg_quality": 0, "call": 0, "put": 0, "wait": 0, "_sum": 0})
        live_map[st]["live_setups"] += 1
        live_map[st]["_sum"] += safe_float(r.get("quality_score"), 0)
        d = str(r.get("decision") or "").upper()
        if "CALL" in d: live_map[st]["call"] += 1
        elif "PUT" in d: live_map[st]["put"] += 1
        else: live_map[st]["wait"] += 1
    live_rows = []
    for v in live_map.values():
        n = v.get("live_setups") or 1
        v["avg_quality"] = round(v.pop("_sum")/n, 2)
        live_rows.append(v)
    live_rows.sort(key=lambda x: x.get("avg_quality", 0), reverse=True)
    return {"version": V17_VERSION, "horizon": horizon, "historical_leaderboard": hist_rows, "live_strategy_distribution": live_rows, "note": "Historical leaderboard is real only after closed journal outcomes exist; live distribution is current setup mix."}


def v17_sector_rotation():
    data = v17_safe(lambda: v131_sector_rotation(), {}) if "v131_sector_rotation" in globals() else {}
    rows = data.get("ranking") or data.get("sectors") or data.get("sector_rotation") or []
    if isinstance(rows, dict):
        rows = [{"sector": k, **(v if isinstance(v, dict) else {"value": v})} for k, v in rows.items()]
    rows = [dict(x) for x in rows] if isinstance(rows, list) else []
    rows.sort(key=lambda x: safe_float(x.get("relative_strength_pct", x.get("score", x.get("return_pct", 0))), 0), reverse=True)
    return {"version": V17_VERSION, "top_sectors": rows[:12], "raw": data}


def v17_portfolio_positions():
    raw = os.getenv("PORTFOLIO_POSITIONS", "")
    positions = []
    for part in raw.split(","):
        if not part.strip() or ":" not in part:
            continue
        sym, weight = part.split(":", 1)
        positions.append({"symbol": resolve_delisted_symbol(sym.strip().upper()).replace(".BK", ""), "weight_pct": safe_float(weight, 0)})
    return positions


V17_SECTOR_MAP = {
    "NVDA":"SEMICONDUCTOR", "AMD":"SEMICONDUCTOR", "AVGO":"SEMICONDUCTOR", "SMCI":"SEMICONDUCTOR", "MU":"SEMICONDUCTOR", "ARM":"SEMICONDUCTOR", "TSM":"SEMICONDUCTOR", "SOXX":"SEMICONDUCTOR", "SMH":"SEMICONDUCTOR",
    "QQQ":"ETF_TECH", "SPY":"ETF_BROAD", "IWM":"ETF_SMALLCAP", "DIA":"ETF_DOW", "TQQQ":"LEVERAGED_ETF", "SQQQ":"LEVERAGED_ETF", "SOXL":"LEVERAGED_SEMI", "SOXS":"LEVERAGED_SEMI",
    "AAPL":"MEGA_TECH", "MSFT":"MEGA_TECH", "GOOGL":"MEGA_TECH", "GOOG":"MEGA_TECH", "META":"MEGA_TECH", "AMZN":"MEGA_TECH", "NFLX":"CONSUMER_TECH",
    "TSLA":"EV", "RIVN":"EV", "LCID":"EV",
    "JPM":"FINANCIAL", "BAC":"FINANCIAL", "XOM":"ENERGY", "CVX":"ENERGY", "LLY":"HEALTHCARE", "UNH":"HEALTHCARE", "NVO":"HEALTHCARE",
}


def v17_portfolio_heat():
    positions = v17_portfolio_positions()
    if not positions:
        return {"configured": False, "message": "Set PORTFOLIO_POSITIONS=NVDA:10,TSLA:5,QQQ:20 to enable true portfolio heat."}
    total = sum(safe_float(p.get("weight_pct"), 0) for p in positions) or 1
    exposures = {}
    for p in positions:
        sym = p.get("symbol")
        weight = safe_float(p.get("weight_pct"), 0) / total * 100
        sector = V17_SECTOR_MAP.get(sym, "OTHER")
        exposures[sector] = exposures.get(sector, 0) + weight
    top_sector, top_weight = max(exposures.items(), key=lambda kv: kv[1]) if exposures else ("N/A", 0)
    heat = min(100, top_weight * 1.15 + max(0, len([x for x in exposures.values() if x > 20]) - 1) * 8)
    corr = v17_safe(lambda: v131_correlation_matrix([p.get("symbol") for p in positions]), {}) if "v131_correlation_matrix" in globals() else {}
    warnings = []
    if top_weight >= 50:
        warnings.append(f"High concentration in {top_sector}: {round(top_weight,1)}%")
    if heat >= 70:
        warnings.append("Portfolio heat is elevated; reduce correlated exposure or position size.")
    return {"configured": True, "positions": positions, "sector_exposure": {k: round(v,2) for k,v in exposures.items()}, "top_exposure": {"sector": top_sector, "weight_pct": round(top_weight,2)}, "portfolio_heat": round(heat,2), "risk_level": "HIGH" if heat >= 70 else "MEDIUM" if heat >= 45 else "LOW", "warnings": warnings, "correlation": corr}


def v17_correlation_engine(symbols=None):
    if symbols is None:
        positions = v17_portfolio_positions()
        symbols = [p.get("symbol") for p in positions] if positions else ["NVDA", "AMD", "AAPL", "MSFT", "META", "QQQ", "SPY"]
    return v17_safe(lambda: v131_correlation_matrix(symbols), {"symbols": symbols, "error": "correlation unavailable"}) if "v131_correlation_matrix" in globals() else {"symbols": symbols, "error": "v131_correlation_matrix missing"}


def v17_snapshot():
    horizon = request.args.get("horizon", V17_DEFAULT_HORIZON) if "request" in globals() else V17_DEFAULT_HORIZON
    return {
        "version": V17_VERSION,
        "time": now_text(),
        "performance": v17_performance_metrics(horizon=horizon),
        "strategy_leaderboard": v17_strategy_leaderboard(horizon),
        "equity_curve": v17_equity_curve(horizon),
        "drawdown": v17_drawdown_analytics(horizon),
        "kelly": v17_kelly_sizing(horizon=horizon),
        "monte_carlo": v17_monte_carlo(horizon=horizon, trials=200, steps=50),
        "market_context": v17_market_context(),
        "sector_rotation": v17_sector_rotation(),
        "ranking_daily": v17_opportunity_ranking(20, "daily"),
        "ranking_intraday": v17_opportunity_ranking(5, "intraday"),
        "ranking_swing": v17_opportunity_ranking(5, "swing"),
        "portfolio_heat": v17_portfolio_heat(),
        "correlation": v17_correlation_engine(),
    }


def v17_bars_from_distribution(dist):
    html = "<div class='bars'>"
    maxv = max(dist.values()) if dist else 1
    for k, v in dist.items():
        pct = int((v / maxv) * 100) if maxv else 0
        html += f"<div class='barrow'><span>{v15_escape(k)}</span><div class='bar'><i style='width:{pct}%'></i></div><b>{v}</b></div>"
    html += "</div>"
    return html


def v17_dashboard_body():
    horizon = request.args.get("horizon", V17_DEFAULT_HORIZON)
    perf = v17_performance_metrics(horizon=horizon)
    eq = v17_equity_curve(horizon)
    dd = v17_drawdown_analytics(horizon)
    mc = v17_monte_carlo(horizon, trials=250, steps=50)
    ranking = v17_opportunity_ranking(20, "daily")
    rows = ranking.get("top", [])
    lb = v17_strategy_leaderboard(horizon)
    portfolio = v17_portfolio_heat()
    body = "<div class='grid grid-4'>"
    body += v15_card("Win Rate", v15_pct(perf.get("win_rate_pct")), f"Closed outcomes: {perf.get('signals_evaluated', 0)}")
    body += v15_card("Profit Factor", v15_num(perf.get("profit_factor")), "Gross win / gross loss")
    body += v15_card("Expectancy", v15_pct(perf.get("expectancy_pct")), f"Horizon: {horizon}")
    body += v15_card("Max Drawdown", v15_pct(dd.get("max_drawdown_pct")), f"Equity: {eq.get('ending_equity')}")
    body += "</div>"
    body += "<div class='grid grid-3'>"
    body += v15_card("Monte Carlo P50", mc.get("ending_equity_p50"), mc.get("sample_note"))
    body += v15_card("Portfolio Heat", portfolio.get("portfolio_heat", "Not configured"), portfolio.get("risk_level", portfolio.get("message", "")))
    body += v15_card("Top Setup", rows[0].get("symbol") if rows else "N/A", f"Quality: {rows[0].get('quality_score') if rows else 'N/A'}")
    body += "</div>"
    body += "<div class='section'><h2>Quality Distribution</h2><div class='section-body'>" + v17_bars_from_distribution(ranking.get("quality_distribution", {})) + "</div></div>"
    body += "<div class='grid grid-2'>"
    body += "<div class='section'><h2>Top 20 Institutional Composite Ranking</h2><div class='section-body'>" + v15_table(rows, [("symbol","Symbol"),("decision","Decision"),("quality_score","Quality"),("institutional_score","Inst Score"),("raw_quality","Raw"),("regime_penalty","Regime"),("history_modifier","History"),("strategy","Strategy")], "No ranking") + "</div></div>"
    body += "<div class='section'><h2>True Strategy Leaderboard</h2><div class='section-body'>" + v15_table(lb.get("historical_leaderboard", []), [("strategy","Strategy"),("signals_evaluated","Signals"),("win_rate_pct","Win Rate"),("profit_factor","PF"),("expectancy_pct","Expectancy"),("avg_win_pct","Avg Win"),("avg_loss_pct","Avg Loss")], "No closed outcomes yet. Use /v14/backfill then /v14/update-outcomes after enough time.") + "</div></div>"
    body += "</div>"
    body += "<div class='section'><h2>Live Strategy Distribution</h2><div class='section-body'>" + v15_table(lb.get("live_strategy_distribution", []), [("strategy","Strategy"),("live_setups","Live"),("avg_quality","Avg Quality"),("call","CALL"),("put","PUT"),("wait","WAIT")], "No live strategy distribution") + "</div></div>"
    return body


def v17_ranking_body():
    mode = request.args.get("mode", "daily")
    data = v17_opportunity_ranking(int(request.args.get("limit", "20")), mode)
    ctx = data.get("context", {})
    body = "<div class='grid grid-4'>" + v15_card("Mode", mode, "daily / intraday / swing") + v15_card("Regime", ctx.get("regime"), "Penalty driver") + v15_card("Breadth", ctx.get("breadth_score"), "Penalty driver") + v15_card("Distribution", json.dumps(data.get("quality_distribution", {})), "Quality bins") + "</div>"
    body += "<div class='actions'><a class='button' href='/v17/ranking?mode=daily'>Daily</a><a class='button' href='/v17/ranking?mode=intraday&limit=5'>Intraday</a><a class='button' href='/v17/ranking?mode=swing&limit=5'>Swing</a></div>"
    body += "<div class='section'><h2>Regime + History + Composite Adjusted Ranking</h2><div class='section-body'>" + v15_table(data.get("top", []), [("symbol","Symbol"),("decision","Decision"),("quality_score","Quality"),("institutional_score","Inst"),("raw_quality","Raw"),("regime_penalty","Regime"),("history_modifier","History"),("regime_filter_notes","Notes"),("strategy","Strategy"),("relative_strength_pct","RS")], "No ranking") + "</div></div>"
    return body


def v17_leaderboard_body():
    data = v17_strategy_leaderboard(request.args.get("horizon", V17_DEFAULT_HORIZON))
    body = "<div class='section'><h2>Historical Strategy Leaderboard · Real Closed Outcomes</h2><div class='section-body'>" + v15_table(data.get("historical_leaderboard", []), [("strategy","Strategy"),("signals_evaluated","Signals"),("win_rate_pct","Win Rate"),("avg_win_pct","Avg Win"),("avg_loss_pct","Avg Loss"),("profit_factor","PF"),("expectancy_pct","Expectancy")], "No closed outcomes yet. This becomes real after journal outcomes close.") + "</div></div>"
    body += "<div class='section'><h2>Live Strategy Distribution</h2><div class='section-body'>" + v15_table(data.get("live_strategy_distribution", []), [("strategy","Strategy"),("live_setups","Live Setups"),("avg_quality","Avg Quality"),("call","CALL"),("put","PUT"),("wait","WAIT")], "No live distribution") + "</div></div>"
    return body


def v17_risk_body():
    horizon = request.args.get("horizon", V17_DEFAULT_HORIZON)
    kelly = v17_kelly_sizing(request.args.get("strategy"), horizon)
    mc = v17_monte_carlo(horizon, trials=int(request.args.get("trials", "500")), steps=int(request.args.get("steps", "50")))
    dd = v17_drawdown_analytics(horizon)
    eq = v17_equity_curve(horizon)
    body = "<div class='grid grid-4'>"
    body += v15_card("Kelly", kelly.get("kelly_fraction"), "Full Kelly, do not use uncapped")
    body += v15_card("Half Kelly Cap", kelly.get("half_kelly_cap"), "Capped at 10%")
    body += v15_card("MC P50", mc.get("ending_equity_p50"), mc.get("sample_note"))
    body += v15_card("Max DD", v15_pct(dd.get("max_drawdown_pct")), f"Equity: {eq.get('ending_equity')}")
    body += "</div>"
    body += "<div class='section'><h2>Equity Curve Latest Points</h2><div class='section-body'>" + v15_table(eq.get("points", [])[-50:], [("created_at","Created"),("symbol","Symbol"),("strategy","Strategy"),("pnl_pct","PnL %"),("equity","Equity"),("drawdown_pct","DD %")], "No equity curve yet") + "</div></div>"
    body += "<div class='section'><h2>Risk Raw JSON</h2><div class='section-body'><div class='code'>" + v15_escape(json.dumps({"kelly": kelly, "monte_carlo": mc, "drawdown": dd}, ensure_ascii=False, indent=2)[:8000]) + "</div></div></div>"
    return body


def v17_portfolio_body():
    heat = v17_portfolio_heat()
    corr = v17_correlation_engine()
    body = "<div class='grid grid-3'>"
    body += v15_card("Portfolio Heat", heat.get("portfolio_heat", "Not configured"), heat.get("risk_level", heat.get("message", "")))
    top = heat.get("top_exposure") or {}
    body += v15_card("Top Exposure", f"{top.get('sector','N/A')} {top.get('weight_pct','')}%", "Largest concentration")
    body += v15_card("Positions", len(heat.get("positions", [])), "From PORTFOLIO_POSITIONS")
    body += "</div>"
    body += "<div class='section'><h2>Sector / Theme Exposure</h2><div class='section-body'><div class='code'>" + v15_escape(json.dumps(heat.get("sector_exposure", heat), ensure_ascii=False, indent=2)[:5000]) + "</div></div></div>"
    body += "<div class='section'><h2>Correlation Engine</h2><div class='section-body'><div class='code'>" + v15_escape(json.dumps(corr, ensure_ascii=False, indent=2)[:7000]) + "</div></div></div>"
    return body


def v17_internals_body():
    ctx = v17_market_context()
    sector = v17_sector_rotation()
    body = "<div class='section'><h2>Market Internals</h2><div class='section-body'>" + (v16_market_internals_cards() if "v16_market_internals_cards" in globals() else "") + "</div></div>"
    body += "<div class='section'><h2>Sector Rotation</h2><div class='section-body'>" + v15_table(sector.get("top_sectors", []), [("sector","Sector"),("symbol","Symbol"),("relative_strength_pct","RS"),("return_pct","Return"),("score","Score")], "No sector rotation data") + "</div></div>"
    body += "<div class='section'><h2>Raw Context</h2><div class='section-body'><div class='code'>" + v15_escape(json.dumps({"market": ctx, "sector": sector}, ensure_ascii=False, indent=2)[:8000]) + "</div></div></div>"
    return body


def v17_layout(title, body, active="dashboard", refresh=False):
    refresh_tag = "<meta http-equiv='refresh' content='180'>" if refresh else ""
    nav = [("Dashboard","/v17/dashboard","dashboard"),("Ranking","/v17/ranking","ranking"),("Leaderboard","/v17/leaderboard","leaderboard"),("Risk","/v17/risk","risk"),("Internals","/v17/internals","internals"),("Portfolio","/v17/portfolio","portfolio"),("JSON","/v17/api/snapshot","json")]
    links = "".join([f"<a class='{ 'active' if key==active else '' }' href='{href}'>{label}</a>" for label, href, key in nav])
    css = """
    body{margin:0;background:#0b1020;color:#e5edf7;font-family:Arial,Helvetica,sans-serif}.wrap{max-width:1280px;margin:0 auto;padding:24px}.top{display:flex;justify-content:space-between;gap:18px;align-items:center}.brand{display:flex;gap:12px;align-items:center}.logo{background:linear-gradient(135deg,#60a5fa,#8b5cf6);padding:10px;border-radius:12px;font-weight:800}.nav a{color:#b8c4d6;text-decoration:none;margin-left:8px;padding:8px 12px;border-radius:999px;background:#151c32}.nav a.active{background:#2563eb;color:white}.grid{display:grid;gap:14px;margin:16px 0}.grid-2{grid-template-columns:1fr 1fr}.grid-3{grid-template-columns:repeat(3,1fr)}.grid-4{grid-template-columns:repeat(4,1fr)}.card,.section{background:#121a2e;border:1px solid #26334f;border-radius:16px;box-shadow:0 10px 30px #0004}.card{padding:18px}.card .label{font-size:12px;text-transform:uppercase;color:#94a3b8}.card .value{font-size:26px;font-weight:800;margin:8px 0}.card .sub{color:#9fb0c8;font-size:12px}.section h2{margin:0;padding:16px 18px;border-bottom:1px solid #26334f}.section-body{padding:14px 18px;overflow:auto}.tbl{width:100%;border-collapse:collapse}.tbl th{color:#a8bad3;text-transform:uppercase;font-size:12px}.tbl td,.tbl th{padding:10px;border-bottom:1px solid #26334f;text-align:left}.pill{display:inline-block;padding:5px 9px;border-radius:999px;background:#273757}.pill.green{background:#14532d;color:#bbf7d0}.pill.red{background:#7f1d1d;color:#fecaca}.pill.yellow{background:#713f12;color:#fde68a}.code{white-space:pre-wrap;background:#070b16;border:1px solid #1f2a44;border-radius:12px;padding:12px;color:#c7d2fe;font-size:12px}.actions{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}.button{display:inline-block;color:white;background:#1d4ed8;text-decoration:none;padding:10px 14px;border-radius:10px}.bars{display:grid;gap:8px}.barrow{display:grid;grid-template-columns:80px 1fr 40px;gap:10px;align-items:center}.bar{height:12px;background:#17203a;border-radius:999px;overflow:hidden}.bar i{display:block;height:100%;background:#60a5fa}@media(max-width:900px){.grid-2,.grid-3,.grid-4{grid-template-columns:1fr}.top{display:block}.nav{margin-top:12px}}
    """
    return f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>{refresh_tag}<title>{v15_escape(title)}</title><style>{css}</style></head><body><div class='wrap'><div class='top'><div class='brand'><div class='logo'>V17</div><div><h1>{v15_escape(title)}</h1><div style='color:#94a3b8'>{V17_VERSION} · {now_text()}</div></div></div><div class='nav'>{links}</div></div>{body}<p style='text-align:center;color:#718096;margin:34px 0'>Free data stack. Research cockpit only. Not investment advice.</p></div></body></html>"


@app.route("/v17/status", methods=["GET"])
def v17_status_route():
    return jsonify({"version": V17_VERSION, "enabled": True, "tier1": ["Trade Journal", "Expectancy", "Profit Factor", "True Strategy Leaderboard", "Quality Distribution", "Real Regime Penalty"], "tier2": ["Sector Rotation", "Correlation Engine", "True Portfolio Heat", "Institutional Composite Score"], "tier3": ["Kelly Sizing", "Monte Carlo", "Equity Curve", "Drawdown Analytics"], "routes": ["/v17", "/v17/dashboard", "/v17/ranking", "/v17/leaderboard", "/v17/risk", "/v17/internals", "/v17/portfolio", "/v17/api/snapshot"]})


@app.route("/v17", methods=["GET"])
def v17_terminal_route():
    return v17_layout("V17 Institutional Portfolio Management Terminal", v17_dashboard_body(), active="dashboard", refresh=request.args.get("refresh") == "1")


@app.route("/v17/dashboard", methods=["GET"])
def v17_dashboard_route():
    return v17_layout("V17 Dashboard", v17_dashboard_body(), active="dashboard", refresh=request.args.get("refresh") == "1")


@app.route("/v17/ranking", methods=["GET"])
def v17_ranking_route():
    return v17_layout("V17 Institutional Ranking", v17_ranking_body(), active="ranking", refresh=request.args.get("refresh") == "1")


@app.route("/v17/leaderboard", methods=["GET"])
def v17_leaderboard_route():
    return v17_layout("V17 True Strategy Leaderboard", v17_leaderboard_body(), active="leaderboard", refresh=request.args.get("refresh") == "1")


@app.route("/v17/risk", methods=["GET"])
def v17_risk_route():
    return v17_layout("V17 Risk Analytics", v17_risk_body(), active="risk", refresh=request.args.get("refresh") == "1")


@app.route("/v17/internals", methods=["GET"])
def v17_internals_route():
    return v17_layout("V17 Market Internals + Sector Rotation", v17_internals_body(), active="internals", refresh=request.args.get("refresh") == "1")


@app.route("/v17/portfolio", methods=["GET"])
def v17_portfolio_route():
    return v17_layout("V17 Portfolio Heat + Correlation", v17_portfolio_body(), active="portfolio", refresh=request.args.get("refresh") == "1")


@app.route("/v17/api/snapshot", methods=["GET"])
def v17_api_snapshot_route():
    return jsonify(v17_snapshot())


# ============================================================
# V18 TRUE HEDGE-FUND STYLE RESEARCH TERMINAL FREE 100%
# Adds: Closed Trade Journal, Strategy Performance DB, True Expectancy,
# Profit Factor, Equity Curve, Breadth Engine, Sector Rotation, Regime Map,
# Correlation Clusters, Portfolio Concentration, Exposure Analytics,
# Monte Carlo 10,000 Runs, Risk of Ruin, Dynamic Kelly.
# ============================================================
V18_VERSION = "V18 Hedge-Fund Style Research Terminal Free 100%"
V18_DEFAULT_HORIZON = os.getenv("V18_DEFAULT_HORIZON", "5d")
V18_CLUSTER_THRESHOLD = float(os.getenv("V18_CLUSTER_THRESHOLD", "0.65"))
V18_MC_RUNS = int(os.getenv("V18_MC_RUNS", "10000"))
V18_MIN_SAMPLE = int(os.getenv("V18_MIN_SAMPLE", "20"))


def v18_safe(fn, default=None):
    try:
        return fn()
    except Exception as e:
        return default if default is not None else {"error": str(e)}


def v18_clamp(x, lo=0, hi=100):
    try:
        return max(lo, min(hi, float(x)))
    except Exception:
        return lo


def v18_num(x, n=2):
    try:
        return f"{float(x):,.{n}f}"
    except Exception:
        return "N/A"


def v18_pct(x, n=2):
    try:
        return f"{float(x):,.{n}f}%"
    except Exception:
        return "N/A"


def v18_json(x, limit=9000):
    return v15_escape(json.dumps(x, ensure_ascii=False, indent=2)[:limit]) if "v15_escape" in globals() else json.dumps(x, ensure_ascii=False)[:limit]


def v18_ensure_db():
    """True closed trade journal. This supplements the older V14 trade_journal.
    It allows manually closed trades and strategy analytics independent of auto signals.
    """
    try:
        conn = db()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS closed_trade_journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                opened_at TEXT,
                closed_at TEXT,
                symbol TEXT NOT NULL,
                side TEXT,
                strategy TEXT,
                entry_price REAL,
                exit_price REAL,
                qty REAL,
                score REAL,
                regime TEXT,
                notes TEXT,
                pnl_pct REAL,
                r_multiple REAL,
                holding_days REAL,
                mae_pct REAL,
                mfe_pct REAL,
                source TEXT DEFAULT 'manual'
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_closed_trade_strategy ON closed_trade_journal(strategy)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_closed_trade_symbol ON closed_trade_journal(symbol)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_closed_trade_closed_at ON closed_trade_journal(closed_at)")
        conn.commit(); conn.close()
        return True
    except Exception as e:
        print("v18_ensure_db error:", e)
        return False


def v18_log_closed_trade(symbol, side="CALL", strategy="MOMENTUM", entry=None, exit=None, qty=1, score=None, regime=None, notes="", opened_at=None, closed_at=None):
    v18_ensure_db()
    symbol = resolve_delisted_symbol(symbol).replace(".BK", "").upper()
    side = str(side or "CALL").upper()
    strategy = str(strategy or "MOMENTUM").upper()
    entry = safe_float(entry)
    exitp = safe_float(exit)
    qty = safe_float(qty, 1)
    if not symbol or entry is None or exitp is None or entry <= 0:
        return {"ok": False, "error": "symbol, entry, exit are required"}
    direction = -1 if side in {"PUT", "SHORT", "SELL"} else 1
    pnl_pct = (exitp - entry) / entry * 100.0 * direction
    # Simple 1R approximation for manual closed trades if stop is unknown.
    r_multiple = pnl_pct / max(1.0, abs(pnl_pct)) if pnl_pct else 0.0
    opened_at = opened_at or now_text()
    closed_at = closed_at or now_text()
    try:
        conn = db()
        conn.execute("""
            INSERT INTO closed_trade_journal
            (opened_at, closed_at, symbol, side, strategy, entry_price, exit_price, qty, score, regime, notes, pnl_pct, r_multiple, holding_days, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (opened_at, closed_at, symbol, side, strategy, entry, exitp, qty, safe_float(score), regime, notes, pnl_pct, r_multiple, 0.0, "manual"))
        conn.commit(); conn.close()
        return {"ok": True, "symbol": symbol, "side": side, "strategy": strategy, "pnl_pct": round(pnl_pct, 3), "r_multiple": round(r_multiple, 3)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def v18_closed_trade_rows(limit=10000):
    v18_ensure_db()
    rows = []
    # 1) manual closed trades
    try:
        conn = db()
        data = conn.execute("SELECT * FROM closed_trade_journal ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
        conn.close()
        for r in data:
            d = dict(r)
            d["pnl"] = safe_float(d.get("pnl_pct"), 0)
            d["source"] = d.get("source") or "manual"
            rows.append(d)
    except Exception:
        pass
    # 2) older V14 auto-journal closed outcomes
    try:
        if "v14_update_outcomes" in globals():
            v14_update_outcomes()
        if "v14_get_journal_rows" in globals():
            v14rows = v14_get_journal_rows(limit=limit)
            for r in v14rows:
                d = dict(r)
                ret = safe_float(d.get(f"return_{V18_DEFAULT_HORIZON}"), None)
                if ret is None:
                    continue
                pnl = v17_pnl_for_row(d, V18_DEFAULT_HORIZON) if "v17_pnl_for_row" in globals() else ret
                rows.append({
                    "id": "v14_" + str(d.get("id")),
                    "opened_at": d.get("created_at"),
                    "closed_at": d.get("updated_at") or now_text(),
                    "symbol": d.get("symbol"),
                    "side": d.get("side"),
                    "strategy": d.get("strategy") or "UNKNOWN",
                    "entry_price": d.get("entry_price"),
                    "exit_price": d.get(f"price_{V18_DEFAULT_HORIZON}"),
                    "score": d.get("score"),
                    "regime": d.get("regime"),
                    "pnl_pct": pnl,
                    "pnl": pnl,
                    "r_multiple": safe_float(pnl, 0) / 2.0,
                    "source": "v14_auto",
                })
    except Exception:
        pass
    return rows[:int(limit)]


def v18_performance_metrics(rows=None):
    rows = rows if rows is not None else v18_closed_trade_rows()
    pnls = [safe_float(r.get("pnl" if r.get("pnl") is not None else "pnl_pct"), None) for r in rows]
    pnls = [p for p in pnls if p is not None]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    total = len(pnls)
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    win_rate = len(wins) / total * 100 if total else 0
    avg_win = gross_win / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    pf = gross_win / gross_loss if gross_loss else (999 if gross_win > 0 else 0)
    expectancy = (win_rate/100.0 * avg_win) - ((1-win_rate/100.0) * abs(avg_loss)) if total else 0
    r_values = [safe_float(r.get("r_multiple"), None) for r in rows]
    r_values = [r for r in r_values if r is not None]
    return {
        "trades": total,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(win_rate, 2),
        "avg_win_pct": round(avg_win, 3),
        "avg_loss_pct": round(avg_loss, 3),
        "profit_factor": round(pf, 3) if pf != 999 else 999,
        "true_expectancy_pct": round(expectancy, 3),
        "avg_r": round(sum(r_values)/len(r_values), 3) if r_values else 0,
        "sample_quality": "LOW" if total < V18_MIN_SAMPLE else "OK",
        "sample_warning": f"Need at least {V18_MIN_SAMPLE} closed outcomes" if total < V18_MIN_SAMPLE else "",
    }


def v18_strategy_performance_db():
    rows = v18_closed_trade_rows()
    groups = {}
    for r in rows:
        st = str(r.get("strategy") or "UNKNOWN").upper()
        groups.setdefault(st, []).append(r)
    perf = []
    for st, gr in groups.items():
        m = v18_performance_metrics(gr)
        perf.append({"strategy": st, **m})
    perf.sort(key=lambda x: (safe_float(x.get("true_expectancy_pct"), 0), safe_float(x.get("profit_factor"), 0), x.get("trades", 0)), reverse=True)
    return {"version": V18_VERSION, "overall": v18_performance_metrics(rows), "strategies": perf}


def v18_equity_curve(starting=100.0):
    rows = v18_closed_trade_rows()
    # approximate sort by id/opened_at string if no clean timestamp
    rows = list(reversed(rows))
    equity = float(starting)
    peak = equity
    points = []
    max_dd = 0.0
    for i, r in enumerate(rows, 1):
        pnl = safe_float(r.get("pnl" if r.get("pnl") is not None else "pnl_pct"), 0)
        equity *= (1 + pnl/100.0)
        peak = max(peak, equity)
        dd = (equity - peak)/peak*100 if peak else 0
        max_dd = min(max_dd, dd)
        points.append({"n": i, "symbol": r.get("symbol"), "strategy": r.get("strategy"), "pnl_pct": round(pnl,3), "equity": round(equity,3), "drawdown_pct": round(dd,3)})
    return {"starting_equity": starting, "ending_equity": round(equity,3), "total_return_pct": round((equity-starting)/starting*100,3), "max_drawdown_pct": round(max_dd,3), "points": points[-300:]}


def v18_drawdown_analytics():
    curve = v18_equity_curve()
    pts = curve.get("points", [])
    dds = [safe_float(p.get("drawdown_pct"), 0) for p in pts]
    return {"max_drawdown_pct": curve.get("max_drawdown_pct"), "current_drawdown_pct": round(dds[-1],3) if dds else 0, "worst_10_drawdowns": sorted(dds)[:10], "equity_curve_points": len(pts)}


def v18_breadth_engine():
    ctx = v17_market_context() if "v17_market_context" in globals() else {}
    b = ctx.get("breadth") or ctx.get("internals", {}).get("breadth") or ctx.get("internals", {}).get("market_breadth") or {}
    if not isinstance(b, dict): b = {}
    items = b.get("items") or ctx.get("items") or []
    adv = b.get("advancers")
    dec = b.get("decliners")
    if adv is None and isinstance(items, list):
        adv = sum(1 for x in items if safe_float(x.get("change_pct"), 0) > 0)
        dec = sum(1 for x in items if safe_float(x.get("change_pct"), 0) < 0)
    total = max(1, (adv or 0) + (dec or 0))
    above50 = b.get("above_ema50_pct")
    above200 = b.get("above_ema200_pct")
    if above50 is None and isinstance(items, list) and items:
        above50 = sum(1 for x in items if x.get("above_ema50")) / len(items) * 100
    if above200 is None and isinstance(items, list) and items:
        above200 = sum(1 for x in items if x.get("above_ema200")) / len(items) * 100
    nh = b.get("new_highs") or b.get("new_20d_highs") or 0
    nl = b.get("new_lows") or b.get("new_20d_lows") or 0
    score = 50
    score += ((adv or 0) - (dec or 0)) / total * 25
    score += (safe_float(above50, 50) - 50) * 0.25
    score += (safe_float(above200, 50) - 50) * 0.15
    score += (safe_float(nh,0) - safe_float(nl,0)) * 0.5
    score = v18_clamp(score)
    regime = "BULLISH_BREADTH" if score >= 62 else "BEARISH_BREADTH" if score <= 42 else "MIXED_BREADTH"
    return {"breadth_score": round(score,2), "breadth_regime": regime, "advancers": adv or 0, "decliners": dec or 0, "advance_decline_ratio": round((adv or 0)/max(1,(dec or 0)),2), "above_ema50_pct": round(safe_float(above50,0),2), "above_ema200_pct": round(safe_float(above200,0),2), "new_highs": nh, "new_lows": nl, "sample_size": len(items) if isinstance(items, list) else 0, "raw": b}


V18_REGIME_MAP = {
    "RISK_ON": {"MOMENTUM": 1.08, "CORE_TREND": 1.05, "BREAKOUT": 1.06, "MEAN_REVERSION": 0.95, "PUT": 0.72},
    "RISK_OFF": {"MOMENTUM": 0.72, "CORE_TREND": 0.82, "BREAKOUT": 0.70, "MEAN_REVERSION": 1.04, "PUT": 1.12},
    "NEUTRAL": {"MOMENTUM": 0.95, "CORE_TREND": 1.00, "BREAKOUT": 0.92, "MEAN_REVERSION": 1.00, "PUT": 0.95},
}


def v18_regime_map():
    ctx = v17_market_context() if "v17_market_context" in globals() else {}
    regime = str(ctx.get("regime") or "NEUTRAL").upper()
    if "RISK_ON" in regime: key = "RISK_ON"
    elif "RISK_OFF" in regime: key = "RISK_OFF"
    else: key = "NEUTRAL"
    breadth = v18_breadth_engine()
    return {"regime": key, "risk_score": ctx.get("risk_score"), "breadth_score": breadth.get("breadth_score"), "multipliers": V18_REGIME_MAP[key], "notes": "Multiplicative strategy map; stronger than simple additive penalties."}


def v18_sector_rotation():
    data = v17_sector_rotation() if "v17_sector_rotation" in globals() else {}
    rows = data.get("top_sectors") or []
    # fallback ETF sector map if older sector route returned empty
    if not rows:
        symbols = {"XLK_TECH":"XLK", "SMH_SEMIS":"SMH", "XLF_FINANCIALS":"XLF", "XLV_HEALTHCARE":"XLV", "XLI_INDUSTRIALS":"XLI", "XLE_ENERGY":"XLE", "XLY_CONSUMER_DISC":"XLY", "XLP_CONSUMER_STAPLES":"XLP", "XLU_UTILITIES":"XLU", "IWM_SMALLCAP":"IWM", "RSP_EQUAL_WEIGHT":"RSP"}
        bench_ret = 0
        try:
            sp = yf.Ticker("SPY").history(period="1mo", interval="1d")
            if not sp.empty:
                bench_ret = (float(sp["Close"].iloc[-1])-float(sp["Close"].iloc[0]))/float(sp["Close"].iloc[0])*100
        except Exception: pass
        for sector, sym in symbols.items():
            ret = None
            try:
                d = yf.Ticker(sym).history(period="1mo", interval="1d")
                if not d.empty:
                    ret = (float(d["Close"].iloc[-1])-float(d["Close"].iloc[0]))/float(d["Close"].iloc[0])*100
            except Exception: pass
            rows.append({"sector": sector, "symbol": sym, "return_pct": round(ret or 0,2), "benchmark_return_pct": round(bench_ret,2), "relative_strength_pct": round((ret or 0)-bench_ret,2), "score": round(50+((ret or 0)-bench_ret)*3,2)})
    rows = [dict(x) for x in rows]
    rows.sort(key=lambda x: safe_float(x.get("relative_strength_pct", x.get("score", 0)), 0), reverse=True)
    return {"top_sectors": rows[:12], "strongest": rows[:3], "weakest": rows[-3:], "raw": data}


def v18_correlation_clusters(symbols=None, threshold=None):
    threshold = safe_float(threshold, V18_CLUSTER_THRESHOLD)
    corr = v17_correlation_engine(symbols) if "v17_correlation_engine" in globals() else {}
    matrix = corr.get("correlation_matrix") or corr.get("matrix") or {}
    syms = corr.get("symbols") or list(matrix.keys())
    # build graph from abs(correlation) >= threshold excluding self
    graph = {s:set() for s in syms}
    for a in syms:
        row = matrix.get(a, {}) if isinstance(matrix, dict) else {}
        for b, val in row.items():
            if a != b and abs(safe_float(val, 0)) >= threshold:
                graph.setdefault(a,set()).add(b); graph.setdefault(b,set()).add(a)
    seen=set(); clusters=[]
    for s in syms:
        if s in seen: continue
        stack=[s]; comp=[]; seen.add(s)
        while stack:
            x=stack.pop(); comp.append(x)
            for y in graph.get(x,set()):
                if y not in seen:
                    seen.add(y); stack.append(y)
        if len(comp)>1:
            clusters.append({"cluster": comp, "size": len(comp), "risk_bucket": "CORRELATED_BUCKET"})
    return {"threshold": threshold, "symbols": syms, "clusters": clusters, "correlation": corr}


V18_EXPOSURE_MAP = {
    "NVDA":["TECH","AI","SEMIS","MEGA_CAP"], "AMD":["TECH","AI","SEMIS"], "AVGO":["TECH","SEMIS","MEGA_CAP"], "SMCI":["TECH","AI","SEMIS"], "MU":["TECH","SEMIS"], "ARM":["TECH","SEMIS"],
    "QQQ":["ETF","TECH","MEGA_CAP"], "SPY":["ETF","BROAD_MARKET"], "IWM":["ETF","SMALL_CAP"],
    "AAPL":["TECH","MEGA_CAP"], "MSFT":["TECH","AI","MEGA_CAP"], "GOOGL":["TECH","AI","MEGA_CAP"], "META":["TECH","AI","MEGA_CAP"], "AMZN":["TECH","CONSUMER","MEGA_CAP"],
    "TSLA":["EV","HIGH_BETA"], "MSTR":["CRYPTO_PROXY","HIGH_BETA"], "COIN":["CRYPTO_PROXY","HIGH_BETA"],
}


def v18_portfolio_exposure():
    positions = v17_portfolio_positions() if "v17_portfolio_positions" in globals() else []
    if not positions:
        return {"configured": False, "message": "Set PORTFOLIO_POSITIONS=NVDA:10,TSLA:5,QQQ:20"}
    total = sum(safe_float(p.get("weight_pct"),0) for p in positions) or 1
    expo={}
    for p in positions:
        sym = str(p.get("symbol") or "").upper()
        w = safe_float(p.get("weight_pct"),0)/total*100
        tags = V18_EXPOSURE_MAP.get(sym) or [V17_SECTOR_MAP.get(sym,"OTHER") if "V17_SECTOR_MAP" in globals() else "OTHER"]
        for t in tags:
            expo[t]=expo.get(t,0)+w
    top = sorted(expo.items(), key=lambda kv: kv[1], reverse=True)
    heat = max([v for _,v in top], default=0) + max(0, len([v for _,v in top if v>25])-1)*8
    warnings=[]
    for k,v in top:
        if v>=50: warnings.append(f"High {k} exposure {round(v,1)}%")
    clusters = v18_correlation_clusters([p.get("symbol") for p in positions]).get("clusters", [])
    if clusters: warnings.append(f"{len(clusters)} correlation cluster(s) detected")
    return {"configured": True, "positions": positions, "exposure": {k:round(v,2) for k,v in top}, "top_exposure": {"theme": top[0][0] if top else None, "weight_pct": round(top[0][1],2) if top else 0}, "portfolio_heat": round(v18_clamp(heat),2), "risk_level": "HIGH" if heat>=70 else "MEDIUM" if heat>=45 else "LOW", "correlation_clusters": clusters, "warnings": warnings}


def v18_dynamic_kelly(strategy=None):
    rows = v18_closed_trade_rows()
    if strategy:
        rows = [r for r in rows if str(r.get("strategy") or "").upper()==str(strategy).upper()]
    m = v18_performance_metrics(rows)
    p = safe_float(m.get("win_rate_pct"),0)/100
    aw = abs(safe_float(m.get("avg_win_pct"),0)); al = abs(safe_float(m.get("avg_loss_pct"),0))
    b = aw/al if al else 0
    if m.get("trades",0) < V18_MIN_SAMPLE or b<=0:
        k=0; note="Insufficient sample; use min-risk sizing."
    else:
        k = p - (1-p)/b
        note="Use fractional Kelly only; cap by portfolio heat and regime."
    # Regime and portfolio haircuts
    reg = v18_regime_map().get("regime")
    heat = v18_portfolio_exposure().get("portfolio_heat", 0) if v18_portfolio_exposure().get("configured") else 0
    haircut = 1.0
    if reg == "RISK_OFF": haircut *= 0.65
    if heat >= 70: haircut *= 0.5
    elif heat >= 45: haircut *= 0.75
    full = max(0, k*haircut)
    return {"strategy": strategy or "ALL", "metrics": m, "kelly_full": round(full,4), "half_kelly": round(min(0.10, full/2),4), "quarter_kelly": round(min(0.05, full/4),4), "haircut": round(haircut,2), "note": note}


def v18_monte_carlo(runs=None, steps=50, ruin_level=70):
    import random
    runs = int(runs or V18_MC_RUNS)
    rows = v18_closed_trade_rows()
    rets = [safe_float(r.get("pnl" if r.get("pnl") is not None else "pnl_pct"), None) for r in rows]
    rets = [r for r in rets if r is not None]
    if len(rets) < 5:
        rets = [0.8, -0.6, 1.1, -0.9, 0.5, -0.4, 1.3, -0.7, 0.6, -0.5]
        note = "Fallback synthetic sample. Collect closed journal outcomes for real MC."
    else:
        note = "Bootstrap from closed trade outcomes."
    finals=[]; maxdds=[]; ruins=0
    for _ in range(runs):
        eq=100.0; peak=100.0; maxdd=0.0
        for _ in range(int(steps)):
            r=random.choice(rets)
            eq *= (1+r/100.0)
            peak=max(peak,eq); dd=(eq-peak)/peak*100 if peak else 0
            maxdd=min(maxdd,dd)
        finals.append(eq); maxdds.append(maxdd)
        if eq <= ruin_level: ruins += 1
    finals.sort(); maxdds.sort()
    def q(arr, pct):
        idx=max(0,min(len(arr)-1,int((len(arr)-1)*pct)))
        return round(arr[idx],3)
    return {"runs": runs, "steps": steps, "sample_size": len(rets), "note": note, "ending_equity": {"p10": q(finals,.10), "p25": q(finals,.25), "p50": q(finals,.50), "p75": q(finals,.75), "p90": q(finals,.90)}, "max_drawdown": {"p10": q(maxdds,.10), "p50": q(maxdds,.50), "p90": q(maxdds,.90)}, "risk_of_ruin_pct": round(ruins/runs*100,3), "ruin_level": ruin_level}


def v18_institutional_composite(row, context=None):
    context = context or {}
    q = v18_clamp(row.get("quality_score", row.get("score", 50)))
    rs = v18_clamp(50 + safe_float(row.get("relative_strength_pct"),0)/2)
    breadth = safe_float(context.get("breadth",{}).get("breadth_score"), 50)
    strategy = str(row.get("strategy") or "CORE_TREND").upper()
    decision = str(row.get("decision") or "").upper()
    regmap = v18_regime_map()
    regime = regmap.get("regime")
    multipliers = regmap.get("multipliers", {})
    mf = multipliers.get("PUT" if "PUT" in decision else strategy, multipliers.get(strategy, 1.0))
    hist = v18_dynamic_kelly(strategy).get("metrics", {})
    pf = safe_float(hist.get("profit_factor"), 0)
    exp = safe_float(hist.get("true_expectancy_pct"), 0)
    hist_factor = 1.0
    if hist.get("trades",0) >= V18_MIN_SAMPLE:
        hist_factor += min(0.20, max(-0.20, exp/10.0))
        if pf < 1: hist_factor -= 0.10
        elif pf >= 1.5: hist_factor += 0.08
    breadth_factor = 0.85 + breadth/100*0.30
    score = (q*0.55 + rs*0.25 + breadth*0.20) * mf * hist_factor * breadth_factor
    return round(v18_clamp(score),2), {"regime": regime, "regime_factor": round(mf,2), "history_factor": round(hist_factor,2), "breadth_factor": round(breadth_factor,2)}


def v18_ranking(limit=20, mode="daily"):
    base = v17_opportunity_ranking(max(limit,40), mode) if "v17_opportunity_ranking" in globals() else {"top":[]}
    breadth = v18_breadth_engine()
    rows=[]
    for r in base.get("top",[]):
        row=dict(r)
        score, factors = v18_institutional_composite(row, {"breadth": breadth})
        row["v18_composite_score"] = score
        row["v18_factors"] = factors
        q = score
        old = str(row.get("decision") or "").upper()
        if q >= 80 and "PUT" not in old: row["decision"]="CALL_WATCH"
        elif q <= 30: row["decision"]="PUT_WATCH"
        elif "PUT" in old and q <= 48: row["decision"]="PUT_WATCH"
        else: row["decision"]="WAIT"
        rows.append(row)
    rows.sort(key=lambda x:safe_float(x.get("v18_composite_score"),0), reverse=True)
    return {"version": V18_VERSION, "mode": mode, "breadth": breadth, "regime_map": v18_regime_map(), "top": rows[:int(limit)]}


def v18_snapshot():
    return {"version": V18_VERSION, "time": now_text(), "closed_trade_journal": {"count": len(v18_closed_trade_rows(20000)), "latest": v18_closed_trade_rows(10)}, "strategy_performance": v18_strategy_performance_db(), "equity_curve": v18_equity_curve(), "drawdown": v18_drawdown_analytics(), "breadth_engine": v18_breadth_engine(), "sector_rotation": v18_sector_rotation(), "regime_map": v18_regime_map(), "ranking": v18_ranking(20,"daily"), "correlation_clusters": v18_correlation_clusters(), "portfolio_exposure": v18_portfolio_exposure(), "kelly_dynamic": v18_dynamic_kelly(), "monte_carlo_10000": v18_monte_carlo(runs=V18_MC_RUNS)}


def v18_card(label, value, sub=""):
    return v15_card(label, value, sub) if "v15_card" in globals() else f"<div><b>{label}</b><br>{value}<br>{sub}</div>"


def v18_table(rows, cols, empty="No data"):
    return v15_table(rows, cols, empty) if "v15_table" in globals() else "<pre>"+v18_json(rows)+"</pre>"


def v18_bars(dist):
    if "v17_bars_from_distribution" in globals(): return v17_bars_from_distribution(dist)
    return "<pre>"+v18_json(dist)+"</pre>"


def v18_dashboard_body():
    perf = v18_strategy_performance_db()
    overall = perf.get("overall", {})
    eq = v18_equity_curve()
    mc = v18_monte_carlo(runs=10000)
    ranking = v18_ranking(20,"daily")
    body = "<div class='grid grid-4'>"
    body += v18_card("Win Rate", v18_pct(overall.get("win_rate_pct")), f"Closed trades: {overall.get('trades',0)}")
    body += v18_card("Profit Factor", v18_num(overall.get("profit_factor")), "True closed outcomes")
    body += v18_card("True Expectancy", v18_pct(overall.get("true_expectancy_pct")), overall.get("sample_warning",""))
    body += v18_card("Risk of Ruin", v18_pct(mc.get("risk_of_ruin_pct")), "MC 10,000")
    body += "</div>"
    body += "<div class='grid grid-2'>"
    body += "<div class='section'><h2>V18 Institutional Composite Ranking</h2><div class='section-body'>" + v18_table(ranking.get("top", [])[:20], [("symbol","Symbol"),("decision","Decision"),("v18_composite_score","V18 Score"),("quality_score","Quality"),("institutional_score","Inst"),("strategy","Strategy")], "No ranking") + "</div></div>"
    body += "<div class='section'><h2>True Strategy Performance</h2><div class='section-body'>" + v18_table(perf.get("strategies", [])[:10], [("strategy","Strategy"),("trades","Trades"),("win_rate_pct","Win%"),("profit_factor","PF"),("true_expectancy_pct","Exp"),("avg_r","Avg R")], "No closed outcomes yet") + "</div></div>"
    body += "</div>"
    body += "<div class='grid grid-3'>" + v18_card("Equity", eq.get("ending_equity"), f"Max DD {eq.get('max_drawdown_pct')}%") + v18_card("Breadth", v18_breadth_engine().get("breadth_score"), v18_breadth_engine().get("breadth_regime")) + v18_card("Portfolio Heat", v18_portfolio_exposure().get("portfolio_heat", "N/A"), v18_portfolio_exposure().get("risk_level", "Not configured")) + "</div>"
    return body


def v18_ranking_body():
    mode = request.args.get("mode", "daily") if "request" in globals() else "daily"
    data = v18_ranking(30, mode)
    body = "<div class='grid grid-4'>" + v18_card("Mode", mode, "daily / intraday / swing") + v18_card("Regime", data.get("regime_map",{}).get("regime"), "Multiplicative map") + v18_card("Breadth", data.get("breadth",{}).get("breadth_score"), data.get("breadth",{}).get("breadth_regime")) + v18_card("Top", data.get("top", [{}])[0].get("symbol") if data.get("top") else "N/A", "Highest V18 composite") + "</div>"
    body += "<div class='actions'><a class='button' href='/v18/ranking?mode=daily'>Daily</a><a class='button' href='/v18/ranking?mode=intraday'>Intraday</a><a class='button' href='/v18/ranking?mode=swing'>Swing</a></div>"
    body += "<div class='section'><h2>V18 Regime × Breadth × History Composite Ranking</h2><div class='section-body'>" + v18_table(data.get("top", []), [("symbol","Symbol"),("decision","Decision"),("v18_composite_score","V18"),("quality_score","Quality"),("raw_quality","Raw"),("regime_penalty","Old Penalty"),("strategy","Strategy"),("relative_strength_pct","RS")], "No ranking") + "</div></div>"
    return body


def v18_leaderboard_body():
    data = v18_strategy_performance_db()
    live = v17_strategy_leaderboard().get("live_strategy_distribution", []) if "v17_strategy_leaderboard" in globals() else []
    body = "<div class='section'><h2>Closed Trade Strategy Performance DB</h2><div class='section-body'>" + v18_table(data.get("strategies", []), [("strategy","Strategy"),("trades","Trades"),("win_rate_pct","Win%"),("avg_win_pct","Avg Win"),("avg_loss_pct","Avg Loss"),("profit_factor","PF"),("true_expectancy_pct","Expectancy"),("avg_r","Avg R")], "No closed outcomes yet. Use /v18/journal/log to add closed trades, or let V14 outcomes close over time.") + "</div></div>"
    body += "<div class='section'><h2>Live Strategy Distribution</h2><div class='section-body'>" + v18_table(live, [("strategy","Strategy"),("live_setups","Live"),("avg_quality","Avg Quality"),("call","Call"),("put","Put"),("wait","Wait")], "No live setups") + "</div></div>"
    return body


def v18_risk_body():
    k = v18_dynamic_kelly()
    mc = v18_monte_carlo(runs=10000)
    eq = v18_equity_curve()
    dd = v18_drawdown_analytics()
    body = "<div class='grid grid-4'>" + v18_card("Kelly Full", k.get("kelly_full"), k.get("note")) + v18_card("Half Kelly", k.get("half_kelly"), "Capped") + v18_card("MC P50", mc.get("ending_equity",{}).get("p50"), "10,000 runs") + v18_card("Max DD", v18_pct(dd.get("max_drawdown_pct")), f"Equity {eq.get('ending_equity')}") + "</div>"
    body += "<div class='section'><h2>Equity Curve Latest Points</h2><div class='section-body'>" + v18_table(eq.get("points", [])[-30:], [("n","#"),("symbol","Symbol"),("strategy","Strategy"),("pnl_pct","PnL%"),("equity","Equity"),("drawdown_pct","DD%")], "No equity curve yet") + "</div></div>"
    body += "<div class='section'><h2>Monte Carlo 10,000 + Risk of Ruin</h2><div class='section-body'><div class='code'>" + v18_json(mc, 5000) + "</div></div></div>"
    return body


def v18_internals_body():
    b = v18_breadth_engine(); sector = v18_sector_rotation(); reg = v18_regime_map()
    body = "<div class='grid grid-4'>" + v18_card("Regime", reg.get("regime"), "Strategy multipliers active") + v18_card("Breadth", b.get("breadth_score"), b.get("breadth_regime")) + v18_card("Adv / Dec", f"{b.get('advancers')} / {b.get('decliners')}", f"Ratio {b.get('advance_decline_ratio')}") + v18_card("Above EMA50", v18_pct(b.get("above_ema50_pct")), f"EMA200 {v18_pct(b.get('above_ema200_pct'))}") + "</div>"
    body += "<div class='section'><h2>Sector Rotation</h2><div class='section-body'>" + v18_table(sector.get("top_sectors", []), [("sector","Sector"),("symbol","Symbol"),("relative_strength_pct","RS"),("return_pct","Return"),("score","Score")], "No sector data") + "</div></div>"
    body += "<div class='section'><h2>Regime Map</h2><div class='section-body'><div class='code'>" + v18_json(reg, 3000) + "</div></div></div>"
    return body


def v18_portfolio_body():
    expo = v18_portfolio_exposure(); clusters = v18_correlation_clusters()
    body = "<div class='grid grid-3'>" + v18_card("Portfolio Heat", expo.get("portfolio_heat", "Not configured"), expo.get("risk_level", expo.get("message", ""))) + v18_card("Top Exposure", (expo.get("top_exposure") or {}).get("theme","N/A"), f"{(expo.get('top_exposure') or {}).get('weight_pct','')}%") + v18_card("Clusters", len(expo.get("correlation_clusters", [])), "Correlation buckets") + "</div>"
    body += "<div class='section'><h2>Exposure Analytics</h2><div class='section-body'><div class='code'>" + v18_json(expo, 7000) + "</div></div></div>"
    body += "<div class='section'><h2>Correlation Clusters</h2><div class='section-body'><div class='code'>" + v18_json(clusters, 9000) + "</div></div></div>"
    return body


def v18_journal_body():
    rows = v18_closed_trade_rows(100)
    body = "<div class='actions'><a class='button' href='/v18/journal/log/NVDA?side=CALL&entry=100&exit=105&strategy=MOMENTUM'>Test Closed Trade</a><a class='button' href='/v18/api/snapshot'>Snapshot JSON</a></div>"
    body += "<div class='section'><h2>Closed Trade Journal</h2><div class='section-body'>" + v18_table(rows[:50], [("symbol","Symbol"),("side","Side"),("strategy","Strategy"),("entry_price","Entry"),("exit_price","Exit"),("pnl_pct","PnL%"),("r_multiple","R"),("source","Source")], "No closed trades yet") + "</div></div>"
    return body


def v18_layout(title, body, active="dashboard", refresh=False):
    refresh_tag = "<meta http-equiv='refresh' content='180'>" if refresh else ""
    nav = [("Dashboard","/v18/dashboard","dashboard"),("Ranking","/v18/ranking","ranking"),("Leaderboard","/v18/leaderboard","leaderboard"),("Risk","/v18/risk","risk"),("Internals","/v18/internals","internals"),("Portfolio","/v18/portfolio","portfolio"),("Journal","/v18/journal","journal"),("JSON","/v18/api/snapshot","json")]
    links = "".join([f"<a class='{ 'active' if key==active else '' }' href='{href}'>{label}</a>" for label, href, key in nav])
    css = """
    body{margin:0;background:#0b1020;color:#e5edf7;font-family:Arial,Helvetica,sans-serif}.wrap{max-width:1320px;margin:0 auto;padding:24px}.top{display:flex;justify-content:space-between;gap:18px;align-items:center}.brand{display:flex;gap:12px;align-items:center}.logo{background:linear-gradient(135deg,#22c55e,#2563eb);padding:10px;border-radius:12px;font-weight:800}.nav a{color:#b8c4d6;text-decoration:none;margin-left:8px;padding:8px 12px;border-radius:999px;background:#151c32}.nav a.active{background:#2563eb;color:white}.grid{display:grid;gap:14px;margin:16px 0}.grid-2{grid-template-columns:1fr 1fr}.grid-3{grid-template-columns:repeat(3,1fr)}.grid-4{grid-template-columns:repeat(4,1fr)}.card,.section{background:#121a2e;border:1px solid #26334f;border-radius:16px;box-shadow:0 10px 30px #0004}.card{padding:18px}.card .label{font-size:12px;text-transform:uppercase;color:#94a3b8}.card .value{font-size:26px;font-weight:800;margin:8px 0}.card .sub{color:#9fb0c8;font-size:12px}.section h2{margin:0;padding:16px 18px;border-bottom:1px solid #26334f}.section-body{padding:14px 18px;overflow:auto}.tbl{width:100%;border-collapse:collapse}.tbl th{color:#a8bad3;text-transform:uppercase;font-size:12px}.tbl td,.tbl th{padding:9px;border-bottom:1px solid #26334f;text-align:left}.pill{display:inline-block;padding:5px 9px;border-radius:999px;background:#273757}.pill.green{background:#14532d;color:#bbf7d0}.pill.red{background:#7f1d1d;color:#fecaca}.pill.yellow{background:#713f12;color:#fde68a}.code{white-space:pre-wrap;background:#070b16;border:1px solid #1f2a44;border-radius:12px;padding:12px;color:#c7d2fe;font-size:12px}.actions{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}.button{display:inline-block;color:white;background:#1d4ed8;text-decoration:none;padding:10px 14px;border-radius:10px}@media(max-width:900px){.grid-2,.grid-3,.grid-4{grid-template-columns:1fr}.top{display:block}.nav{margin-top:12px}}
    """
    return f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>{refresh_tag}<title>{v15_escape(title)}</title><style>{css}</style></head><body><div class='wrap'><div class='top'><div class='brand'><div class='logo'>V18</div><div><h1>{v15_escape(title)}</h1><div style='color:#94a3b8'>{V18_VERSION} · {now_text()}</div></div></div><div class='nav'>{links}</div></div>{body}<p style='text-align:center;color:#718096;margin:34px 0'>Free data stack. Research cockpit only. Not investment advice.</p></div></body></html>"


@app.route("/v18/status", methods=["GET"])
def v18_status_route():
    return jsonify({"version": V18_VERSION, "enabled": True, "priorities": {"p1":["Closed Trade Journal","Strategy Performance Database","True Expectancy","Profit Factor","Equity Curve"], "p2":["Breadth Engine","Sector Rotation","Regime Map"], "p3":["Correlation Cluster","Portfolio Concentration","Exposure Analytics"], "p4":["Monte Carlo 10000 Runs","Risk Of Ruin","Kelly Dynamic"]}, "routes": ["/v18", "/v18/dashboard", "/v18/ranking", "/v18/leaderboard", "/v18/risk", "/v18/internals", "/v18/portfolio", "/v18/journal", "/v18/api/snapshot"]})

@app.route("/v18", methods=["GET"])
def v18_root_route():
    return v18_layout("V18 Hedge-Fund Research Terminal", v18_dashboard_body(), active="dashboard", refresh=request.args.get("refresh")=="1")

@app.route("/v18/dashboard", methods=["GET"])
def v18_dashboard_route():
    return v18_layout("V18 Dashboard", v18_dashboard_body(), active="dashboard", refresh=request.args.get("refresh")=="1")

@app.route("/v18/ranking", methods=["GET"])
def v18_ranking_route():
    return v18_layout("V18 Institutional Composite Ranking", v18_ranking_body(), active="ranking", refresh=request.args.get("refresh")=="1")

@app.route("/v18/leaderboard", methods=["GET"])
def v18_leaderboard_route():
    return v18_layout("V18 Strategy Performance DB", v18_leaderboard_body(), active="leaderboard", refresh=request.args.get("refresh")=="1")

@app.route("/v18/risk", methods=["GET"])
def v18_risk_route():
    return v18_layout("V18 Risk: Kelly + Monte Carlo + Drawdown", v18_risk_body(), active="risk", refresh=request.args.get("refresh")=="1")

@app.route("/v18/internals", methods=["GET"])
def v18_internals_route():
    return v18_layout("V18 Breadth + Sector + Regime Map", v18_internals_body(), active="internals", refresh=request.args.get("refresh")=="1")

@app.route("/v18/portfolio", methods=["GET"])
def v18_portfolio_route():
    return v18_layout("V18 Portfolio Exposure + Correlation Clusters", v18_portfolio_body(), active="portfolio", refresh=request.args.get("refresh")=="1")

@app.route("/v18/journal", methods=["GET"])
def v18_journal_route():
    return v18_layout("V18 Closed Trade Journal", v18_journal_body(), active="journal", refresh=request.args.get("refresh")=="1")

@app.route("/v18/journal/log/<symbol>", methods=["GET", "POST"])
def v18_journal_log_route(symbol):
    return jsonify(v18_log_closed_trade(symbol, side=request.args.get("side","CALL"), strategy=request.args.get("strategy","MOMENTUM"), entry=request.args.get("entry"), exit=request.args.get("exit"), qty=request.args.get("qty",1), score=request.args.get("score"), regime=request.args.get("regime"), notes=request.args.get("notes","")))

@app.route("/v18/api/snapshot", methods=["GET"])
def v18_api_snapshot_route():
    return jsonify(v18_snapshot())

# ============================================================
# V19 TRUE JOURNAL / OUTCOME / EQUITY / STRATEGY STATS LAYER
# ============================================================
V19_VERSION = "V19 True Journal + Outcome Database Free 100%"
V19_HORIZONS = [1, 3, 5, 10, 20]


def v19_init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS v19_trade_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opened_at TEXT NOT NULL,
            closed_at TEXT,
            symbol TEXT NOT NULL,
            yf_symbol TEXT,
            asset_type TEXT,
            side TEXT NOT NULL,
            strategy TEXT NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL,
            qty REAL DEFAULT 1,
            score REAL,
            regime TEXT,
            stop_price REAL,
            target_price REAL,
            status TEXT DEFAULT 'OPEN',
            pnl_pct REAL,
            pnl_amount REAL,
            r_multiple REAL,
            holding_days REAL,
            notes TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS v19_trade_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id INTEGER NOT NULL,
            horizon_days INTEGER NOT NULL,
            evaluated_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            strategy TEXT,
            entry_price REAL,
            mark_price REAL,
            return_pct REAL,
            outcome TEXT,
            UNIQUE(trade_id, horizon_days)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS v19_equity_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id INTEGER UNIQUE,
            timestamp TEXT NOT NULL,
            equity REAL NOT NULL,
            pnl_pct REAL,
            drawdown_pct REAL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_v19_trade_status ON v19_trade_journal(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_v19_trade_strategy ON v19_trade_journal(strategy)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_v19_outcomes_trade ON v19_trade_outcomes(trade_id)")
    conn.commit()
    conn.close()


def v19_to_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", "").strip())
    except Exception:
        return default


def v19_parse_dt(text):
    if not text:
        return None
    for fmt in ("%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(text).split(".")[0], fmt)
        except Exception:
            pass
    return None


def v19_current_price(symbol):
    asset = normalize_asset(resolve_delisted_symbol(symbol))
    quote, closes, highs, lows, opens, volumes = get_market_data(asset)
    price = safe_float(quote.get("close") or quote.get("price"))
    if not price and closes:
        price = closes[-1]
    return price, asset


def v19_side_return(side, entry, exit_price):
    side = (side or "LONG").upper()
    entry = v19_to_float(entry)
    exit_price = v19_to_float(exit_price)
    if not entry or not exit_price:
        return None
    if side in {"PUT", "SHORT", "SELL", "BEARISH"}:
        return (entry - exit_price) / entry * 100.0
    return (exit_price - entry) / entry * 100.0


def v19_r_multiple(side, entry, exit_price, stop_price):
    entry = v19_to_float(entry)
    exit_price = v19_to_float(exit_price)
    stop_price = v19_to_float(stop_price)
    if not entry or not exit_price or not stop_price or entry == stop_price:
        return None
    side = (side or "LONG").upper()
    if side in {"PUT", "SHORT", "SELL", "BEARISH"}:
        risk = stop_price - entry
        gain = entry - exit_price
    else:
        risk = entry - stop_price
        gain = exit_price - entry
    if risk <= 0:
        return None
    return gain / risk


def v19_open_trade(symbol, side="LONG", strategy="MANUAL", entry=None, qty=1, score=None, regime=None, stop=None, target=None, notes=""):
    v19_init_db()
    symbol = resolve_delisted_symbol(symbol)
    price, asset = v19_current_price(symbol) if entry in (None, "") else (v19_to_float(entry), normalize_asset(symbol))
    if not price:
        return {"ok": False, "error": f"No entry/live price available for {symbol}"}
    side = (side or "LONG").upper()
    strategy = (strategy or "MANUAL").upper()
    qty = v19_to_float(qty, 1.0) or 1.0
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO v19_trade_journal
        (opened_at, symbol, yf_symbol, asset_type, side, strategy, entry_price, qty, score, regime, stop_price, target_price, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)
    """, (now_text(), asset.get("symbol", symbol), asset.get("yf_symbol"), asset.get("asset_type"), side, strategy, float(price), qty, v19_to_float(score), regime, v19_to_float(stop), v19_to_float(target), notes or ""))
    trade_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {"ok": True, "trade_id": trade_id, "symbol": asset.get("symbol", symbol), "side": side, "strategy": strategy, "entry_price": float(price), "qty": qty, "status": "OPEN"}


def v19_close_trade(trade_id, exit_price=None, notes=""):
    v19_init_db()
    conn = db()
    row = conn.execute("SELECT * FROM v19_trade_journal WHERE id=?", (trade_id,)).fetchone()
    if not row:
        conn.close()
        return {"ok": False, "error": "trade_id not found"}
    if (row["status"] or "").upper() == "CLOSED":
        conn.close()
        return {"ok": True, "message": "already closed", "trade_id": trade_id}
    if exit_price in (None, ""):
        exit_price, _ = v19_current_price(row["symbol"])
    exit_price = v19_to_float(exit_price)
    if not exit_price:
        conn.close()
        return {"ok": False, "error": "No exit/live price available"}
    pnl_pct = v19_side_return(row["side"], row["entry_price"], exit_price)
    qty = v19_to_float(row["qty"], 1.0) or 1.0
    entry = v19_to_float(row["entry_price"])
    raw_diff = exit_price - entry
    if str(row["side"]).upper() in {"PUT", "SHORT", "SELL", "BEARISH"}:
        raw_diff = entry - exit_price
    pnl_amount = raw_diff * qty
    r_mult = v19_r_multiple(row["side"], entry, exit_price, row["stop_price"])
    opened = v19_parse_dt(row["opened_at"])
    holding = None
    if opened:
        holding = max(0.0, (datetime.now() - opened).total_seconds() / 86400.0)
    closed_at = now_text()
    conn.execute("""
        UPDATE v19_trade_journal
        SET closed_at=?, exit_price=?, status='CLOSED', pnl_pct=?, pnl_amount=?, r_multiple=?, holding_days=?, notes=COALESCE(notes,'') || ?
        WHERE id=?
    """, (closed_at, exit_price, pnl_pct, pnl_amount, r_mult, holding, (" | close: " + notes) if notes else "", trade_id))
    conn.commit()
    conn.close()
    v19_rebuild_equity_curve()
    return {"ok": True, "trade_id": trade_id, "exit_price": exit_price, "pnl_pct": pnl_pct, "pnl_amount": pnl_amount, "r_multiple": r_mult, "status": "CLOSED"}


def v19_trade_rows(status=None, limit=200):
    v19_init_db()
    conn = db()
    if status:
        rows = conn.execute("SELECT * FROM v19_trade_journal WHERE status=? ORDER BY id DESC LIMIT ?", (status.upper(), int(limit))).fetchall()
    else:
        rows = conn.execute("SELECT * FROM v19_trade_journal ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def v19_update_outcomes():
    v19_init_db()
    conn = db()
    rows = conn.execute("SELECT * FROM v19_trade_journal WHERE status='OPEN' ORDER BY id ASC").fetchall()
    inserted = 0
    errors = []
    for r in rows:
        opened = v19_parse_dt(r["opened_at"])
        if not opened:
            continue
        elapsed = (datetime.now() - opened).days
        try:
            mark, _ = v19_current_price(r["symbol"])
        except Exception as e:
            errors.append(f"{r['symbol']}: {e}")
            continue
        if not mark:
            continue
        for h in V19_HORIZONS:
            if elapsed >= h:
                ret = v19_side_return(r["side"], r["entry_price"], mark)
                outcome = "WIN" if (ret or 0) > 0 else "LOSS" if (ret or 0) < 0 else "FLAT"
                try:
                    conn.execute("""
                        INSERT OR REPLACE INTO v19_trade_outcomes
                        (trade_id, horizon_days, evaluated_at, symbol, side, strategy, entry_price, mark_price, return_pct, outcome)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (r["id"], h, now_text(), r["symbol"], r["side"], r["strategy"], r["entry_price"], mark, ret, outcome))
                    inserted += 1
                except Exception as e:
                    errors.append(str(e))
    conn.commit()
    conn.close()
    return {"ok": True, "open_trades": len(rows), "outcomes_upserted": inserted, "errors": errors[:10], "horizons": V19_HORIZONS}


def v19_closed_stats(rows):
    returns = [v19_to_float(r.get("pnl_pct")) for r in rows if v19_to_float(r.get("pnl_pct")) is not None]
    wins = [x for x in returns if x > 0]
    losses = [x for x in returns if x < 0]
    total = len(returns)
    win_rate = len(wins) / total * 100 if total else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_win / gross_loss if gross_loss else (gross_win if gross_win else 0.0)
    expectancy = (win_rate/100.0)*avg_win + (1-win_rate/100.0)*avg_loss if total else 0.0
    return {"trades": total, "wins": len(wins), "losses": len(losses), "win_rate": round(win_rate,2), "avg_win_pct": round(avg_win,2), "avg_loss_pct": round(avg_loss,2), "profit_factor": round(profit_factor,2), "expectancy_pct": round(expectancy,2)}


def v19_strategy_stats():
    v19_init_db()
    conn = db()
    rows = [dict(r) for r in conn.execute("SELECT * FROM v19_trade_journal WHERE status='CLOSED' ORDER BY closed_at ASC").fetchall()]
    conn.close()
    by = {}
    for r in rows:
        by.setdefault((r.get("strategy") or "UNKNOWN"), []).append(r)
    out = []
    for strat, items in by.items():
        s = v19_closed_stats(items)
        s["strategy"] = strat
        out.append(s)
    out.sort(key=lambda x: (x.get("profit_factor",0), x.get("expectancy_pct",0), x.get("trades",0)), reverse=True)
    overall = v19_closed_stats(rows)
    return {"overall": overall, "strategies": out, "sample_warning": "Need at least 30 closed trades per strategy for statistical confidence" if overall["trades"] < 30 else "OK"}


def v19_rebuild_equity_curve(starting=100.0):
    v19_init_db()
    conn = db()
    rows = conn.execute("SELECT * FROM v19_trade_journal WHERE status='CLOSED' AND pnl_pct IS NOT NULL ORDER BY closed_at ASC, id ASC").fetchall()
    conn.execute("DELETE FROM v19_equity_points")
    equity = float(starting)
    peak = equity
    points = []
    for r in rows:
        pnl_pct = v19_to_float(r["pnl_pct"], 0.0) or 0.0
        equity = equity * (1 + pnl_pct/100.0)
        peak = max(peak, equity)
        dd = ((equity - peak) / peak * 100.0) if peak else 0.0
        conn.execute("INSERT OR REPLACE INTO v19_equity_points(trade_id, timestamp, equity, pnl_pct, drawdown_pct) VALUES (?, ?, ?, ?, ?)", (r["id"], r["closed_at"] or now_text(), equity, pnl_pct, dd))
        points.append({"trade_id": r["id"], "timestamp": r["closed_at"], "equity": round(equity,2), "pnl_pct": round(pnl_pct,2), "drawdown_pct": round(dd,2)})
    conn.commit()
    conn.close()
    return points


def v19_equity_curve():
    v19_init_db()
    conn = db()
    rows = conn.execute("SELECT * FROM v19_equity_points ORDER BY id ASC").fetchall()
    conn.close()
    points = [dict(r) for r in rows]
    if not points:
        points = v19_rebuild_equity_curve()
    if points:
        max_dd = min([v19_to_float(p.get("drawdown_pct"),0) for p in points])
        latest = points[-1].get("equity")
    else:
        max_dd = 0.0
        latest = 100.0
    return {"starting_equity":100.0, "latest_equity":latest, "max_drawdown_pct":round(max_dd,2), "points":points[-100:]}


def v19_backfill_from_v18():
    v19_init_db()
    conn = db()
    # Import compatible v18 closed_trade_journal rows if present and not already in notes.
    try:
        rows = conn.execute("SELECT * FROM closed_trade_journal ORDER BY id ASC").fetchall()
    except Exception:
        rows = []
    inserted = 0
    for r in rows:
        marker = f"v18_id:{r['id']}"
        exists = conn.execute("SELECT id FROM v19_trade_journal WHERE notes LIKE ?", (f"%{marker}%",)).fetchone()
        if exists:
            continue
        try:
            conn.execute("""
                INSERT INTO v19_trade_journal
                (opened_at, closed_at, symbol, yf_symbol, asset_type, side, strategy, entry_price, exit_price, qty, score, regime, status, pnl_pct, pnl_amount, r_multiple, holding_days, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'CLOSED', ?, ?, ?, ?, ?)
            """, (r["opened_at"] or now_text(), r["closed_at"] or now_text(), r["symbol"], r["symbol"], "US_STOCK", r["side"], r["strategy"], r["entry_price"], r["exit_price"], r["qty"] or 1, r["score"], r["regime"], r["pnl_pct"], r["pnl_amount"], r["r_multiple"], r["holding_days"], marker))
            inserted += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    v19_rebuild_equity_curve()
    return {"ok": True, "imported": inserted}


def v19_auto_journal_from_ranking(limit=5):
    # Optional helper: open watchlist trades from current ranking so the database can start collecting outcomes.
    v19_init_db()
    try:
        rank = v18_ranking(limit=int(limit), mode="daily")
    except Exception:
        rank = []
    opened = []
    for item in rank:
        decision = str(item.get("decision", "")).upper()
        if decision not in {"CALL_WATCH", "PUT_WATCH"}:
            continue
        side = "CALL" if "CALL" in decision else "PUT"
        sym = item.get("symbol")
        # Avoid duplicate open trade for same symbol/strategy.
        conn = db()
        ex = conn.execute("SELECT id FROM v19_trade_journal WHERE symbol=? AND strategy=? AND status='OPEN'", (sym, item.get("strategy","AUTO"))).fetchone()
        conn.close()
        if ex:
            continue
        res = v19_open_trade(sym, side=side, strategy=item.get("strategy","AUTO"), entry=None, qty=1, score=item.get("institutional_score") or item.get("score"), regime=(v18_regime_map().get("regime") if "v18_regime_map" in globals() else None), notes="auto_from_v19_ranking")
        opened.append(res)
    return {"ok": True, "opened": opened, "source": "v18_ranking top daily"}


def v19_escape(x):
    return (str(x) if x is not None else "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")


def v19_table(rows, cols):
    if not rows:
        return "<div class='empty'>No data yet</div>"
    th = "".join(f"<th>{v19_escape(label)}</th>" for label, key in cols)
    body = []
    for r in rows:
        tds = []
        for label, key in cols:
            val = r.get(key) if isinstance(r, dict) else getattr(r, key, "")
            if isinstance(val, float):
                val = round(val, 2)
            tds.append(f"<td>{v19_escape(val)}</td>")
        body.append("<tr>"+"".join(tds)+"</tr>")
    return f"<table class='tbl'><thead><tr>{th}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def v19_layout(title, body, active="dashboard", refresh=False):
    refresh_tag = "<meta http-equiv='refresh' content='180'>" if refresh else ""
    nav = [("Dashboard","/v19/dashboard","dashboard"),("Journal","/v19/journal","journal"),("Leaderboard","/v19/leaderboard","leaderboard"),("Equity","/v19/equity","equity"),("Outcomes","/v19/outcomes","outcomes"),("JSON","/v19/api/snapshot","json")]
    links = "".join([f"<a class='{ 'active' if key==active else '' }' href='{href}'>{label}</a>" for label, href, key in nav])
    css = """
    body{margin:0;background:#0b1020;color:#e5edf7;font-family:Arial,Helvetica,sans-serif}.wrap{max-width:1320px;margin:auto;padding:24px}.top{display:flex;justify-content:space-between;gap:18px;align-items:center}.brand{display:flex;gap:12px;align-items:center}.logo{background:linear-gradient(135deg,#f59e0b,#2563eb);padding:10px;border-radius:12px;font-weight:800}.nav a{color:#b8c4d6;text-decoration:none;margin-left:8px;padding:8px 12px;border-radius:999px;background:#151c32}.nav a.active{background:#2563eb;color:white}.grid{display:grid;gap:14px;margin:16px 0}.grid-2{grid-template-columns:1fr 1fr}.grid-3{grid-template-columns:repeat(3,1fr)}.grid-4{grid-template-columns:repeat(4,1fr)}.card,.section{background:#121a2e;border:1px solid #26334f;border-radius:16px;box-shadow:0 10px 30px #0004}.card{padding:18px}.card .label{font-size:12px;text-transform:uppercase;color:#94a3b8}.card .value{font-size:26px;font-weight:800;margin:8px 0}.card .sub{color:#9fb0c8;font-size:12px}.section h2{margin:0;padding:16px 18px;border-bottom:1px solid #26334f}.section-body{padding:14px 18px;overflow:auto}.tbl{width:100%;border-collapse:collapse}.tbl th{color:#a8bad3;text-transform:uppercase;font-size:12px}.tbl td,.tbl th{padding:8px;border-bottom:1px solid #26334f;text-align:left}.empty{padding:16px;color:#94a3b8;border:1px dashed #334155;border-radius:12px}.code{white-space:pre-wrap;background:#070b16;border:1px solid #1f2a44;border-radius:12px;padding:12px;color:#c7d2fe;font-size:12px}.button{display:inline-block;color:white;background:#1d4ed8;text-decoration:none;padding:10px 14px;border-radius:10px;margin:4px}@media(max-width:900px){.grid-2,.grid-3,.grid-4{grid-template-columns:1fr}.top{display:block}.nav{margin-top:12px}}
    """
    return f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>{refresh_tag}<title>{v19_escape(title)}</title><style>{css}</style></head><body><div class='wrap'><div class='top'><div class='brand'><div class='logo'>V19</div><div><h1>{v19_escape(title)}</h1><div style='color:#94a3b8'>{V19_VERSION} · {now_text()}</div></div></div><div class='nav'>{links}</div></div>{body}<p style='text-align:center;color:#718096;margin:34px 0'>True journal database. Research cockpit only. Not investment advice.</p></div></body></html>"


def v19_dashboard_body():
    stats = v19_strategy_stats()
    eq = v19_equity_curve()
    overall = stats.get("overall", {})
    live = []
    try:
        live = v18_ranking(10,"daily")
    except Exception:
        live = []
    cards = f"""
    <div class='grid grid-4'>
      <div class='card'><div class='label'>Closed Trades</div><div class='value'>{overall.get('trades',0)}</div><div class='sub'>Real journal only</div></div>
      <div class='card'><div class='label'>Win Rate</div><div class='value'>{overall.get('win_rate',0)}%</div><div class='sub'>Closed outcomes</div></div>
      <div class='card'><div class='label'>Profit Factor</div><div class='value'>{overall.get('profit_factor',0)}</div><div class='sub'>Gross win / gross loss</div></div>
      <div class='card'><div class='label'>Expectancy</div><div class='value'>{overall.get('expectancy_pct',0)}%</div><div class='sub'>Per closed trade</div></div>
    </div>
    <div class='grid grid-3'>
      <div class='card'><div class='label'>Latest Equity</div><div class='value'>{eq.get('latest_equity',100)}</div><div class='sub'>Starts at 100</div></div>
      <div class='card'><div class='label'>Max Drawdown</div><div class='value'>{eq.get('max_drawdown_pct',0)}%</div><div class='sub'>From closed trades</div></div>
      <div class='card'><div class='label'>Open Trades</div><div class='value'>{len(v19_trade_rows('OPEN',10000))}</div><div class='sub'>Outcome tracker source</div></div>
    </div>
    """
    live_table = v19_table(live, [("Symbol","symbol"),("Decision","decision"),("Quality","quality"),("Inst","institutional_score"),("Strategy","strategy")])
    return cards + f"<div class='grid grid-2'><div class='section'><h2>Strategy Performance Database</h2><div class='section-body'>{v19_table(stats.get('strategies',[]), [('Strategy','strategy'),('Trades','trades'),('Win %','win_rate'),('PF','profit_factor'),('Expectancy %','expectancy_pct'),('Avg Win %','avg_win_pct'),('Avg Loss %','avg_loss_pct')])}</div></div><div class='section'><h2>Live Ranking Source</h2><div class='section-body'>{live_table}<a class='button' href='/v19/auto-journal?limit=5'>Auto-open Top Signals</a><a class='button' href='/v19/update-outcomes'>Update Outcomes</a></div></div></div>"


def v19_journal_body():
    open_rows = v19_trade_rows('OPEN', 100)
    closed_rows = v19_trade_rows('CLOSED', 100)
    sample = "/v19/journal/open/NVDA?side=CALL&entry=212&strategy=MOMENTUM&qty=1&stop=205&target=225"
    return f"<div class='section'><h2>How to Log a Trade</h2><div class='section-body'><div class='code'>Open: {sample}\nClose: /v19/journal/close/TRADE_ID?exit=225\nAuto outcome: /v19/update-outcomes</div></div></div><div class='grid grid-2'><div class='section'><h2>Open Trades</h2><div class='section-body'>{v19_table(open_rows, [('ID','id'),('Opened','opened_at'),('Symbol','symbol'),('Side','side'),('Strategy','strategy'),('Entry','entry_price'),('Score','score')])}</div></div><div class='section'><h2>Closed Trades</h2><div class='section-body'>{v19_table(closed_rows, [('ID','id'),('Closed','closed_at'),('Symbol','symbol'),('Side','side'),('Strategy','strategy'),('Entry','entry_price'),('Exit','exit_price'),('PnL %','pnl_pct'),('R','r_multiple')])}</div></div></div>"


def v19_leaderboard_body():
    stats = v19_strategy_stats()
    return f"<div class='section'><h2>Strategy Stats from Real Closed Trades</h2><div class='section-body'>{v19_table(stats.get('strategies',[]), [('Strategy','strategy'),('Trades','trades'),('Wins','wins'),('Losses','losses'),('Win %','win_rate'),('PF','profit_factor'),('Expectancy %','expectancy_pct'),('Avg Win %','avg_win_pct'),('Avg Loss %','avg_loss_pct')])}<div class='code'>{json.dumps(stats, ensure_ascii=False, indent=2)}</div></div></div>"


def v19_equity_body():
    eq = v19_equity_curve()
    pts = eq.get('points', [])
    spark = " ".join([f"{p.get('equity')}" for p in pts[-20:]]) or "No equity curve yet"
    return f"<div class='grid grid-3'><div class='card'><div class='label'>Latest Equity</div><div class='value'>{eq.get('latest_equity')}</div><div class='sub'>Base 100</div></div><div class='card'><div class='label'>Max Drawdown</div><div class='value'>{eq.get('max_drawdown_pct')}%</div><div class='sub'>Closed trades</div></div><div class='card'><div class='label'>Points</div><div class='value'>{len(pts)}</div><div class='sub'>Equity observations</div></div></div><div class='section'><h2>Equity Curve Latest Points</h2><div class='section-body'><div class='code'>{v19_escape(spark)}</div>{v19_table(pts[-50:], [('Trade','trade_id'),('Time','timestamp'),('Equity','equity'),('PnL %','pnl_pct'),('DD %','drawdown_pct')])}</div></div>"


def v19_outcomes_body():
    v19_init_db()
    conn = db()
    rows = [dict(r) for r in conn.execute("SELECT * FROM v19_trade_outcomes ORDER BY id DESC LIMIT 300").fetchall()]
    conn.close()
    return f"<div class='section'><h2>Outcome Database</h2><div class='section-body'><a class='button' href='/v19/update-outcomes'>Update Outcomes Now</a>{v19_table(rows, [('Trade','trade_id'),('Horizon','horizon_days'),('Symbol','symbol'),('Side','side'),('Strategy','strategy'),('Entry','entry_price'),('Mark','mark_price'),('Return %','return_pct'),('Outcome','outcome'),('Time','evaluated_at')])}</div></div>"


def v19_snapshot():
    return {"version": V19_VERSION, "time": now_text(), "journal": {"open": v19_trade_rows('OPEN',1000), "closed": v19_trade_rows('CLOSED',1000)}, "strategy_stats": v19_strategy_stats(), "equity_curve": v19_equity_curve()}


@app.route("/v19/status", methods=["GET"])
def v19_status_route():
    v19_init_db()
    return jsonify({"version": V19_VERSION, "enabled": True, "core": ["Journal Database", "Closed Trade Storage", "Outcome Tracking", "Equity Curve from real closed trades", "Expectancy from real closed trades", "Profit Factor from real closed trades", "Strategy Leaderboard from real closed trades"], "routes": ["/v19", "/v19/dashboard", "/v19/journal", "/v19/journal/open/<symbol>", "/v19/journal/close/<trade_id>", "/v19/update-outcomes", "/v19/leaderboard", "/v19/equity", "/v19/outcomes", "/v19/api/snapshot"]})

@app.route("/v19", methods=["GET"])
def v19_root_route():
    return v19_layout("V19 True Journal Terminal", v19_dashboard_body(), "dashboard", request.args.get("refresh")=="1")

@app.route("/v19/dashboard", methods=["GET"])
def v19_dashboard_route():
    return v19_layout("V19 True Performance Dashboard", v19_dashboard_body(), "dashboard", request.args.get("refresh")=="1")

@app.route("/v19/journal", methods=["GET"])
def v19_journal_route():
    return v19_layout("V19 Trade Journal Database", v19_journal_body(), "journal", request.args.get("refresh")=="1")

@app.route("/v19/journal/open/<symbol>", methods=["GET", "POST"])
def v19_journal_open_route(symbol):
    return jsonify(v19_open_trade(symbol, side=request.args.get("side","LONG"), strategy=request.args.get("strategy","MANUAL"), entry=request.args.get("entry"), qty=request.args.get("qty",1), score=request.args.get("score"), regime=request.args.get("regime"), stop=request.args.get("stop"), target=request.args.get("target"), notes=request.args.get("notes","")))

@app.route("/v19/journal/close/<int:trade_id>", methods=["GET", "POST"])
def v19_journal_close_route(trade_id):
    return jsonify(v19_close_trade(trade_id, exit_price=request.args.get("exit"), notes=request.args.get("notes","")))

@app.route("/v19/update-outcomes", methods=["GET", "POST"])
def v19_update_outcomes_route():
    return jsonify(v19_update_outcomes())

@app.route("/v19/backfill-v18", methods=["GET", "POST"])
def v19_backfill_v18_route():
    return jsonify(v19_backfill_from_v18())

@app.route("/v19/auto-journal", methods=["GET", "POST"])
def v19_auto_journal_route():
    return jsonify(v19_auto_journal_from_ranking(limit=request.args.get("limit",5)))

@app.route("/v19/leaderboard", methods=["GET"])
def v19_leaderboard_route():
    return v19_layout("V19 Strategy Leaderboard from Real Outcomes", v19_leaderboard_body(), "leaderboard", request.args.get("refresh")=="1")

@app.route("/v19/equity", methods=["GET"])
def v19_equity_route():
    return v19_layout("V19 Equity Curve from Closed Trades", v19_equity_body(), "equity", request.args.get("refresh")=="1")

@app.route("/v19/outcomes", methods=["GET"])
def v19_outcomes_route():
    return v19_layout("V19 Outcome Database", v19_outcomes_body(), "outcomes", request.args.get("refresh")=="1")

@app.route("/v19/api/snapshot", methods=["GET"])
def v19_api_snapshot_route():
    return jsonify(v19_snapshot())



# ============================================================
# V20 RESEARCH + PORTFOLIO + EXECUTION + OUTCOME ENGINE
# ============================================================
V20_VERSION = "V20 Research + Portfolio + Execution + Outcome Engine Free 100%"
V20_MIN_EDGE_SAMPLE = int(os.getenv("V20_MIN_EDGE_SAMPLE", "30"))
V20_DEFAULT_ACCOUNT_SIZE = float(os.getenv("V20_ACCOUNT_SIZE", "100000"))
V20_MAX_RISK_PER_TRADE_PCT = float(os.getenv("V20_MAX_RISK_PER_TRADE_PCT", "1.0"))
V20_MAX_SETUP_PROB_NO_SAMPLE = float(os.getenv("V20_MAX_PROB_NO_SAMPLE", "70"))


def v20_clamp(x, lo=0, hi=100):
    try:
        return max(lo, min(hi, float(x)))
    except Exception:
        return lo


def v20_grade(score):
    s = v20_clamp(score)
    if s >= 92: return "A+"
    if s >= 85: return "A"
    if s >= 78: return "B+"
    if s >= 70: return "B"
    if s >= 60: return "C+"
    if s >= 50: return "C"
    return "D"


def v20_html_escape(x):
    return (str(x) if x is not None else "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")


def v20_hist_edge(strategy=None, symbol=None):
    """True historical edge from V19 closed trade journal. Falls back to insufficient sample, not fake probability."""
    out = v19_strategy_stats() if "v19_strategy_stats" in globals() else {"overall":{}, "strategies":[]}
    strategies = out.get("strategies", []) or []
    overall = out.get("overall", {}) or {}
    pick = None
    if strategy:
        for s in strategies:
            if str(s.get("strategy","")).upper() == str(strategy).upper():
                pick = s; break
    if not pick:
        pick = overall
    trades = int(pick.get("trades") or 0)
    reliable = trades >= V20_MIN_EDGE_SAMPLE
    return {
        "scope": "strategy" if strategy and pick is not overall else "overall",
        "strategy": strategy,
        "symbol": symbol,
        "trades": trades,
        "wins": pick.get("wins", 0),
        "losses": pick.get("losses", 0),
        "win_rate": pick.get("win_rate", 0),
        "avg_win_pct": pick.get("avg_win_pct", 0),
        "avg_loss_pct": pick.get("avg_loss_pct", 0),
        "profit_factor": pick.get("profit_factor", 0),
        "expectancy_pct": pick.get("expectancy_pct", 0),
        "reliable": reliable,
        "sample_warning": "OK" if reliable else f"Insufficient closed trades. Need at least {V20_MIN_EDGE_SAMPLE} closed outcomes before treating this as statistical edge."
    }


def v20_risk_reward(entry, stop, target, side="LONG"):
    entry = safe_float(entry); stop = safe_float(stop); target = safe_float(target)
    if not entry or stop is None or target is None:
        return {"rr": None, "risk": None, "reward": None, "quality": "UNKNOWN"}
    side = str(side or "LONG").upper()
    if side in {"PUT", "SHORT", "SELL"}:
        risk = max(0, stop - entry)
        reward = max(0, entry - target)
    else:
        risk = max(0, entry - stop)
        reward = max(0, target - entry)
    rr = reward / risk if risk else None
    if rr is None: q="UNKNOWN"
    elif rr >= 2.0: q="GOOD"
    elif rr >= 1.5: q="ACCEPTABLE"
    elif rr >= 1.0: q="WEAK"
    else: q="POOR"
    return {"rr": round(rr,2) if rr is not None else None, "risk": round(risk,4), "reward": round(reward,4), "quality": q}


def v20_symbol_analysis(symbol):
    asset = normalize_asset(symbol)
    quote, closes, highs, lows, opens, volumes = get_market_data(asset)
    analysis = analyze_signal(asset, quote, closes, highs, lows, opens, volumes)
    return asset, quote, analysis


def v20_signal_quality(symbol):
    """Institutional style single-symbol trade quality review: score, grade, real edge, R:R, penalties."""
    asset, quote, a = v20_symbol_analysis(symbol)
    score = safe_float(a.get("score"), 50)
    strategy = "MOMENTUM" if score >= 70 or score <= 35 else "CORE_TREND"
    side = "CALL" if score >= 70 else ("PUT" if score <= 35 else "WAIT")
    reasons, penalties, bonuses = [], [], []

    rsi = safe_float(a.get("rsi"))
    if side == "CALL" and rsi is not None:
        if rsi >= 80:
            penalties.append({"name":"Extreme overbought", "points":15, "why":"RSI >= 80; late-cycle chase risk"})
        elif rsi >= 75:
            penalties.append({"name":"Overbought", "points":10, "why":"RSI >= 75; wait for pullback"})
        elif rsi >= 70:
            penalties.append({"name":"Mild overbought", "points":5, "why":"RSI >= 70; reduce size"})
    if side == "PUT" and rsi is not None:
        if rsi <= 20:
            penalties.append({"name":"Extreme oversold", "points":15, "why":"RSI <= 20; rebound risk"})
        elif rsi <= 25:
            penalties.append({"name":"Oversold", "points":10, "why":"RSI <= 25; avoid chasing downside"})
        elif rsi <= 30:
            penalties.append({"name":"Mild oversold", "points":5, "why":"RSI <= 30; wait for rebound sell"})

    regime = str(a.get("regime") or "UNKNOWN")
    if side == "CALL" and "RANGE" in regime:
        penalties.append({"name":"Range regime", "points":5, "why":"Bullish setup but market regime is range/low volatility"})
    if side == "CALL" and "DOWNTREND" in regime:
        penalties.append({"name":"Regime conflict", "points":18, "why":"CALL idea conflicts with downtrend regime"})
    if side == "PUT" and "UPTREND" in regime:
        penalties.append({"name":"Regime conflict", "points":18, "why":"PUT idea conflicts with uptrend regime"})

    breadth = v18_breadth_engine() if "v18_breadth_engine" in globals() else {}
    breadth_score = safe_float(breadth.get("breadth_score"), 50)
    if side == "CALL" and breadth_score < 45:
        penalties.append({"name":"Weak breadth", "points":8, "why":"Market participation is weak for long setup"})
    if side == "PUT" and breadth_score > 60:
        penalties.append({"name":"Strong breadth", "points":8, "why":"Market participation is strong against short setup"})
    if side == "CALL" and breadth_score >= 60:
        bonuses.append({"name":"Breadth support", "points":5, "why":"Market breadth supports long bias"})
    if side == "PUT" and breadth_score <= 40:
        bonuses.append({"name":"Breadth support", "points":5, "why":"Market breadth supports short bias"})

    price = safe_float(a.get("price"))
    atr = safe_float(a.get("atr")) or (price*0.02 if price else None)
    if price and atr:
        if side == "CALL":
            entry = price - atr*0.30
            stop = price - atr*1.50
            target = price + atr*2.00
        elif side == "PUT":
            entry = price + atr*0.30
            stop = price + atr*1.50
            target = price - atr*2.00
        else:
            entry = price; stop = None; target = None
    else:
        entry = stop = target = None
    rr = v20_risk_reward(entry, stop, target, side)
    if rr.get("rr") is not None:
        if rr["rr"] < 1.0:
            penalties.append({"name":"Poor R:R", "points":12, "why":"Reward/risk below 1.0R"})
        elif rr["rr"] < 1.5:
            penalties.append({"name":"Weak R:R", "points":6, "why":"Reward/risk below preferred 1.5R"})
        elif rr["rr"] >= 2.0:
            bonuses.append({"name":"Good R:R", "points":5, "why":"Reward/risk >= 2R"})

    edge = v20_hist_edge(strategy=strategy, symbol=asset.get("symbol"))
    hist_mod = 0
    if edge.get("reliable"):
        exp = safe_float(edge.get("expectancy_pct"), 0)
        pf = safe_float(edge.get("profit_factor"), 0)
        wr = safe_float(edge.get("win_rate"), 0)
        hist_mod += max(-12, min(12, exp*2.0))
        if pf >= 1.5: hist_mod += 6
        elif pf < 1 and edge.get("trades",0) >= V20_MIN_EDGE_SAMPLE: hist_mod -= 8
        if wr >= 60: hist_mod += 3
        elif wr < 45: hist_mod -= 3
    else:
        penalties.append({"name":"No statistical edge yet", "points":3, "why":"Closed-trade sample is still too small; cap displayed probability"})

    penalty_points = sum(safe_float(p.get("points"),0) for p in penalties)
    bonus_points = sum(safe_float(b.get("points"),0) for b in bonuses)
    final_score = v20_clamp(score - penalty_points + bonus_points + hist_mod)
    grade = v20_grade(final_score)
    synthetic_prob = max(35, min(82, 50 + (final_score-50)*0.45))
    if not edge.get("reliable"):
        synthetic_prob = min(synthetic_prob, V20_MAX_SETUP_PROB_NO_SAMPLE)
    if edge.get("reliable"):
        probability_type = "historical-adjusted"
        displayed_probability = round((safe_float(edge.get("win_rate"),50)*0.55 + synthetic_prob*0.45),2)
    else:
        probability_type = "model-confidence-capped-not-real-probability"
        displayed_probability = round(synthetic_prob,2)

    size_pct = 0
    if side != "WAIT":
        if final_score >= 90: size_pct = 75
        elif final_score >= 82: size_pct = 55
        elif final_score >= 72: size_pct = 35
        elif final_score >= 60: size_pct = 20
        else: size_pct = 0
        if any("overbought" in p.get("name","").lower() or "oversold" in p.get("name","").lower() for p in penalties):
            size_pct = min(size_pct, 40)
        if rr.get("rr") is not None and rr.get("rr") < 1.5:
            size_pct = min(size_pct, 35)
    action = "WAIT" if side == "WAIT" or final_score < 60 else ("PULLBACK_BUY" if side=="CALL" and rsi and rsi>=70 else ("REBOUND_SELL" if side=="PUT" and rsi and rsi<=30 else side))

    return {
        "version": V20_VERSION,
        "symbol": asset.get("display"),
        "asset_type": asset.get("asset_type"),
        "side": side,
        "action": action,
        "strategy": strategy,
        "price": price,
        "base_score": round(score,2),
        "final_score": round(final_score,2),
        "setup_grade": grade,
        "displayed_probability_pct": displayed_probability,
        "probability_type": probability_type,
        "historical_edge": edge,
        "risk_reward": rr,
        "suggested_size_pct_of_normal": size_pct,
        "analysis": {"regime": regime, "rsi": rsi, "atr": atr, "trend_alignment": a.get("alignment"), "reasons": a.get("reasons",[])},
        "breadth": {"score": breadth_score, "regime": breadth.get("breadth_regime") or breadth.get("regime")},
        "penalties": penalties,
        "bonuses": bonuses,
        "history_modifier": round(hist_mod,2),
        "trade_plan": {"entry": round(entry,4) if entry else None, "stop": round(stop,4) if stop else None, "target": round(target,4) if target else None},
        "institutional_note": "This is research support. Probability is capped until enough closed outcomes exist in the journal."
    }


def v20_quality_rows(limit=20, mode="daily"):
    base = v18_ranking(max(int(limit),20), mode) if "v18_ranking" in globals() else {"top":[]}
    rows=[]
    for r in base.get("top",[]):
        sym = r.get("symbol") or r.get("display")
        if not sym: continue
        try:
            q = v20_signal_quality(sym)
            row = dict(r)
            row.update({
                "v20_score": q.get("final_score"),
                "setup_grade": q.get("setup_grade"),
                "action": q.get("action"),
                "probability_type": q.get("probability_type"),
                "displayed_probability_pct": q.get("displayed_probability_pct"),
                "edge_trades": q.get("historical_edge",{}).get("trades"),
                "expectancy_pct": q.get("historical_edge",{}).get("expectancy_pct"),
                "profit_factor": q.get("historical_edge",{}).get("profit_factor"),
                "rr": q.get("risk_reward",{}).get("rr"),
                "size_pct": q.get("suggested_size_pct_of_normal"),
                "penalty_count": len(q.get("penalties",[])),
                "decision": q.get("action")
            })
            rows.append(row)
        except Exception as e:
            row=dict(r); row["v20_error"]=str(e)[:160]; rows.append(row)
    rows.sort(key=lambda x: safe_float(x.get("v20_score"),0), reverse=True)
    return {"version": V20_VERSION, "mode": mode, "time": now_text(), "top": rows[:int(limit)], "source": "v18 ranking + v20 institutional signal quality formula"}


def v20_execution_plan(symbol):
    q = v20_signal_quality(symbol)
    tp = q.get("trade_plan",{})
    rr = q.get("risk_reward",{})
    edge = q.get("historical_edge",{})
    return {
        "symbol": q.get("symbol"),
        "action": q.get("action"),
        "grade": q.get("setup_grade"),
        "entry": tp.get("entry"),
        "stop": tp.get("stop"),
        "target": tp.get("target"),
        "rr": rr.get("rr"),
        "suggested_size_pct_of_normal": q.get("suggested_size_pct_of_normal"),
        "journal_url_example": f"/v19/journal/open/{q.get('symbol')}?side={q.get('side')}&entry={tp.get('entry')}&strategy={q.get('strategy')}&qty=1&stop={tp.get('stop')}&target={tp.get('target')}",
        "edge": edge,
        "note": "Use journal URL after actual execution, not just because a signal appears."
    }


def v20_strategy_leaderboard():
    stats = v19_strategy_stats() if "v19_strategy_stats" in globals() else {"overall":{}, "strategies":[]}
    live = v20_quality_rows(30,"daily").get("top",[])
    live_by = {}
    for r in live:
        s = str(r.get("strategy") or "UNKNOWN")
        d = live_by.setdefault(s, {"strategy":s,"live_setups":0,"avg_v20_score":0,"grades":{}})
        d["live_setups"] += 1
        d["avg_v20_score"] += safe_float(r.get("v20_score"),0)
        g = r.get("setup_grade") or "NA"
        d["grades"][g]=d["grades"].get(g,0)+1
    for d in live_by.values():
        d["avg_v20_score"] = round(d["avg_v20_score"]/max(1,d["live_setups"]),2)
    return {"version": V20_VERSION, "closed_performance": stats, "live_distribution": sorted(live_by.values(), key=lambda x:x["avg_v20_score"], reverse=True)}


def v20_snapshot():
    return {
        "version": V20_VERSION,
        "time": now_text(),
        "dashboard": {
            "top_setups": v20_quality_rows(10,"daily"),
            "strategy_leaderboard": v20_strategy_leaderboard(),
            "journal": v19_snapshot() if "v19_snapshot" in globals() else {},
            "portfolio": v18_portfolio_exposure() if "v18_portfolio_exposure" in globals() else {},
            "risk": v18_monte_carlo(runs=10000) if "v18_monte_carlo" in globals() else {},
            "internals": v18_breadth_engine() if "v18_breadth_engine" in globals() else {}
        }
    }


def v20_table(rows, cols, empty="No data"):
    if not rows:
        return f"<div class='empty'>{empty}</div>"
    th = "".join(f"<th>{v20_html_escape(c[0])}</th>" for c in cols)
    body=[]
    for r in rows:
        tds=[]
        for title,key in cols:
            val = r.get(key,"")
            cls=""
            if key in {"action","decision"}:
                sval=str(val).upper()
                cls="badge green" if "CALL" in sval or "BUY" in sval else ("badge red" if "PUT" in sval or "SELL" in sval else "badge yellow")
                val=f"<span class='{cls}'>{v20_html_escape(val)}</span>"
            else:
                val=v20_html_escape(val)
            tds.append(f"<td>{val}</td>")
        body.append("<tr>"+"".join(tds)+"</tr>")
    return f"<table><thead><tr>{th}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def v20_css():
    return """
    <style>
    body{margin:0;background:#111827;color:#e5e7eb;font-family:Inter,Arial,sans-serif}.wrap{max-width:1180px;margin:auto;padding:24px}
    .nav a{color:#dbeafe;text-decoration:none;margin-right:12px;padding:8px 12px;border-radius:14px;background:#1f2937}.nav a.active{background:#2563eb}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.card{background:#1f2937;border:1px solid #374151;border-radius:18px;padding:18px;box-shadow:0 8px 24px rgba(0,0,0,.22)}
    h1{font-size:28px;margin:8px 0}h2{font-size:19px;margin:0 0 12px}.muted{color:#9ca3af;font-size:13px}.big{font-size:28px;font-weight:800}.section{margin-top:18px}table{width:100%;border-collapse:collapse;font-size:13px}th,td{border-bottom:1px solid #374151;padding:8px;text-align:left}th{color:#93c5fd}.badge{display:inline-block;padding:4px 8px;border-radius:999px;font-weight:700}.green{background:#064e3b;color:#bbf7d0}.red{background:#7f1d1d;color:#fecaca}.yellow{background:#713f12;color:#fde68a}.empty{border:1px dashed #4b5563;border-radius:14px;padding:14px;color:#9ca3af}pre{white-space:pre-wrap;background:#0b1220;border-radius:14px;padding:14px;overflow:auto}.two{display:grid;grid-template-columns:2fr 1fr;gap:14px}@media(max-width:900px){.grid,.two{grid-template-columns:1fr}}
    </style>
    """


def v20_layout(title, body, active="dashboard"):
    links=[("Dashboard","/v20/dashboard","dashboard"),("Ranking","/v20/ranking","ranking"),("Leaderboard","/v20/leaderboard","leaderboard"),("Journal","/v19/journal","journal"),("Equity","/v19/equity","equity"),("JSON","/v20/api/snapshot","json")]
    nav=" ".join(f"<a class='{ 'active' if k==active else ''}' href='{u}'>{n}</a>" for n,u,k in links)
    return Response(f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>{v20_css()}<title>{v20_html_escape(title)}</title></head><body><div class='wrap'><div class='nav'>{nav}</div><h1>{v20_html_escape(title)}</h1><div class='muted'>{V20_VERSION} • {now_text()}</div>{body}<div class='muted section'>Free data stack. Research support only. Not investment advice.</div></div></body></html>", mimetype="text/html")


def v20_dashboard_body():
    rank = v20_quality_rows(12,"daily")
    rows = rank.get("top",[])
    stats = v19_strategy_stats() if "v19_strategy_stats" in globals() else {"overall":{}}
    overall = stats.get("overall",{})
    best = rows[0] if rows else {}
    cards = f"""
    <div class='grid section'>
      <div class='card'><div class='muted'>Win Rate</div><div class='big'>{overall.get('win_rate',0)}%</div><div class='muted'>Closed trades: {overall.get('trades',0)}</div></div>
      <div class='card'><div class='muted'>Profit Factor</div><div class='big'>{overall.get('profit_factor',0)}</div><div class='muted'>From real closed journal</div></div>
      <div class='card'><div class='muted'>Expectancy</div><div class='big'>{overall.get('expectancy_pct',0)}%</div><div class='muted'>Actual outcome database</div></div>
      <div class='card'><div class='muted'>Best Current Setup</div><div class='big'>{v20_html_escape(best.get('symbol','N/A'))}</div><div class='muted'>Grade {v20_html_escape(best.get('setup_grade','N/A'))} • Score {best.get('v20_score','N/A')}</div></div>
    </div>"""
    table = v20_table(rows, [("Symbol","symbol"),("Action","action"),("Grade","setup_grade"),("V20","v20_score"),("Prob","displayed_probability_pct"),("R:R","rr"),("Size%","size_pct"),("Trades","edge_trades"),("PF","profit_factor"),("Exp%","expectancy_pct")])
    return cards + f"<div class='section two'><div class='card'><h2>Top Institutional Setups</h2>{table}</div><div class='card'><h2>Probability Policy</h2><p>V20 caps model probability until the closed journal has enough samples. This prevents synthetic 80–90% probabilities from being mistaken for real statistical edge.</p><pre>{v20_html_escape(json.dumps({'min_edge_sample':V20_MIN_EDGE_SAMPLE,'max_prob_without_sample':V20_MAX_SETUP_PROB_NO_SAMPLE}, indent=2))}</pre></div></div>"


def v20_ranking_body():
    mode = request.args.get("mode","daily")
    rank = v20_quality_rows(20,mode)
    table = v20_table(rank.get("top",[]), [("Symbol","symbol"),("Action","action"),("Grade","setup_grade"),("V20 Score","v20_score"),("Base","quality_score"),("Prob%","displayed_probability_pct"),("Prob Type","probability_type"),("R:R","rr"),("Size%","size_pct"),("Strategy","strategy")])
    return f"<div class='section card'><h2>V20 Institutional Quality Ranking</h2><p class='muted'>Mode: {v20_html_escape(mode)}</p>{table}</div>"


def v20_leaderboard_body():
    lb = v20_strategy_leaderboard()
    perf = lb.get("closed_performance",{})
    live = lb.get("live_distribution",[])
    perf_table = v20_table(perf.get("strategies",[]), [("Strategy","strategy"),("Trades","trades"),("Win%","win_rate"),("Avg Win","avg_win_pct"),("Avg Loss","avg_loss_pct"),("PF","profit_factor"),("Expectancy","expectancy_pct")], "No closed strategy outcomes yet")
    live_table = v20_table(live, [("Strategy","strategy"),("Live Setups","live_setups"),("Avg V20","avg_v20_score")], "No live setups")
    return f"<div class='section two'><div class='card'><h2>True Strategy Performance</h2>{perf_table}</div><div class='card'><h2>Live Strategy Distribution</h2>{live_table}</div></div>"


@app.route("/v20/status", methods=["GET"])
def v20_status_route():
    return jsonify({"version": V20_VERSION, "enabled": True, "modules":["Signal Quality Formula", "Historical Edge", "Setup Grade", "Real Trade Quality", "Execution Plan", "Outcome-aware Ranking"], "routes":["/v20", "/v20/dashboard", "/v20/ranking", "/v20/quality/<symbol>", "/v20/execution/<symbol>", "/v20/edge", "/v20/leaderboard", "/v20/api/snapshot"]})

@app.route("/v20", methods=["GET"])
@app.route("/v20/dashboard", methods=["GET"])
def v20_dashboard_route():
    return v20_layout("V20 Institutional Signal Quality Terminal", v20_dashboard_body(), "dashboard")

@app.route("/v20/ranking", methods=["GET"])
def v20_ranking_route():
    return v20_layout("V20 Outcome-Aware Ranking", v20_ranking_body(), "ranking")

@app.route("/v20/leaderboard", methods=["GET"])
def v20_leaderboard_route():
    return v20_layout("V20 True Strategy Leaderboard", v20_leaderboard_body(), "leaderboard")

@app.route("/v20/quality/<symbol>", methods=["GET"])
def v20_quality_route(symbol):
    return jsonify(v20_signal_quality(symbol))

@app.route("/v20/execution/<symbol>", methods=["GET"])
def v20_execution_route(symbol):
    return jsonify(v20_execution_plan(symbol))

@app.route("/v20/edge", methods=["GET"])
def v20_edge_route():
    return jsonify(v20_hist_edge(strategy=request.args.get("strategy"), symbol=request.args.get("symbol")))

@app.route("/v20/api/snapshot", methods=["GET"])
def v20_snapshot_route():
    return jsonify(v20_snapshot())

# ============================================================
# V21 CORE DATABASE LAYER - TRUE JOURNAL / CLOSED OUTCOMES
# ============================================================
V21_VERSION = "V21 Core Database Layer Free 100%"


def v21_now_iso():
    try:
        return (datetime.now(timezone.utc) + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def v21_init_db():
    """Create the real trade journal database used by V21.
    This is deliberately independent from signal-audit tables so closed outcomes are not mixed with theoretical signals.
    """
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS v21_trade_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            strategy TEXT NOT NULL,
            entry_price REAL NOT NULL,
            stop_price REAL,
            target_price REAL,
            qty REAL DEFAULT 1,
            entry_time TEXT,
            exit_price REAL,
            exit_time TEXT,
            pnl REAL,
            pnl_pct REAL,
            r_multiple REAL,
            result TEXT,
            status TEXT NOT NULL DEFAULT 'OPEN',
            notes TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_v21_trade_status ON v21_trade_journal(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_v21_trade_symbol ON v21_trade_journal(symbol)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_v21_trade_strategy ON v21_trade_journal(strategy)")
    conn.commit()
    conn.close()


def v21_side_factor(side):
    s = str(side or "").strip().upper()
    if s in {"PUT", "SELL", "SHORT", "BEAR", "BEARISH"}:
        return -1
    return 1


def v21_clean_strategy(strategy):
    s = str(strategy or "MANUAL").strip().upper().replace(" ", "_")
    return s or "MANUAL"


def v21_calc_trade_metrics(side, entry, exit_price, stop=None, qty=1):
    entry = safe_float(entry)
    exit_price = safe_float(exit_price)
    stop = safe_float(stop)
    qty = safe_float(qty, 1) or 1
    if entry is None or exit_price is None or entry <= 0:
        return {"pnl": 0.0, "pnl_pct": 0.0, "r_multiple": 0.0, "result": "FLAT"}
    factor = v21_side_factor(side)
    pnl_per_share = (exit_price - entry) * factor
    pnl = pnl_per_share * qty
    pnl_pct = (pnl_per_share / entry) * 100
    if stop is not None and stop > 0:
        risk_per_share = abs(entry - stop)
    else:
        risk_per_share = max(entry * 0.02, 0.01)
    r_multiple = pnl_per_share / risk_per_share if risk_per_share else 0.0
    if r_multiple > 0:
        result = "WIN"
    elif r_multiple < 0:
        result = "LOSS"
    else:
        result = "FLAT"
    return {
        "pnl": round(float(pnl), 6),
        "pnl_pct": round(float(pnl_pct), 6),
        "r_multiple": round(float(r_multiple), 6),
        "result": result,
    }


def v21_open_trade(symbol, side, entry, strategy="MANUAL", qty=1, stop=None, target=None, notes=""):
    v21_init_db()
    symbol = str(symbol or "").strip().upper()
    side = str(side or "CALL").strip().upper()
    strategy = v21_clean_strategy(strategy)
    entry = safe_float(entry)
    qty = safe_float(qty, 1) or 1
    stop = safe_float(stop)
    target = safe_float(target)
    if not symbol:
        raise ValueError("symbol is required")
    if entry is None or entry <= 0:
        raise ValueError("entry must be a positive number")
    now = v21_now_iso()
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO v21_trade_journal
        (created_at, updated_at, symbol, side, strategy, entry_price, stop_price, target_price, qty, entry_time, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)
    """, (now, now, symbol, side, strategy, entry, stop, target, qty, now, str(notes or "")[:1000]))
    trade_id = cur.lastrowid
    conn.commit()
    conn.close()
    return v21_get_trade(trade_id)


def v21_get_trade(trade_id):
    v21_init_db()
    conn = db()
    row = conn.execute("SELECT * FROM v21_trade_journal WHERE id=?", (int(trade_id),)).fetchone()
    conn.close()
    return dict(row) if row else None


def v21_close_trade(trade_id, exit_price, notes_append=""):
    v21_init_db()
    trade = v21_get_trade(trade_id)
    if not trade:
        raise ValueError("trade not found")
    if str(trade.get("status", "")).upper() == "CLOSED":
        return trade
    exit_price = safe_float(exit_price)
    if exit_price is None or exit_price <= 0:
        raise ValueError("exit must be a positive number")
    metrics = v21_calc_trade_metrics(
        trade.get("side"), trade.get("entry_price"), exit_price,
        stop=trade.get("stop_price"), qty=trade.get("qty")
    )
    now = v21_now_iso()
    notes = (trade.get("notes") or "")
    if notes_append:
        notes = (notes + " | " + str(notes_append))[:1000]
    conn = db()
    conn.execute("""
        UPDATE v21_trade_journal
        SET updated_at=?, exit_price=?, exit_time=?, pnl=?, pnl_pct=?, r_multiple=?, result=?, status='CLOSED', notes=?
        WHERE id=?
    """, (now, exit_price, now, metrics["pnl"], metrics["pnl_pct"], metrics["r_multiple"], metrics["result"], notes, int(trade_id)))
    conn.commit()
    conn.close()
    return v21_get_trade(trade_id)


def v21_rows(status=None, limit=250):
    v21_init_db()
    limit = int(safe_float(limit, 250) or 250)
    conn = db()
    if status:
        rows = conn.execute(
            "SELECT * FROM v21_trade_journal WHERE status=? ORDER BY id DESC LIMIT ?",
            (str(status).upper(), limit)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM v21_trade_journal ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def v21_closed_rows(limit=5000):
    v21_init_db()
    conn = db()
    rows = conn.execute("""
        SELECT * FROM v21_trade_journal
        WHERE status='CLOSED' AND r_multiple IS NOT NULL
        ORDER BY id ASC LIMIT ?
    """, (int(limit),)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def v21_performance(rows=None):
    rows = rows if rows is not None else v21_closed_rows()
    n = len(rows)
    if n == 0:
        return {
            "trades": 0, "wins": 0, "losses": 0, "flats": 0,
            "win_rate_pct": 0.0, "avg_win_r": 0.0, "avg_loss_r": 0.0,
            "profit_factor": 0.0, "expectancy_r": 0.0,
            "total_r": 0.0, "max_drawdown_r": 0.0,
            "sample_warning": "Need 50-100 closed trades before trusting statistics."
        }
    rs = [safe_float(r.get("r_multiple"), 0) or 0 for r in rows]
    wins = [x for x in rs if x > 0]
    losses = [x for x in rs if x < 0]
    flats = [x for x in rs if x == 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = gross_win / gross_loss if gross_loss else (gross_win if gross_win else 0.0)
    expectancy = sum(rs) / n if n else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    equity = []
    cur = 0.0
    peak = 0.0
    max_dd = 0.0
    for x in rs:
        cur += x
        peak = max(peak, cur)
        max_dd = min(max_dd, cur - peak)
        equity.append(round(cur, 4))
    return {
        "trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "flats": len(flats),
        "win_rate_pct": round(len(wins) / n * 100, 2),
        "avg_win_r": round(avg_win, 4),
        "avg_loss_r": round(avg_loss, 4),
        "profit_factor": round(pf, 4),
        "expectancy_r": round(expectancy, 4),
        "total_r": round(sum(rs), 4),
        "max_drawdown_r": round(abs(max_dd), 4),
        "sample_warning": "Reliable" if n >= 50 else "Low sample: collect at least 50 closed trades."
    }


def v21_strategy_stats():
    rows = v21_closed_rows()
    groups = {}
    for r in rows:
        key = v21_clean_strategy(r.get("strategy"))
        groups.setdefault(key, []).append(r)
    out = []
    for strategy, items in groups.items():
        p = v21_performance(items)
        p["strategy"] = strategy
        out.append(p)
    out.sort(key=lambda x: (x.get("expectancy_r", 0), x.get("profit_factor", 0), x.get("trades", 0)), reverse=True)
    return out


def v21_equity_curve():
    rows = v21_closed_rows()
    curve = []
    cur = 0.0
    peak = 0.0
    for r in rows:
        r_mult = safe_float(r.get("r_multiple"), 0) or 0
        cur += r_mult
        peak = max(peak, cur)
        curve.append({
            "trade_id": r.get("id"),
            "time": r.get("exit_time") or r.get("updated_at"),
            "symbol": r.get("symbol"),
            "strategy": r.get("strategy"),
            "r": round(r_mult, 4),
            "equity_r": round(cur, 4),
            "drawdown_r": round(max(0.0, peak - cur), 4),
        })
    return curve


def v21_dashboard_snapshot():
    rows = v21_rows(limit=100)
    closed = [r for r in rows if str(r.get("status", "")).upper() == "CLOSED"]
    open_rows = [r for r in rows if str(r.get("status", "")).upper() == "OPEN"]
    perf = v21_performance(v21_closed_rows())
    return {
        "version": V21_VERSION,
        "open_trades": len(open_rows),
        "recent_trades": rows[:20],
        "performance": perf,
        "strategy_stats": v21_strategy_stats(),
        "equity_curve": v21_equity_curve()[-100:],
    }


def v21_html_escape(x):
    return str(x if x is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def v21_layout(title, body, active="dashboard"):
    nav = "".join([
        f'<a class="nav {"on" if active==k else ""}" href="{href}">{label}</a>'
        for k, label, href in [
            ("dashboard", "Dashboard", "/v21"),
            ("journal", "Journal", "/v21/journal"),
            ("stats", "Stats", "/v21/stats"),
            ("equity", "Equity", "/v21/equity"),
            ("api", "JSON", "/v21/api/snapshot"),
        ]
    ])
    return Response(f"""
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{v21_html_escape(title)}</title>
<style>
body{{margin:0;background:#0f172a;color:#e5e7eb;font-family:Arial,Helvetica,sans-serif}}.wrap{{max-width:1180px;margin:0 auto;padding:22px}}
.top{{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:16px}}h1{{font-size:28px;margin:0}}.sub{{color:#94a3b8;font-size:13px}}
.nav{{color:#cbd5e1;text-decoration:none;padding:9px 12px;border-radius:12px;background:#172036;margin-left:6px;font-size:13px}}.nav.on{{background:#2563eb;color:#fff}}
.grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}}.card{{background:#172036;border:1px solid #334155;border-radius:16px;padding:16px;box-shadow:0 8px 20px rgba(0,0,0,.18)}}
.card h3{{margin:0 0 8px;font-size:13px;color:#cbd5e1;text-transform:uppercase}}.big{{font-size:28px;font-weight:800}}.ok{{color:#22c55e}}.bad{{color:#ef4444}}.warn{{color:#f59e0b}}
table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{padding:10px;border-bottom:1px solid #334155;text-align:left}}th{{color:#93c5fd;font-size:12px;text-transform:uppercase}}.section{{margin-top:16px}}
.badge{{display:inline-block;border-radius:999px;padding:4px 8px;font-size:11px;font-weight:700;background:#334155}}.win{{background:#14532d;color:#bbf7d0}}.loss{{background:#7f1d1d;color:#fecaca}}.open{{background:#1e3a8a;color:#bfdbfe}}
pre{{white-space:pre-wrap;background:#0b1020;border-radius:14px;padding:14px;border:1px solid #334155;overflow:auto}}@media(max-width:900px){{.grid{{grid-template-columns:1fr 1fr}}.top{{display:block}}.nav{{display:inline-block;margin:6px 4px 0 0}}}}@media(max-width:560px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><div class="wrap"><div class="top"><div><h1>{v21_html_escape(title)}</h1><div class="sub">{V21_VERSION} • {v21_now_iso()} • Real closed-trade database only</div></div><div>{nav}</div></div>{body}</div></body></html>
""", mimetype="text/html")


def v21_dashboard_body():
    snap = v21_dashboard_snapshot()
    p = snap["performance"]
    stats = snap["strategy_stats"][:8]
    recent = snap["recent_trades"][:12]
    cards = f"""
    <div class="grid">
      <div class="card"><h3>Closed Trades</h3><div class="big">{p['trades']}</div><div class="sub">Real outcomes only</div></div>
      <div class="card"><h3>Win Rate</h3><div class="big">{p['win_rate_pct']}%</div><div class="sub">Wins {p['wins']} / Losses {p['losses']}</div></div>
      <div class="card"><h3>Profit Factor</h3><div class="big">{p['profit_factor']}</div><div class="sub">Gross win / gross loss</div></div>
      <div class="card"><h3>Expectancy</h3><div class="big {'ok' if p['expectancy_r']>0 else 'bad' if p['expectancy_r']<0 else ''}">{p['expectancy_r']}R</div><div class="sub">{p['sample_warning']}</div></div>
    </div>
    """
    stat_rows = "".join([f"<tr><td>{v21_html_escape(s['strategy'])}</td><td>{s['trades']}</td><td>{s['win_rate_pct']}%</td><td>{s['profit_factor']}</td><td>{s['expectancy_r']}R</td><td>{s['max_drawdown_r']}R</td></tr>" for s in stats]) or "<tr><td colspan='6'>No closed outcomes yet. Open and close trades to build real statistics.</td></tr>"
    recent_rows = "".join([f"<tr><td>{r['id']}</td><td>{v21_html_escape(r['symbol'])}</td><td>{v21_html_escape(r['side'])}</td><td>{v21_html_escape(r['strategy'])}</td><td>{r['entry_price']}</td><td>{r.get('exit_price') or ''}</td><td><span class='badge {str(r.get('status','')).lower()}'>{v21_html_escape(r.get('status'))}</span></td><td>{r.get('r_multiple') if r.get('r_multiple') is not None else ''}</td></tr>" for r in recent]) or "<tr><td colspan='8'>No trades yet.</td></tr>"
    return cards + f"""
    <div class="section card"><h3>True Strategy Leaderboard</h3><table><tr><th>Strategy</th><th>Trades</th><th>Win%</th><th>PF</th><th>Expectancy</th><th>Max DD</th></tr>{stat_rows}</table></div>
    <div class="section card"><h3>Recent Journal</h3><table><tr><th>ID</th><th>Symbol</th><th>Side</th><th>Strategy</th><th>Entry</th><th>Exit</th><th>Status</th><th>R</th></tr>{recent_rows}</table></div>
    <div class="section card"><h3>How to log a real trade</h3><pre>/v21/journal/open/NVDA?side=CALL&entry=212&stop=205&target=225&strategy=MOMENTUM&qty=1
/v21/journal/close/1?exit=225</pre></div>
    """


def v21_journal_body():
    rows = v21_rows(limit=300)
    tr = "".join([f"<tr><td>{r['id']}</td><td>{v21_html_escape(r['symbol'])}</td><td>{v21_html_escape(r['side'])}</td><td>{v21_html_escape(r['strategy'])}</td><td>{r['entry_price']}</td><td>{r.get('stop_price') or ''}</td><td>{r.get('target_price') or ''}</td><td>{r.get('exit_price') or ''}</td><td><span class='badge {str(r.get('status','')).lower()}'>{v21_html_escape(r.get('status'))}</span></td><td>{r.get('r_multiple') if r.get('r_multiple') is not None else ''}</td><td>{v21_html_escape(r.get('entry_time'))}</td></tr>" for r in rows]) or "<tr><td colspan='11'>No journal entries yet.</td></tr>"
    return f"<div class='card'><h3>Real Trade Journal</h3><table><tr><th>ID</th><th>Symbol</th><th>Side</th><th>Strategy</th><th>Entry</th><th>Stop</th><th>Target</th><th>Exit</th><th>Status</th><th>R</th><th>Entry Time</th></tr>{tr}</table></div>"


def v21_stats_body():
    p = v21_performance(v21_closed_rows())
    stats = v21_strategy_stats()
    rows = "".join([f"<tr><td>{v21_html_escape(s['strategy'])}</td><td>{s['trades']}</td><td>{s['wins']}</td><td>{s['losses']}</td><td>{s['win_rate_pct']}%</td><td>{s['avg_win_r']}R</td><td>{s['avg_loss_r']}R</td><td>{s['profit_factor']}</td><td>{s['expectancy_r']}R</td><td>{s['total_r']}R</td></tr>" for s in stats]) or "<tr><td colspan='10'>No closed outcomes yet.</td></tr>"
    return f"""
    <div class="grid"><div class="card"><h3>All Trades</h3><div class="big">{p['trades']}</div></div><div class="card"><h3>Win Rate</h3><div class="big">{p['win_rate_pct']}%</div></div><div class="card"><h3>PF</h3><div class="big">{p['profit_factor']}</div></div><div class="card"><h3>Expectancy</h3><div class="big">{p['expectancy_r']}R</div></div></div>
    <div class="section card"><h3>Strategy Stats From Closed Trades</h3><table><tr><th>Strategy</th><th>Trades</th><th>Wins</th><th>Losses</th><th>Win%</th><th>Avg Win</th><th>Avg Loss</th><th>PF</th><th>Expectancy</th><th>Total R</th></tr>{rows}</table></div>
    """


def v21_equity_body():
    curve = v21_equity_curve()
    rows = "".join([f"<tr><td>{c['trade_id']}</td><td>{v21_html_escape(c['time'])}</td><td>{v21_html_escape(c['symbol'])}</td><td>{v21_html_escape(c['strategy'])}</td><td>{c['r']}R</td><td>{c['equity_r']}R</td><td>{c['drawdown_r']}R</td></tr>" for c in curve[-100:]]) or "<tr><td colspan='7'>No equity curve yet. Close trades first.</td></tr>"
    points = [c['equity_r'] for c in curve[-60:]]
    bars = "".join([f"<div title='{p}R' style='height:{max(4, min(120, 60 + p*8))}px;width:8px;background:#38bdf8;border-radius:4px;display:inline-block;margin-right:3px;vertical-align:bottom'></div>" for p in points]) or "<div class='sub'>No curve yet</div>"
    return f"<div class='card'><h3>Equity Curve in R</h3><div style='height:140px;display:flex;align-items:flex-end'>{bars}</div></div><div class='section card'><h3>Equity Points</h3><table><tr><th>ID</th><th>Time</th><th>Symbol</th><th>Strategy</th><th>R</th><th>Equity</th><th>DD</th></tr>{rows}</table></div>"


@app.route("/v21/status", methods=["GET"])
def v21_status_route():
    v21_init_db()
    return jsonify({
        "version": V21_VERSION,
        "enabled": True,
        "purpose": "Core Database Layer only: journal, closed trades, true stats, equity curve.",
        "routes": ["/v21", "/v21/dashboard", "/v21/journal", "/v21/journal/open/<symbol>", "/v21/journal/close/<id>", "/v21/stats", "/v21/equity", "/v21/api/snapshot"]
    })


@app.route("/v21", methods=["GET"])
@app.route("/v21/dashboard", methods=["GET"])
def v21_dashboard_route():
    return v21_layout("V21 Core Database Layer", v21_dashboard_body(), "dashboard")


@app.route("/v21/journal", methods=["GET"])
def v21_journal_route():
    return v21_layout("V21 Real Trade Journal", v21_journal_body(), "journal")


@app.route("/v21/journal/open/<symbol>", methods=["GET", "POST"])
def v21_open_trade_route(symbol):
    try:
        trade = v21_open_trade(
            symbol=symbol,
            side=request.args.get("side", "CALL"),
            entry=request.args.get("entry"),
            strategy=request.args.get("strategy", "MANUAL"),
            qty=request.args.get("qty", 1),
            stop=request.args.get("stop"),
            target=request.args.get("target"),
            notes=request.args.get("notes", "")
        )
        return jsonify({"ok": True, "trade": trade, "close_url_example": f"/v21/journal/close/{trade['id']}?exit=YOUR_EXIT_PRICE"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "example": "/v21/journal/open/NVDA?side=CALL&entry=212&stop=205&target=225&strategy=MOMENTUM&qty=1"}), 400


@app.route("/v21/journal/close/<int:trade_id>", methods=["GET", "POST"])
def v21_close_trade_route(trade_id):
    try:
        trade = v21_close_trade(trade_id, request.args.get("exit"), notes_append=request.args.get("notes", ""))
        return jsonify({"ok": True, "trade": trade, "performance": v21_performance(v21_closed_rows())})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "example": f"/v21/journal/close/{trade_id}?exit=225"}), 400


@app.route("/v21/stats", methods=["GET"])
def v21_stats_route():
    return v21_layout("V21 True Strategy Stats", v21_stats_body(), "stats")


@app.route("/v21/equity", methods=["GET"])
def v21_equity_route():
    return v21_layout("V21 Equity Curve From Closed Trades", v21_equity_body(), "equity")


@app.route("/v21/api/snapshot", methods=["GET"])
def v21_snapshot_route():
    return jsonify(v21_dashboard_snapshot())

# ============================================================
# V21.5 AUTO JOURNAL + OUTCOME DATABASE + STRATEGY PERFORMANCE DB
# ============================================================
V215_VERSION = "V21.5 Auto Journal + Outcome DB + Strategy Performance Free 100%"


def v215_init_db():
    """Persistent outcome layer built on top of the proven V21 trade journal."""
    v21_init_db()
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS v215_trade_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id INTEGER UNIQUE,
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            strategy TEXT NOT NULL,
            entry_price REAL NOT NULL,
            stop_price REAL,
            target_price REAL,
            exit_price REAL NOT NULL,
            pnl REAL,
            pnl_pct REAL,
            r_multiple REAL NOT NULL,
            result TEXT NOT NULL,
            holding_minutes REAL,
            regime TEXT,
            source TEXT,
            notes TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_v215_outcome_strategy ON v215_trade_outcomes(strategy)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_v215_outcome_symbol ON v215_trade_outcomes(symbol)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_v215_outcome_result ON v215_trade_outcomes(result)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS v215_strategy_stats (
            strategy TEXT PRIMARY KEY,
            updated_at TEXT NOT NULL,
            trades INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            flats INTEGER DEFAULT 0,
            win_rate_pct REAL DEFAULT 0,
            avg_win_r REAL DEFAULT 0,
            avg_loss_r REAL DEFAULT 0,
            profit_factor REAL DEFAULT 0,
            expectancy_r REAL DEFAULT 0,
            total_r REAL DEFAULT 0,
            max_drawdown_r REAL DEFAULT 0,
            sample_quality TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS v215_auto_journal_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            source TEXT,
            symbol TEXT,
            strategy TEXT,
            side TEXT,
            entry_price REAL,
            trade_id INTEGER,
            status TEXT,
            notes TEXT
        )
    """)
    conn.commit()
    conn.close()


def v215_parse_dt(s):
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(s)[:19], fmt)
        except Exception:
            pass
    return None


def v215_holding_minutes(entry_time, exit_time):
    a = v215_parse_dt(entry_time)
    b = v215_parse_dt(exit_time)
    if not a or not b:
        return None
    return round(max(0, (b - a).total_seconds() / 60.0), 2)


def v215_outcome_from_trade(trade, source="manual_close"):
    if not trade or str(trade.get("status", "")).upper() != "CLOSED":
        return None
    v215_init_db()
    trade_id = int(trade.get("id"))
    conn = db()
    existing = conn.execute("SELECT * FROM v215_trade_outcomes WHERE trade_id=?", (trade_id,)).fetchone()
    now = v21_now_iso()
    vals = (
        trade_id, now, str(trade.get("symbol") or "").upper(), str(trade.get("side") or "").upper(),
        v21_clean_strategy(trade.get("strategy")), safe_float(trade.get("entry_price"), 0) or 0,
        safe_float(trade.get("stop_price")), safe_float(trade.get("target_price")), safe_float(trade.get("exit_price"), 0) or 0,
        safe_float(trade.get("pnl"), 0) or 0, safe_float(trade.get("pnl_pct"), 0) or 0,
        safe_float(trade.get("r_multiple"), 0) or 0, str(trade.get("result") or "FLAT").upper(),
        v215_holding_minutes(trade.get("entry_time"), trade.get("exit_time")),
        None, source, str(trade.get("notes") or "")[:1000]
    )
    if existing:
        conn.execute("""
            UPDATE v215_trade_outcomes
            SET created_at=?, symbol=?, side=?, strategy=?, entry_price=?, stop_price=?, target_price=?, exit_price=?,
                pnl=?, pnl_pct=?, r_multiple=?, result=?, holding_minutes=?, regime=?, source=?, notes=?
            WHERE trade_id=?
        """, (now, vals[2], vals[3], vals[4], vals[5], vals[6], vals[7], vals[8], vals[9], vals[10], vals[11], vals[12], vals[13], vals[14], vals[15], vals[16], trade_id))
    else:
        conn.execute("""
            INSERT INTO v215_trade_outcomes
            (trade_id, created_at, symbol, side, strategy, entry_price, stop_price, target_price, exit_price, pnl, pnl_pct,
             r_multiple, result, holding_minutes, regime, source, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, vals)
    conn.commit()
    conn.close()
    v215_recalculate_strategy_stats()
    return v215_get_outcome(trade_id)


def v215_get_outcome(trade_id):
    v215_init_db()
    conn = db()
    row = conn.execute("SELECT * FROM v215_trade_outcomes WHERE trade_id=?", (int(trade_id),)).fetchone()
    conn.close()
    return dict(row) if row else None


def v215_outcome_rows(limit=5000):
    v215_init_db()
    conn = db()
    rows = conn.execute("SELECT * FROM v215_trade_outcomes ORDER BY id ASC LIMIT ?", (int(safe_float(limit, 5000) or 5000),)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def v215_recalculate_strategy_stats():
    v215_init_db()
    rows = v215_outcome_rows(100000)
    groups = {}
    for r in rows:
        groups.setdefault(v21_clean_strategy(r.get("strategy")), []).append({"r_multiple": r.get("r_multiple")})
    conn = db()
    now = v21_now_iso()
    for strategy, items in groups.items():
        perf = v21_performance(items)
        conn.execute("""
            INSERT INTO v215_strategy_stats
            (strategy, updated_at, trades, wins, losses, flats, win_rate_pct, avg_win_r, avg_loss_r, profit_factor,
             expectancy_r, total_r, max_drawdown_r, sample_quality)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(strategy) DO UPDATE SET
              updated_at=excluded.updated_at,
              trades=excluded.trades,
              wins=excluded.wins,
              losses=excluded.losses,
              flats=excluded.flats,
              win_rate_pct=excluded.win_rate_pct,
              avg_win_r=excluded.avg_win_r,
              avg_loss_r=excluded.avg_loss_r,
              profit_factor=excluded.profit_factor,
              expectancy_r=excluded.expectancy_r,
              total_r=excluded.total_r,
              max_drawdown_r=excluded.max_drawdown_r,
              sample_quality=excluded.sample_quality
        """, (
            strategy, now, perf["trades"], perf["wins"], perf["losses"], perf["flats"], perf["win_rate_pct"],
            perf["avg_win_r"], perf["avg_loss_r"], perf["profit_factor"], perf["expectancy_r"], perf["total_r"],
            perf["max_drawdown_r"], perf.get("sample_warning")
        ))
    conn.commit()
    conn.close()
    return v215_strategy_stats_rows()


def v215_strategy_stats_rows():
    v215_init_db()
    conn = db()
    rows = conn.execute("""
        SELECT * FROM v215_strategy_stats
        ORDER BY expectancy_r DESC, profit_factor DESC, trades DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def v215_backfill_outcomes():
    closed = v21_closed_rows(100000)
    made = []
    for trade in closed:
        out = v215_outcome_from_trade(trade, source="backfill_v21_closed")
        if out:
            made.append(out)
    return {"ok": True, "backfilled": len(made), "strategy_stats": v215_strategy_stats_rows()}


def v215_auto_journal_from_ranking(limit=5, min_grade=None):
    """Open trades from current V20 ranking so future outcomes can be measured.
    This does not send orders. It only logs research candidates into the journal.
    """
    v215_init_db()
    limit = int(safe_float(limit, 5) or 5)
    source_rows = []
    if "v20_quality_rows" in globals():
        source_rows = v20_quality_rows(limit=max(limit * 2, 10), mode=request.args.get("mode", "daily")).get("top", [])
    elif "v18_ranking" in globals():
        source_rows = v18_ranking(limit=max(limit * 2, 10), mode=request.args.get("mode", "daily")).get("top", [])
    opened = []
    skipped = []
    conn = db()
    for row in source_rows:
        if len(opened) >= limit:
            break
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        action = str(row.get("action") or row.get("decision") or "").upper()
        if "WAIT" in action:
            skipped.append({"symbol": symbol, "reason": "WAIT decision"})
            continue
        existing = conn.execute("SELECT id FROM v21_trade_journal WHERE symbol=? AND status='OPEN' LIMIT 1", (symbol,)).fetchone()
        if existing:
            skipped.append({"symbol": symbol, "reason": "already open", "trade_id": existing["id"]})
            continue
        entry = safe_float(row.get("entry") or row.get("price") or row.get("last") or row.get("underlying_price"))
        # Fallback: estimate entry from yfinance fast info if ranking did not include a price.
        if entry is None or entry <= 0:
            try:
                hist = yf.Ticker(symbol).history(period="5d", interval="1d")
                if hist is not None and len(hist) > 0:
                    entry = float(hist["Close"].dropna().iloc[-1])
            except Exception:
                entry = None
        if entry is None or entry <= 0:
            skipped.append({"symbol": symbol, "reason": "missing entry"})
            continue
        side = "PUT" if ("PUT" in action or "SELL" in action or "SHORT" in action) else "CALL"
        strategy = row.get("strategy") or row.get("setup") or "AUTO_RANKING"
        if side == "CALL":
            stop = round(entry * 0.97, 4)
            target = round(entry * 1.06, 4)
        else:
            stop = round(entry * 1.03, 4)
            target = round(entry * 0.94, 4)
        trade = v21_open_trade(symbol, side, entry, strategy=strategy, qty=1, stop=stop, target=target, notes="v21.5 auto_journal_from_ranking")
        opened.append(trade)
        conn.execute("""
            INSERT INTO v215_auto_journal_log
            (created_at, source, symbol, strategy, side, entry_price, trade_id, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (v21_now_iso(), "ranking", symbol, v21_clean_strategy(strategy), side, entry, trade.get("id"), "OPENED", "auto journal only; not a trading order"))
    conn.commit()
    conn.close()
    return {"ok": True, "opened": opened, "skipped": skipped, "source_count": len(source_rows)}


def v215_snapshot():
    v215_backfill_outcomes()
    outcomes = v215_outcome_rows(10000)
    perf = v21_performance([{"r_multiple": r.get("r_multiple")} for r in outcomes])
    return {
        "version": V215_VERSION,
        "time": v21_now_iso(),
        "open_trades": len([r for r in v21_rows(limit=10000) if str(r.get("status", "")).upper()=="OPEN"]),
        "closed_outcomes": len(outcomes),
        "performance": perf,
        "strategy_performance_db": v215_strategy_stats_rows(),
        "recent_outcomes": outcomes[-20:][::-1],
        "equity_curve": v21_equity_curve()[-200:],
    }


def v215_badge(x):
    s = str(x or "").upper()
    cls = "win" if s == "WIN" else "loss" if s == "LOSS" else "open"
    return f"<span class='badge {cls}'>{v21_html_escape(s)}</span>"


def v215_layout(title, body, active="dashboard"):
    nav = "".join([
        f'<a class="nav {"on" if active==k else ""}" href="{href}">{label}</a>'
        for k, label, href in [
            ("dashboard", "Dashboard", "/v21-5"),
            ("journal", "Journal", "/v21-5/journal"),
            ("outcomes", "Outcomes", "/v21-5/outcomes"),
            ("stats", "Strategy DB", "/v21-5/strategy-db"),
            ("equity", "Equity", "/v21-5/equity"),
            ("json", "JSON", "/v21-5/api/snapshot"),
        ]
    ])
    return v21_layout(title, body.replace("/v21/", "/v21-5/"), active="dashboard").get_data(as_text=True).replace("</div></body></html>", f"<div class='section card'><h3>V21.5 Navigation</h3>{nav}</div></div></body></html>")


def v215_dashboard_body():
    snap = v215_snapshot()
    p = snap["performance"]
    cards = f"""
    <div class="grid">
      <div class="card"><h3>Closed Outcomes</h3><div class="big">{p['trades']}</div><div class="sub">Outcome DB rows</div></div>
      <div class="card"><h3>Win Rate</h3><div class="big">{p['win_rate_pct']}%</div><div class="sub">Wins {p['wins']} / Losses {p['losses']}</div></div>
      <div class="card"><h3>Profit Factor</h3><div class="big">{p['profit_factor']}</div><div class="sub">Real outcomes only</div></div>
      <div class="card"><h3>Expectancy</h3><div class="big {'ok' if p['expectancy_r']>0 else 'bad' if p['expectancy_r']<0 else ''}">{p['expectancy_r']}R</div><div class="sub">{p['sample_warning']}</div></div>
    </div>
    """
    strat_rows = "".join([f"<tr><td>{v21_html_escape(s['strategy'])}</td><td>{s['trades']}</td><td>{s['win_rate_pct']}%</td><td>{s['profit_factor']}</td><td>{s['expectancy_r']}R</td><td>{s['total_r']}R</td><td>{s['sample_quality']}</td></tr>" for s in snap["strategy_performance_db"]]) or "<tr><td colspan='7'>No strategy outcomes yet.</td></tr>"
    out_rows = "".join([f"<tr><td>{o['trade_id']}</td><td>{v21_html_escape(o['symbol'])}</td><td>{v21_html_escape(o['strategy'])}</td><td>{v21_html_escape(o['side'])}</td><td>{o['entry_price']}</td><td>{o['exit_price']}</td><td>{v215_badge(o['result'])}</td><td>{o['r_multiple']}R</td></tr>" for o in snap["recent_outcomes"][:12]]) or "<tr><td colspan='8'>No closed outcomes yet.</td></tr>"
    return cards + f"""
    <div class="section card"><h3>Strategy Performance Database</h3><table><tr><th>Strategy</th><th>Trades</th><th>Win%</th><th>PF</th><th>Expectancy</th><th>Total R</th><th>Sample</th></tr>{strat_rows}</table></div>
    <div class="section card"><h3>Recent Closed Outcomes</h3><table><tr><th>ID</th><th>Symbol</th><th>Strategy</th><th>Side</th><th>Entry</th><th>Exit</th><th>Result</th><th>R</th></tr>{out_rows}</table></div>
    <div class="section card"><h3>Auto Journal</h3><pre>/v21-5/auto-journal?limit=5
/v21-5/journal/close/1?exit=220
/v21-5/backfill</pre></div>
    """


@app.route("/v21-5/status", methods=["GET"])
def v215_status_route():
    v215_init_db()
    return jsonify({
        "version": V215_VERSION,
        "enabled": True,
        "modules": ["Auto Journal", "Outcome Database", "Strategy Performance Database", "Backfill from V21 closed trades"],
        "routes": ["/v21-5", "/v21-5/dashboard", "/v21-5/journal", "/v21-5/outcomes", "/v21-5/strategy-db", "/v21-5/equity", "/v21-5/auto-journal", "/v21-5/backfill", "/v21-5/api/snapshot"]
    })


@app.route("/v21-5", methods=["GET"])
@app.route("/v21-5/dashboard", methods=["GET"])
def v215_dashboard_route():
    return v21_layout("V21.5 Auto Journal + Outcome Database", v215_dashboard_body(), "dashboard")


@app.route("/v21-5/journal", methods=["GET"])
def v215_journal_route():
    return v21_layout("V21.5 Real Trade Journal", v21_journal_body(), "journal")


@app.route("/v21-5/outcomes", methods=["GET"])
def v215_outcomes_route():
    v215_backfill_outcomes()
    rows = v215_outcome_rows(1000)[::-1]
    tr = "".join([f"<tr><td>{r['trade_id']}</td><td>{v21_html_escape(r['symbol'])}</td><td>{v21_html_escape(r['side'])}</td><td>{v21_html_escape(r['strategy'])}</td><td>{r['entry_price']}</td><td>{r['exit_price']}</td><td>{v215_badge(r['result'])}</td><td>{r['r_multiple']}R</td><td>{r.get('holding_minutes') or ''}</td></tr>" for r in rows]) or "<tr><td colspan='9'>No outcomes yet.</td></tr>"
    return v21_layout("V21.5 Closed Outcome Database", f"<div class='card'><h3>Closed Outcomes</h3><table><tr><th>Trade ID</th><th>Symbol</th><th>Side</th><th>Strategy</th><th>Entry</th><th>Exit</th><th>Result</th><th>R</th><th>Minutes</th></tr>{tr}</table></div>", "journal")


@app.route("/v21-5/strategy-db", methods=["GET"])
def v215_strategy_db_route():
    v215_recalculate_strategy_stats()
    rows = v215_strategy_stats_rows()
    tr = "".join([f"<tr><td>{v21_html_escape(r['strategy'])}</td><td>{r['trades']}</td><td>{r['wins']}</td><td>{r['losses']}</td><td>{r['win_rate_pct']}%</td><td>{r['avg_win_r']}R</td><td>{r['avg_loss_r']}R</td><td>{r['profit_factor']}</td><td>{r['expectancy_r']}R</td><td>{r['total_r']}R</td><td>{v21_html_escape(r['sample_quality'])}</td></tr>" for r in rows]) or "<tr><td colspan='11'>No strategy stats yet.</td></tr>"
    return v21_layout("V21.5 Strategy Performance Database", f"<div class='card'><h3>Persistent Strategy Performance Database</h3><table><tr><th>Strategy</th><th>Trades</th><th>Wins</th><th>Losses</th><th>Win%</th><th>Avg Win</th><th>Avg Loss</th><th>PF</th><th>Expectancy</th><th>Total R</th><th>Sample</th></tr>{tr}</table></div>", "stats")


@app.route("/v21-5/equity", methods=["GET"])
def v215_equity_route():
    return v21_layout("V21.5 Equity Curve From Real Outcomes", v21_equity_body(), "equity")


@app.route("/v21-5/journal/open/<symbol>", methods=["GET", "POST"])
def v215_open_trade_route(symbol):
    return v21_open_trade_route(symbol)


@app.route("/v21-5/journal/close/<int:trade_id>", methods=["GET", "POST"])
def v215_close_trade_route(trade_id):
    try:
        trade = v21_close_trade(trade_id, request.args.get("exit"), notes_append=request.args.get("notes", ""))
        outcome = v215_outcome_from_trade(trade, source="v21_5_close")
        return jsonify({"ok": True, "trade": trade, "outcome": outcome, "strategy_db": v215_strategy_stats_rows(), "performance": v21_performance(v21_closed_rows())})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "example": f"/v21-5/journal/close/{trade_id}?exit=225"}), 400


@app.route("/v21-5/backfill", methods=["GET", "POST"])
def v215_backfill_route():
    return jsonify(v215_backfill_outcomes())


@app.route("/v21-5/auto-journal", methods=["GET", "POST"])
def v215_auto_journal_route():
    return jsonify(v215_auto_journal_from_ranking(limit=request.args.get("limit", 5), min_grade=request.args.get("min_grade")))


@app.route("/v21-5/api/snapshot", methods=["GET"])
def v215_snapshot_route():
    return jsonify(v215_snapshot())

import os
import sqlite3
from datetime import datetime

V216_ENABLE_AUTO_JOURNAL = os.getenv("V216_ENABLE_AUTO_JOURNAL", "true").lower() == "true"
V216_DEFAULT_QTY = float(os.getenv("V216_DEFAULT_QTY", "1"))
V216_MIN_SAMPLE_WARNING = int(os.getenv("V216_MIN_SAMPLE_WARNING", "50"))


def v216_now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def v216_safe_float(x, default=None):
    try:
        if x is None or x == "":
            return default
        return float(x)
    except Exception:
        return default


def v216_safe_int(x, default=0):
    try:
        if x is None or x == "":
            return default
        return int(float(x))
    except Exception:
        return default


def v216_round(x, nd=4):
    try:
        if x is None:
            return 0.0
        return round(float(x), nd)
    except Exception:
        return 0.0


def v216_add_column_if_missing(cur, table, column, coltype):
    try:
        cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
        if cols and column not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
    except Exception:
        pass


def v216_init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS trade_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            strategy TEXT DEFAULT 'UNKNOWN',
            entry_price REAL NOT NULL,
            stop_price REAL,
            target_price REAL,
            exit_price REAL,
            qty REAL DEFAULT 1,
            status TEXT DEFAULT 'OPEN',
            result TEXT,
            r_multiple REAL,
            pnl REAL,
            source TEXT DEFAULT 'manual',
            signal_score REAL,
            probability REAL,
            notes TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS closed_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id INTEGER UNIQUE,
            closed_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            strategy TEXT DEFAULT 'UNKNOWN',
            entry_price REAL NOT NULL,
            exit_price REAL NOT NULL,
            stop_price REAL,
            target_price REAL,
            qty REAL DEFAULT 1,
            result TEXT NOT NULL,
            r_multiple REAL NOT NULL,
            pnl REAL,
            holding_minutes REAL,
            source TEXT DEFAULT 'manual',
            notes TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS strategy_performance (
            strategy TEXT PRIMARY KEY,
            trades INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            breakeven INTEGER DEFAULT 0,
            win_rate REAL DEFAULT 0,
            avg_win_r REAL DEFAULT 0,
            avg_loss_r REAL DEFAULT 0,
            profit_factor REAL DEFAULT 0,
            expectancy_r REAL DEFAULT 0,
            total_r REAL DEFAULT 0,
            max_win_r REAL DEFAULT 0,
            max_loss_r REAL DEFAULT 0,
            updated_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS equity_curve (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            trade_id INTEGER UNIQUE,
            symbol TEXT,
            strategy TEXT,
            r_multiple REAL NOT NULL,
            equity_r REAL NOT NULL,
            drawdown_r REAL NOT NULL
        )
    """)

    # Migration guard for older tables / older V21-V21.5 tables.
    # This prevents: sqlite3.OperationalError: no such column: exit_price
    for table in ["trade_journal", "journal_trades"]:
        for col, typ in [
            ("created_at", "TEXT"),
            ("updated_at", "TEXT"),
            ("symbol", "TEXT"),
            ("side", "TEXT"),
            ("strategy", "TEXT"),
            ("entry_price", "REAL"),
            ("stop_price", "REAL"),
            ("target_price", "REAL"),
            ("exit_price", "REAL"),
            ("qty", "REAL DEFAULT 1"),
            ("status", "TEXT"),
            ("result", "TEXT"),
            ("r_multiple", "REAL"),
            ("pnl", "REAL"),
            ("source", "TEXT"),
            ("signal_score", "REAL"),
            ("probability", "REAL"),
            ("notes", "TEXT"),
        ]:
            v216_add_column_if_missing(cur, table, col, typ)

    conn.commit()
    conn.close()


def v216_calc_r(side, entry, stop, exit_price):
    side = str(side or "").upper()
    entry = float(entry)
    exit_price = float(exit_price)
    stop = v216_safe_float(stop)

    if side in ("CALL", "BUY", "LONG"):
        risk = abs(entry - stop) if stop is not None and entry != stop else max(abs(entry) * 0.01, 0.01)
        return (exit_price - entry) / risk

    if side in ("PUT", "SELL", "SHORT"):
        risk = abs(stop - entry) if stop is not None and entry != stop else max(abs(entry) * 0.01, 0.01)
        return (entry - exit_price) / risk

    return 0.0


def v216_result_from_r(r):
    if r > 0:
        return "WIN"
    if r < 0:
        return "LOSS"
    return "BE"


def v216_open_trade(symbol, side, entry_price, stop_price=None, target_price=None,
                    strategy="UNKNOWN", qty=1, source="manual",
                    signal_score=None, probability=None, notes=None):
    v216_init_db()

    symbol = str(symbol or "").upper().strip()
    side = str(side or "").upper().strip()
    strategy = str(strategy or "UNKNOWN").upper().strip()
    entry_price = v216_safe_float(entry_price)
    stop_price = v216_safe_float(stop_price)
    target_price = v216_safe_float(target_price)
    qty = v216_safe_float(qty, V216_DEFAULT_QTY)

    if not symbol:
        raise ValueError("symbol is required")
    if side not in ("CALL", "PUT", "BUY", "SELL", "LONG", "SHORT"):
        raise ValueError("side must be CALL/PUT/BUY/SELL/LONG/SHORT")
    if entry_price is None or entry_price <= 0:
        raise ValueError("entry_price must be positive")

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO trade_journal
        (created_at, updated_at, symbol, side, strategy, entry_price, stop_price,
         target_price, qty, status, source, signal_score, probability, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?)
    """, (
        v216_now_text(), v216_now_text(), symbol, side, strategy,
        entry_price, stop_price, target_price, qty, source,
        signal_score, probability, notes
    ))
    trade_id = cur.lastrowid
    conn.commit()
    conn.close()
    return trade_id


def v216_close_trade(trade_id, exit_price, notes=None):
    v216_init_db()

    trade_id = v216_safe_int(trade_id, 0)
    exit_price = v216_safe_float(exit_price)

    if trade_id <= 0:
        raise ValueError("trade_id is required")
    if exit_price is None or exit_price <= 0:
        raise ValueError("exit_price must be positive")

    conn = db()
    conn.row_factory = sqlite3.Row
    trade = conn.execute("SELECT * FROM trade_journal WHERE id=?", (trade_id,)).fetchone()

    if not trade:
        conn.close()
        raise ValueError("trade not found")

    if str(trade["status"]).upper() == "CLOSED":
        conn.close()
        return {"ok": True, "message": "already closed", "trade_id": trade_id}

    entry = float(trade["entry_price"])
    stop = trade["stop_price"]
    side = trade["side"]
    qty = float(trade["qty"] or 1)

    r = v216_calc_r(side, entry, stop, exit_price)
    result = v216_result_from_r(r)

    if str(side).upper() in ("CALL", "BUY", "LONG"):
        pnl = (exit_price - entry) * qty
    else:
        pnl = (entry - exit_price) * qty

    closed_at = v216_now_text()
    holding_minutes = None
    try:
        start_dt = datetime.strptime(trade["created_at"], "%Y-%m-%d %H:%M:%S")
        end_dt = datetime.strptime(closed_at, "%Y-%m-%d %H:%M:%S")
        holding_minutes = (end_dt - start_dt).total_seconds() / 60.0
    except Exception:
        pass

    conn.execute("""
        UPDATE trade_journal
        SET updated_at=?, exit_price=?, status='CLOSED', result=?, r_multiple=?, pnl=?, notes=COALESCE(?, notes)
        WHERE id=?
    """, (closed_at, exit_price, result, r, pnl, notes, trade_id))

    conn.execute("""
        INSERT OR REPLACE INTO closed_outcomes
        (trade_id, closed_at, symbol, side, strategy, entry_price, exit_price,
         stop_price, target_price, qty, result, r_multiple, pnl, holding_minutes, source, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        trade_id, closed_at, trade["symbol"], trade["side"], trade["strategy"],
        trade["entry_price"], exit_price, trade["stop_price"], trade["target_price"],
        qty, result, r, pnl, holding_minutes, trade["source"], notes or trade["notes"]
    ))

    conn.commit()
    conn.close()

    v216_rebuild_strategy_performance()
    v216_rebuild_equity_curve()

    return {
        "ok": True,
        "trade_id": trade_id,
        "symbol": trade["symbol"],
        "result": result,
        "r_multiple": v216_round(r, 6),
        "pnl": v216_round(pnl, 4)
    }


def v216_backfill_closed_outcomes():
    v216_init_db()
    conn = db()
    conn.row_factory = sqlite3.Row

    # Only backfill from trade_journal, because this patch owns that schema.
    # Older journal_trades may have incompatible column names.
    rows = conn.execute("""
        SELECT *
        FROM trade_journal
        WHERE status='CLOSED'
          AND exit_price IS NOT NULL
          AND id NOT IN (SELECT trade_id FROM closed_outcomes WHERE trade_id IS NOT NULL)
        ORDER BY id ASC
    """).fetchall()
    conn.close()

    count = 0
    for row in rows:
        try:
            v216_close_trade(row["id"], row["exit_price"], row["notes"])
            count += 1
        except Exception as e:
            print("v21.6 backfill row error:", e)

    v216_rebuild_strategy_performance()
    v216_rebuild_equity_curve()
    return count


def v216_performance_from_rows(rows):
    trades = len(rows)
    wins = [float(r["r_multiple"]) for r in rows if float(r["r_multiple"]) > 0]
    losses = [float(r["r_multiple"]) for r in rows if float(r["r_multiple"]) < 0]
    bes = [float(r["r_multiple"]) for r in rows if float(r["r_multiple"]) == 0]

    total_win = sum(wins)
    total_loss_abs = abs(sum(losses))
    total_r = sum(float(r["r_multiple"]) for r in rows)

    win_rate = (len(wins) / trades * 100.0) if trades else 0.0
    avg_win = (sum(wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(losses) / len(losses)) if losses else 0.0
    profit_factor = (total_win / total_loss_abs) if total_loss_abs > 0 else (total_win if total_win > 0 else 0.0)
    expectancy = (total_r / trades) if trades else 0.0

    return {
        "trades": trades,
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(bes),
        "win_rate": v216_round(win_rate, 2),
        "avg_win_r": v216_round(avg_win, 4),
        "avg_loss_r": v216_round(avg_loss, 4),
        "profit_factor": v216_round(profit_factor, 4),
        "expectancy_r": v216_round(expectancy, 4),
        "total_r": v216_round(total_r, 4),
        "max_win_r": v216_round(max(wins) if wins else 0, 4),
        "max_loss_r": v216_round(min(losses) if losses else 0, 4),
        "sample_warning": "Need 50-100 closed trades before trusting statistics." if trades < V216_MIN_SAMPLE_WARNING else ""
    }


def v216_rebuild_strategy_performance():
    v216_init_db()
    conn = db()
    conn.row_factory = sqlite3.Row

    strategies = conn.execute("SELECT DISTINCT strategy FROM closed_outcomes ORDER BY strategy").fetchall()
    conn.execute("DELETE FROM strategy_performance")

    for s in strategies:
        strategy = s["strategy"] or "UNKNOWN"
        rows = conn.execute("SELECT * FROM closed_outcomes WHERE strategy=? ORDER BY id ASC", (strategy,)).fetchall()
        p = v216_performance_from_rows(rows)
        conn.execute("""
            INSERT OR REPLACE INTO strategy_performance
            (strategy, trades, wins, losses, breakeven, win_rate, avg_win_r, avg_loss_r,
             profit_factor, expectancy_r, total_r, max_win_r, max_loss_r, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            strategy, p["trades"], p["wins"], p["losses"], p["breakeven"], p["win_rate"],
            p["avg_win_r"], p["avg_loss_r"], p["profit_factor"], p["expectancy_r"],
            p["total_r"], p["max_win_r"], p["max_loss_r"], v216_now_text()
        ))

    conn.commit()
    conn.close()


def v216_rebuild_equity_curve():
    v216_init_db()
    conn = db()
    conn.row_factory = sqlite3.Row

    rows = conn.execute("SELECT * FROM closed_outcomes ORDER BY id ASC").fetchall()
    conn.execute("DELETE FROM equity_curve")

    equity = 0.0
    peak = 0.0
    for r in rows:
        rr = float(r["r_multiple"] or 0)
        equity += rr
        peak = max(peak, equity)
        dd = equity - peak
        conn.execute("""
            INSERT OR REPLACE INTO equity_curve
            (created_at, trade_id, symbol, strategy, r_multiple, equity_r, drawdown_r)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (r["closed_at"], r["trade_id"], r["symbol"], r["strategy"], rr, equity, dd))

    conn.commit()
    conn.close()


def v216_snapshot():
    v216_init_db()
    v216_backfill_closed_outcomes()

    conn = db()
    conn.row_factory = sqlite3.Row
    open_trades = conn.execute("SELECT COUNT(*) AS c FROM trade_journal WHERE status='OPEN'").fetchone()["c"]
    closed_trades = conn.execute("SELECT COUNT(*) AS c FROM closed_outcomes").fetchone()["c"]
    outcomes = conn.execute("SELECT * FROM closed_outcomes ORDER BY id DESC LIMIT 20").fetchall()
    strategies = conn.execute("SELECT * FROM strategy_performance ORDER BY expectancy_r DESC, profit_factor DESC").fetchall()
    equity = conn.execute("SELECT * FROM equity_curve ORDER BY id ASC").fetchall()
    all_rows = conn.execute("SELECT * FROM closed_outcomes ORDER BY id ASC").fetchall()
    conn.close()

    return {
        "version": "V21.6 Database Writer Fix SAFE",
        "db_path": os.getenv("DB_PATH", "signals.db"),
        "open_trades": open_trades,
        "closed_outcomes": closed_trades,
        "performance": v216_performance_from_rows(all_rows),
        "strategy_performance_db": [dict(x) for x in strategies],
        "recent_outcomes": [dict(x) for x in outcomes],
        "equity_curve": [dict(x) for x in equity[-50:]]
    }


def v216_html_page(title, body, active="dashboard"):
    nav = [
        ("Dashboard", "/v21-6"),
        ("Journal", "/v21-6/journal"),
        ("Outcomes", "/v21-6/outcomes"),
        ("Stats", "/v21-6/strategy-db"),
        ("Equity", "/v21-6/equity"),
        ("JSON", "/v21-6/api/snapshot"),
    ]
    links = "".join(
        f'<a class="nav {"on" if active == name.lower() else ""}" href="{href}">{name}</a>'
        for name, href in nav
    )
    return f"""
    <html><head><title>{title}</title>
    <style>
    body{{margin:0;background:#111827;color:#e5e7eb;font-family:Arial,sans-serif}}
    .wrap{{max-width:1180px;margin:0 auto;padding:28px}}
    .top{{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px}}
    .badge{{background:#2563eb;border-radius:12px;padding:8px 10px;font-weight:700}}
    .nav{{color:#cbd5e1;text-decoration:none;margin-left:10px;padding:8px 12px;border-radius:10px;background:#1f2937}}
    .nav.on{{background:#2563eb;color:white}}
    .card{{background:#1f2937;border:1px solid #374151;border-radius:16px;padding:18px;margin:14px 0}}
    .grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}
    .metric{{background:#243044;border:1px solid #3b4a63;border-radius:14px;padding:14px}}
    .label{{font-size:12px;color:#93a4bd;text-transform:uppercase;font-weight:700}}
    .value{{font-size:28px;font-weight:800;margin-top:6px}}
    table{{width:100%;border-collapse:collapse;margin-top:10px}}
    th,td{{border-bottom:1px solid #374151;padding:9px;text-align:left;font-size:14px}}
    th{{color:#93c5fd;text-transform:uppercase;font-size:12px}}
    pre{{white-space:pre-wrap;background:#0b1220;border-radius:12px;padding:12px;color:#d1fae5}}
    .ok{{color:#86efac;font-weight:700}}
    .warn{{color:#fde68a;font-weight:700}}
    </style></head><body><div class="wrap">
    <div class="top"><div><span class="badge">V21.6</span>
    <h1>{title}</h1><p>Safe Database Writer Fix · Journal + Outcomes + Strategy DB + Equity Curve</p></div>
    <div>{links}</div></div>
    {body}
    <p style="text-align:center;color:#94a3b8;margin-top:30px">Research cockpit only. Not investment advice.</p>
    </div></body></html>
    """


@app.route("/v21-6/status")
def v216_status():
    v216_init_db()
    return jsonify({
        "ok": True,
        "version": "V21.6 Database Writer Fix SAFE",
        "db_path": os.getenv("DB_PATH", "signals.db"),
        "routes": [
            "/v21-6",
            "/v21-6/status",
            "/v21-6/journal",
            "/v21-6/journal/open?symbol=NVDA&side=CALL&entry=212&stop=205&target=225&strategy=MOMENTUM&qty=1",
            "/v21-6/journal/close/<id>?exit=220",
            "/v21-6/backfill",
            "/v21-6/outcomes",
            "/v21-6/strategy-db",
            "/v21-6/equity",
            "/v21-6/api/snapshot",
        ]
    })


@app.route("/v21-6/journal/open")
def v216_route_open_trade():
    try:
        trade_id = v216_open_trade(
            symbol=request.args.get("symbol"),
            side=request.args.get("side", "CALL"),
            entry_price=request.args.get("entry"),
            stop_price=request.args.get("stop"),
            target_price=request.args.get("target"),
            strategy=request.args.get("strategy", "MANUAL"),
            qty=request.args.get("qty", V216_DEFAULT_QTY),
            source=request.args.get("source", "manual"),
            signal_score=request.args.get("score"),
            probability=request.args.get("prob"),
            notes=request.args.get("notes"),
        )
        return jsonify({
            "ok": True,
            "trade_id": trade_id,
            "close_url_example": f"/v21-6/journal/close/{trade_id}?exit=YOUR_EXIT_PRICE"
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/v21-6/journal/close/<int:trade_id>")
def v216_route_close_trade(trade_id):
    try:
        return jsonify(v216_close_trade(trade_id, request.args.get("exit"), request.args.get("notes")))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/v21-6/backfill")
def v216_route_backfill():
    try:
        count = v216_backfill_closed_outcomes()
        snap = v216_snapshot()
        return jsonify({
            "ok": True,
            "backfilled": count,
            "closed_outcomes": snap["closed_outcomes"],
            "performance": snap["performance"],
            "strategy_stats": snap["strategy_performance_db"]
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/v21-6/api/snapshot")
def v216_route_snapshot():
    try:
        return jsonify(v216_snapshot())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/v21-6")
@app.route("/v21-6/dashboard")
def v216_dashboard():
    snap = v216_snapshot()
    p = snap["performance"]
    best = snap["strategy_performance_db"][0]["strategy"] if snap["strategy_performance_db"] else "N/A"
    body = f"""
    <div class="grid">
      <div class="metric"><div class="label">Open Trades</div><div class="value">{snap["open_trades"]}</div></div>
      <div class="metric"><div class="label">Closed Trades</div><div class="value">{snap["closed_outcomes"]}</div></div>
      <div class="metric"><div class="label">Profit Factor</div><div class="value">{p["profit_factor"]}</div></div>
      <div class="metric"><div class="label">Expectancy</div><div class="value">{p["expectancy_r"]}R</div></div>
    </div>
    <div class="card"><h2>Best Strategy</h2><p class="ok">{best}</p><p class="warn">{p["sample_warning"]}</p></div>
    <div class="card"><h2>Quick Test</h2>
    <pre>/v21-6/journal/open?symbol=NVDA&side=CALL&entry=212&stop=205&target=225&strategy=MOMENTUM&qty=1
/v21-6/journal/close/1?exit=220
/v21-6/backfill</pre></div>
    """
    return v216_html_page("V21.6 Database Writer Dashboard", body, "dashboard")


@app.route("/v21-6/journal")
def v216_journal_page():
    v216_init_db()
    conn = db()
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM trade_journal ORDER BY id DESC LIMIT 100").fetchall()
    conn.close()

    trs = "".join(
        f"<tr><td>{r['id']}</td><td>{r['symbol']}</td><td>{r['side']}</td><td>{r['strategy']}</td>"
        f"<td>{r['entry_price']}</td><td>{r['stop_price']}</td><td>{r['target_price']}</td>"
        f"<td>{r['exit_price']}</td><td>{r['status']}</td><td>{v216_round(r['r_multiple'],4)}</td><td>{r['created_at']}</td></tr>"
        for r in rows
    ) or "<tr><td colspan='11'>No journal entries yet.</td></tr>"

    body = f"<div class='card'><h2>Real Trade Journal</h2><table><tr><th>ID</th><th>Symbol</th><th>Side</th><th>Strategy</th><th>Entry</th><th>Stop</th><th>Target</th><th>Exit</th><th>Status</th><th>R</th><th>Entry Time</th></tr>{trs}</table></div>"
    return v216_html_page("V21.6 Real Trade Journal", body, "journal")


@app.route("/v21-6/outcomes")
def v216_outcomes_page():
    snap = v216_snapshot()
    trs = "".join(
        f"<tr><td>{r['trade_id']}</td><td>{r['symbol']}</td><td>{r['side']}</td><td>{r['strategy']}</td>"
        f"<td>{r['entry_price']}</td><td>{r['exit_price']}</td><td>{r['result']}</td><td>{v216_round(r['r_multiple'],4)}</td><td>{v216_round(r['holding_minutes'],1)}</td></tr>"
        for r in snap["recent_outcomes"]
    ) or "<tr><td colspan='9'>No outcomes yet.</td></tr>"

    body = f"<div class='card'><h2>Closed Outcome Database</h2><table><tr><th>Trade ID</th><th>Symbol</th><th>Side</th><th>Strategy</th><th>Entry</th><th>Exit</th><th>Result</th><th>R</th><th>Minutes</th></tr>{trs}</table></div>"
    return v216_html_page("V21.6 Closed Outcome Database", body, "outcomes")


@app.route("/v21-6/strategy-db")
def v216_strategy_db_page():
    snap = v216_snapshot()
    trs = "".join(
        f"<tr><td>{r['strategy']}</td><td>{r['trades']}</td><td>{r['wins']}</td><td>{r['losses']}</td><td>{r['win_rate']}%</td>"
        f"<td>{r['avg_win_r']}</td><td>{r['avg_loss_r']}</td><td>{r['profit_factor']}</td><td>{r['expectancy_r']}</td><td>{r['total_r']}</td></tr>"
        for r in snap["strategy_performance_db"]
    ) or "<tr><td colspan='10'>No strategy stats yet.</td></tr>"

    body = f"<div class='card'><h2>Persistent Strategy Performance Database</h2><table><tr><th>Strategy</th><th>Trades</th><th>Wins</th><th>Losses</th><th>Win%</th><th>Avg Win</th><th>Avg Loss</th><th>PF</th><th>Expectancy</th><th>Total R</th></tr>{trs}</table></div>"
    return v216_html_page("V21.6 Strategy Performance Database", body, "stats")


@app.route("/v21-6/equity")
def v216_equity_page():
    snap = v216_snapshot()
    rows = snap["equity_curve"]

    trs = "".join(
        f"<tr><td>{r['id']}</td><td>{r['created_at']}</td><td>{r['symbol']}</td><td>{r['strategy']}</td><td>{v216_round(r['r_multiple'],4)}R</td><td>{v216_round(r['equity_r'],4)}R</td><td>{v216_round(r['drawdown_r'],4)}R</td></tr>"
        for r in rows
    ) or "<tr><td colspan='7'>No equity curve yet.</td></tr>"

    bars = ""
    if rows:
        values = [float(x["equity_r"]) for x in rows]
        mn, mx = min(values), max(values)
        span = max(mx - mn, 1)
        for v in values:
            h = 20 + int((v - mn) / span * 120)
            bars += f"<div title='{v:.2f}R' style='display:inline-block;width:10px;height:{h}px;background:#38bdf8;margin-right:4px;border-radius:4px'></div>"

    body = f"""
    <div class='card'><h2>Equity Curve In R</h2><div style='height:170px;display:flex;align-items:end'>{bars}</div></div>
    <div class='card'><h2>Equity Points</h2><table><tr><th>ID</th><th>Time</th><th>Symbol</th><th>Strategy</th><th>R</th><th>Equity</th><th>DD</th></tr>{trs}</table></div>
    """
    return v216_html_page("V21.6 Equity Curve From Closed Trades", body, "equity")


# Optional: Auto Journal from save_signal()
# This wraps your existing save_signal if it exists.
try:
    _v216_original_save_signal = save_signal

    def save_signal(symbol, asset_type, price, score, bias, signal_type, regime, probability, report):
        _v216_original_save_signal(symbol, asset_type, price, score, bias, signal_type, regime, probability, report)

        if not V216_ENABLE_AUTO_JOURNAL:
            return

        try:
            b = str(bias or "").upper()
            st = str(signal_type or "AUTO_SIGNAL").upper()
            symbol = str(symbol or "").upper()
            entry = v216_safe_float(price)
            sc = v216_safe_float(score, 0)
            prob = v216_safe_float(probability, 0)

            if not symbol or entry is None:
                return

            if b in ("BULLISH", "CALL", "BUY", "LONG"):
                side = "CALL"
                stop = entry * 0.97
                target = entry * 1.06
            elif b in ("BEARISH", "PUT", "SELL", "SHORT"):
                side = "PUT"
                stop = entry * 1.03
                target = entry * 0.94
            else:
                return

            conn = db()
            existing = conn.execute("""
                SELECT id FROM trade_journal
                WHERE symbol=? AND side=? AND strategy=? AND status='OPEN'
                ORDER BY id DESC LIMIT 1
            """, (symbol, side, st)).fetchone()
            conn.close()

            if existing:
                return

            v216_open_trade(
                symbol=symbol,
                side=side,
                entry_price=entry,
                stop_price=stop,
                target_price=target,
                strategy=st,
                qty=V216_DEFAULT_QTY,
                source="auto_signal",
                signal_score=sc,
                probability=prob,
                notes=str(report or "")[:1000],
            )
        except Exception as e:
            print("v21.6 auto journal error:", e)

except NameError:
    pass


try:
    v216_init_db()
except Exception as e:
    print("v21.6 init error:", e)

if __name__ == "__main__":
    if ENABLE_AUTO_ALERTS and ALERT_USER_IDS:
        threading.Thread(target=auto_alert_loop, daemon=True).start()

app.run(host="0.0.0.0", port=PORT)
