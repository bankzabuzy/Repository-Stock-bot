import os
import re
import hmac
import json
import time
import base64
import hashlib
import sqlite3
import threading
import html as html_lib
from datetime import datetime, timedelta, timezone
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

import requests
try:
    import yfinance as yf
except Exception as _yf_import_error:
    yf = None
    print("yfinance not loaded:", _yf_import_error)
from bs4 import BeautifulSoup
from flask import Flask, request, abort, jsonify, Response

app = Flask(__name__)

# V27.2-V27.7 Full Institutional Integration Routes
try:
    from modules.v27_full_institutional_routes import register_v27_full_institutional_routes
    register_v27_full_institutional_routes(app)
except Exception as e:
    print('V27.7 full institutional routes not loaded:', e)



# V28 Fund Validation Core routes
try:
    from modules.v28_fund_validation_routes import register_v28_fund_validation_routes
    register_v28_fund_validation_routes(app)
except Exception as e:
    print('V28 fund validation routes not loaded:', e)



# V29 Production Hardening & Governance Core routes
try:
    from modules.v29_governance_routes import register_v29_governance_routes
    register_v29_governance_routes(app)
except Exception as e:
    print('V29 governance routes not loaded:', e)



# V30 Institutional Model Validation & Paper Trading Core routes
try:
    from modules.v30_model_validation_routes import register_v30_model_validation_routes
    register_v30_model_validation_routes(app)
except Exception as e:
    print('V30 model validation routes not loaded:', e)



# V31 Alpha Research & Performance Attribution Core routes
try:
    from modules.v31_alpha_attribution_routes import register_v31_alpha_attribution_routes
    register_v31_alpha_attribution_routes(app)
except Exception as e:
    print('V31 alpha attribution routes not loaded:', e)

# V27.1 Integration Phase routes
try:
    from modules.v27_integration_routes_snippet import register_v27_integration_routes
    register_v27_integration_routes(app)
except Exception as e:
    print('V27.1 integration routes not loaded:', e)

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
US_ALLOW_PREMARKET_ALERTS = os.getenv("US_ALLOW_PREMARKET_ALERTS", "false").lower() == "true"
ENABLE_THAI_STOCK_ALERTS = os.getenv("ENABLE_THAI_STOCK_ALERTS", "false").lower() == "true"
ENABLE_US_STOCK_ALERTS = os.getenv("ENABLE_US_STOCK_ALERTS", "true").lower() == "true"
ENABLE_US_REGULAR_SESSION_ONLY = os.getenv("ENABLE_US_REGULAR_SESSION_ONLY", "true").lower() == "true"
USE_US_EXCHANGE_TIME = os.getenv("USE_US_EXCHANGE_TIME", "true").lower() == "true"
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
# V13 bugfix: keep US regular session aligned with current DST Thai time. Do not override 20:30 with 21:30.
US_SESSION_START_TH = os.getenv("US_SESSION_START_TH", "20:30")
US_SESSION_END_TH = os.getenv("US_SESSION_END_TH", "03:00")
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
PREMARKET_REMINDER_TH = os.getenv("PREMARKET_REMINDER_TH", "20:20")
ENABLE_PREMARKET_REMINDER = os.getenv("ENABLE_PREMARKET_REMINDER", "false").lower() == "true"
TOP5_DAILY_TIME_TH = os.getenv("TOP5_DAILY_TIME_TH", "20:45")
ENABLE_TOP5_DAILY = os.getenv("ENABLE_TOP5_DAILY", "true").lower() == "true"
TOP5_UNIVERSE = [
    x.strip().upper()
    for x in os.getenv("TOP5_UNIVERSE", os.getenv("WATCHLIST", "NVDA,AAPL,TSLA,QQQ,SPY,META,AMD,PLTR,AVGO,MSFT")).split(",")
    if x.strip()
]
PREMARKET_COOLDOWN_KEY = "premarket_reminder"
TOP5_COOLDOWN_KEY = "top5_daily"

DB_PATH = os.getenv("DB_PATH", "signals.db")

# Production-safe fallback values. These prevent Railway from crashing when
# API keys, network providers, or the persistent volume are temporarily unavailable.
ENABLE_YFINANCE_FALLBACK = os.getenv("ENABLE_YFINANCE_FALLBACK", "true").lower() == "true"
ENABLE_GOLDTRADERS_FETCH = os.getenv("ENABLE_GOLDTRADERS_FETCH", "true").lower() == "true"
ENABLE_THAI_OIL_FETCH = os.getenv("ENABLE_THAI_OIL_FETCH", "false").lower() == "true"

FALLBACK_MARKET_PRICES = {
    "GOLD": 2350.0,
    "XAUUSD": 2350.0,
    "GC=F": 2350.0,
    "USDTHB": 36.50,
    "NVDA": 120.0,
    "AAPL": 200.0,
    "TSLA": 180.0,
    "QQQ": 450.0,
    "SPY": 520.0,
}

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
def _usable_db_path():
    """Return a SQLite path that can be opened in production.

    If DB_PATH points to a missing/unmounted Railway volume such as
    /data/signals.db, the app falls back to a local file instead of crashing.
    """
    path = os.getenv("DB_PATH", DB_PATH or "signals.db") or "signals.db"
    directory = os.path.dirname(path)
    if directory:
        try:
            os.makedirs(directory, exist_ok=True)
        except Exception as e:
            print("DB directory unavailable, fallback to local signals.db:", e)
            return "signals.db"
    return path


def db():
    path = _usable_db_path()
    try:
        conn = sqlite3.connect(path)
    except Exception as e:
        print("DB open error, fallback to local signals.db:", e)
        conn = sqlite3.connect("signals.db")
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
        # V13 Signal Quality Layer: audit every emitted signal for future win-rate evaluation.
        try:
            if "save_signal_audit" in globals():
                save_signal_audit(symbol, asset_type, price, score, bias, signal_type, regime, probability, report)
        except Exception as audit_error:
            print("save_signal_audit error:", audit_error)
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
                timeout=8,
            )
            rate = safe_float(r.json().get("rate"))
            if rate:
                cache_set("USDTHB", rate)
                return rate
    except Exception:
        pass

    if ENABLE_YFINANCE_FALLBACK and yf is not None:
        try:
            data = yf.Ticker("USDTHB=X").history(period="5d", interval="1d")
            if not data.empty:
                rate = float(data["Close"].dropna().iloc[-1])
                cache_set("USDTHB", rate)
                return rate
        except Exception:
            pass

    return FALLBACK_MARKET_PRICES.get("USDTHB", 36.50)


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
    if not ENABLE_GOLDTRADERS_FETCH:
        return None

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
    if not ENABLE_YFINANCE_FALLBACK:
        raise RuntimeError("yfinance fallback is disabled; using safe fallback data")
    if yf is None:
        raise RuntimeError("yfinance is not installed or failed to import")
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


def fallback_market_data(asset, reason=""):
    """Last-resort market data.

    Important: do not fabricate a confident price for Thai stocks or gold.
    For unavailable Thai stock data, return a neutral/no-trade series around None-safe
    fallback only when a numeric series is required by the indicator engine.
    """
    symbol = str(asset.get("symbol") or asset.get("yf_symbol") or "").upper()
    asset_type = asset.get("asset_type")
    base = FALLBACK_MARKET_PRICES.get(symbol)
    if base is None and asset_type == "GOLD":
        # Try official Thai gold first, then XAU fallback.
        real_gold = get_goldtraders_price()
        if real_gold and real_gold.get("bar_sell"):
            base = safe_float(real_gold.get("gold_spot")) or FALLBACK_MARKET_PRICES.get("GOLD", 2350.0)
        else:
            base = FALLBACK_MARKET_PRICES.get("GOLD", 2350.0)
    if base is None and asset_type == "THAI_STOCK":
        # Avoid using the old 100/106.32 fake price as if it were a market quote.
        base = None
    if base is None:
        base = 100.0

    closes = [round(base * (1 + (i - 80) * 0.0008), 4) for i in range(160)]
    highs = [round(x * 1.006, 4) for x in closes]
    lows = [round(x * 0.994, 4) for x in closes]
    opens = [round(x * 0.999, 4) for x in closes]
    volumes = [1000000.0 for _ in closes]
    price = closes[-1]
    prev = closes[-2]
    quote = {
        "close": price,
        "previous_close": prev,
        "change": round(price - prev, 4),
        "percent_change": round(((price - prev) / prev * 100), 4) if prev else 0.0,
        "source": "SAFE_FALLBACK",
        "warning": str(reason or "market data provider unavailable")[:300],
        "is_fallback": True,
    }
    return quote, closes, highs, lows, opens, volumes


def yahoo_chart_get_quote_and_series(asset, range_="6mo", interval="1d"):
    """Direct Yahoo chart fallback without relying on yfinance internals."""
    symbol = asset.get("yf_symbol") or asset.get("symbol")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    r = requests.get(url, params={"range": range_, "interval": interval}, headers=REQUEST_HEADERS, timeout=15)
    data = r.json()
    result = (((data or {}).get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"Yahoo chart no data for {symbol}")
    q = (result.get("indicators") or {}).get("quote") or []
    q = q[0] if q else {}
    closes_raw = q.get("close") or []
    highs_raw = q.get("high") or []
    lows_raw = q.get("low") or []
    opens_raw = q.get("open") or []
    volumes_raw = q.get("volume") or []
    closes, highs, lows, opens, volumes = [], [], [], [], []
    for c,h,l,o,v in zip(closes_raw, highs_raw, lows_raw, opens_raw, volumes_raw):
        if c is None or h is None or l is None or o is None:
            continue
        closes.append(float(c)); highs.append(float(h)); lows.append(float(l)); opens.append(float(o)); volumes.append(float(v or 0))
    if not closes:
        raise RuntimeError(f"Yahoo chart empty prices for {symbol}")
    price = closes[-1]
    prev = closes[-2] if len(closes) >= 2 else None
    change = price - prev if prev is not None else None
    pct = change / prev * 100 if change is not None and prev else None
    quote = {"close": price, "previous_close": prev, "change": change, "percent_change": pct, "source": "Yahoo Chart"}
    return quote, closes, highs, lows, opens, volumes


def get_market_data(asset):
    key = f"MD:{asset['asset_type']}:{asset['symbol']}"
    cached = cache_get(key)
    if cached:
        return cached

    try:
        if asset["asset_type"] == "THAI_STOCK":
            # Thai stocks must use SET/Yahoo .BK data, never US/TwelveData fallback.
            try:
                result = yf_get_quote_and_series(asset)
                result[0]["source"] = result[0].get("source") or "Yahoo Finance .BK"
            except Exception as e1:
                try:
                    result = yahoo_chart_get_quote_and_series(asset)
                except Exception as e2:
                    result = fallback_market_data(asset, f"Thai stock data unavailable: {e1} | {e2}")

        elif asset["asset_type"] == "US_STOCK":
            if ENABLE_MULTI_API_FALLBACK:
                result = multi_api_get_us_market_data(asset)
            else:
                quote = td_get_quote(asset)
                closes, highs, lows, opens, volumes = td_get_series(asset)
                result = (quote, closes, highs, lows, opens, volumes)

        elif asset["asset_type"] == "GOLD":
            # Keep XAU/USD technical analysis, but Thai gold report/dashboard will use GoldTraders.
            try:
                quote = td_get_quote(asset)
                closes, highs, lows, opens, volumes = td_get_series(asset)
                result = (quote, closes, highs, lows, opens, volumes) if closes else yf_get_quote_and_series(asset)
            except Exception as e:
                print("Gold XAU provider fallback:", e)
                try:
                    result = yf_get_quote_and_series(asset)
                    result[0]["source"] = result[0].get("source") or "Yahoo Finance GC=F"
                except Exception as yf_error:
                    result = fallback_market_data(asset, yf_error)

        else:
            result = yf_get_quote_and_series(asset)
    except Exception as e:
        print("market data fallback:", asset, e)
        result = fallback_market_data(asset, e)

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
    quote = quote or {}
    price = safe_float(quote.get("close"))
    previous_close = safe_float(quote.get("previous_close"))
    change = safe_float(quote.get("change"))
    percent_change = safe_float(quote.get("percent_change"))
    provider_is_fallback = bool(quote.get("is_fallback") or quote.get("source") == "SAFE_FALLBACK")

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

    if provider_is_fallback:
        # Do not output BUY/SELL confidence from fake/fallback data.
        score = 50
        probability = 40
        bias = "NEUTRAL / ข้อมูลตลาดจริงไม่พอ"
        reasons = ["ข้อมูลราคาจริงจากผู้ให้บริการไม่พร้อม จึงไม่ออกสัญญาณซื้อขาย"]

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

if result["dividend_yield"] is not None:
    if result["dividend_yield"] <= 1:
        result["dividend_yield"] = result["dividend_yield"] * 100

    if result["dividend_yield"] > 20 or result["dividend_yield"] < 0:
        result["dividend_yield"] = None
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
    # Default safe mode avoids long external oil-site timeouts on Railway.
    if not ENABLE_THAI_OIL_FETCH:
        return {
            "source": "SAFE_FALLBACK_PT_STATION",
            "updated_at": now_text(),
            "raw_url": None,
            "prices": {
                "today": {
                    "ดีเซล": 32.94,
                    "ดีเซล B20": 32.94,
                    "แก๊สโซฮอล์ 95": 39.35,
                    "แก๊สโซฮอล์ 91": 38.98,
                    "แก๊สโซฮอล์ E20": 37.14,
                    "เบนซิน 95": 47.04,
                },
                "tomorrow": {},
            },
            "has_tomorrow": False,
            "is_estimate": True,
            "note": "Set ENABLE_THAI_OIL_FETCH=true to fetch live oil prices.",
        }

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
    try:
        asset = normalize_asset("ทองคำ")
        quote, closes, highs, lows, opens, volumes = get_market_data(asset)
        analysis = analyze_signal(asset, quote, closes, highs, lows, opens, volumes)
        usd_thb = get_usd_thb_rate()
        return jsonify({
            "ok": True,
            "xauusd": analysis.get("price"),
            "usd_thb": usd_thb,
            "thai_gold": get_thai_gold_price_or_estimate(analysis.get("price"), usd_thb),
            "provider": quote.get("source"),
            "warning": quote.get("warning"),
            "time_th": now_text(),
        })
    except Exception as e:
        usd_thb = 36.50
        xauusd = FALLBACK_MARKET_PRICES["GOLD"]
        return jsonify({
            "ok": False,
            "error": str(e),
            "xauusd": xauusd,
            "usd_thb": usd_thb,
            "thai_gold": get_thai_gold_price_or_estimate(xauusd, usd_thb),
            "provider": "SAFE_FALLBACK",
            "time_th": now_text(),
        }), 200


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
    rows = conn.execute("SELECT * FROM signals ORDER BY id DESC LIMIT 80").fetchall()
    conn.close()

    def cell(v):
        return html_lib.escape("" if v is None else str(v))

    html_rows = "".join(
        f"<tr><td>{cell(r['created_at'])}</td><td>{cell(r['symbol'])}</td><td>{cell(r['asset_type'])}</td>"
        f"<td>{cell(fmt_num(r['price']))}</td><td>{cell(r['score'])}</td><td>{cell(str(r['probability']) + '%')}</td>"
        f"<td>{cell(r['signal_type'])}</td><td>{cell(r['regime'])}</td><td>{cell(r['bias'])}</td></tr>"
        for r in rows
    )
    title = "AI Market LINE Bot V31.3 Production Dashboard"
    return Response(f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body{{font-family:Arial, sans-serif;padding:18px;background:#f7f7f7;color:#111}}
h1{{font-size:24px;line-height:1.25;margin:0 0 12px}}
.note{{font-size:13px;color:#555;margin-bottom:14px}}
.wrap{{overflow-x:auto;background:#fff;border:1px solid #ddd}}
table{{border-collapse:collapse;width:100%;min-width:880px;background:#fff}}
td,th{{border:1px solid #ddd;padding:7px;font-size:13px;vertical-align:top}}
th{{background:#111;color:#fff;position:sticky;top:0}}
tr:nth-child(even){{background:#fafafa}}
.badge{{display:inline-block;padding:2px 6px;border-radius:4px;background:#eee}}
</style></head><body>
<h1>{title}</h1>
<div class="note">Time TH: {now_text()} | Rows: {len(rows)} | Gold uses Gold Traders Association when available.</div>
<div class="wrap"><table><thead><tr><th>Time</th><th>Symbol</th><th>Asset</th><th>Price</th><th>Score</th><th>Prob</th><th>Signal</th><th>Regime</th><th>Bias</th></tr></thead><tbody>{html_rows}</tbody></table></div>
</body></html>""", mimetype="text/html")



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


def asset_type_alert_enabled(asset_type):
    """Global asset enable/disable switch for auto alerts.

    Defaults: Thai stock auto alerts OFF, US stock auto alerts ON.
    Manual LINE commands still work unless blocked elsewhere.
    """
    if asset_type == "THAI_STOCK":
        return bool(globals().get("ENABLE_THAI_STOCK_ALERTS", False))
    if asset_type == "US_STOCK":
        return bool(globals().get("ENABLE_US_STOCK_ALERTS", True))
    return True


def build_v8_scan_watchlist():
    if ENABLE_SEPARATE_WATCHLISTS:
        base = []
        # Priority order
        base.extend(TIER_A_WATCHLIST)
        base.extend(TIER_B_WATCHLIST)
        base.extend(TIER_C_WATCHLIST)
        base.extend(GOLD_WATCHLIST)
        if ENABLE_US_STOCK_ALERTS:
            base.extend(US_WATCHLIST)
        if ENABLE_THAI_STOCK_ALERTS:
            base.extend(TH_WATCHLIST)
        if ENABLE_EXPANDED_SECTOR_WATCHLIST:
            if ENABLE_US_STOCK_ALERTS:
                base.extend(EXPANDED_US_WATCHLIST)
            if ENABLE_THAI_STOCK_ALERTS:
                base.extend(EXPANDED_TH_WATCHLIST)
        if ENABLE_MARKET_LEADER_WATCHLIST:
            if ENABLE_US_STOCK_ALERTS:
                base.extend(MARKET_LEADER_US_WATCHLIST)
            if ENABLE_THAI_STOCK_ALERTS:
                base.extend(MARKET_LEADER_TH_WATCHLIST)
        base = [resolve_delisted_symbol(x).replace(".BK", "").replace(".SET", "") for x in base]
        return dedupe_keep_order(base)

    # Backward compatible mode from old WATCHLIST, but with safer classification.
    valid = []
    for s in WATCHLIST:
        asset_class = classify_watchlist_symbol(s)
        if asset_class and asset_type_alert_enabled(asset_class):
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
        "enable_thai_stock_alerts": ENABLE_THAI_STOCK_ALERTS,
        "enable_us_stock_alerts": ENABLE_US_STOCK_ALERTS,
        "us_regular_session_only": ENABLE_US_REGULAR_SESSION_ONLY,
        "use_us_exchange_time": USE_US_EXCHANGE_TIME,
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
    atype = asset.get("asset_type")
    if not asset_type_alert_enabled(atype):
        return False
    if atype == "THAI_STOCK":
        return bool(globals().get("ENABLE_THAI_STOCK_ALERTS", False)) and is_th_market_open_now()
    if atype == "US_STOCK":
        if not globals().get("ENABLE_US_SESSION_ONLY", False):
            return True
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
    if asset.get("asset_type") != "US_STOCK":
        return ""

    price = analysis.get("price")
    if not price:
        return ""

    score = int(analysis.get("score", 50))
    atr = analysis.get("atr") or price * 0.015
    symbol = asset.get("symbol")

    if score <= STRONG_PUT_SCORE:
        direction = "PUT"
    elif score >= STRONG_CALL_SCORE:
        direction = "CALL"
    else:
        direction = "CALL" if score >= 50 else "PUT"

    if direction == "CALL":
        strike = round_strike(price + atr * 0.8)
        side_word = "Suggested Call"
        suffix = "C"
    else:
        strike = round_strike(price - atr * 0.8)
        side_word = "Suggested Put"
        suffix = "P"

    risk = "Medium"
    reward = "High" if abs(score - 50) >= 35 else "Medium"

    return f"""🧩 Options Hybrid
{side_word}

{symbol} {fmt_num(strike, 0)}{suffix}
Exp: {next_friday_text()}

Risk: {risk}
Reward: {reward}

หมายเหตุ: เป็น Options Hybrid จากราคา/ATR/AI Score ไม่ใช่ option chain จริง"""


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
    confidence = adjusted_confidence(analysis, side) if "adjusted_confidence" in globals() else calculate_signal_confidence(analysis)
    trend = trend_strength_score(analysis) if "trend_strength_score" in globals() else 5
    rvol = safe_float(analysis.get("rvol"), 1.0) or 1.0
    regime = str(analysis.get("regime", "")).upper()

    risk_points = 0
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

    tf4h, ok4h = timeframe_4h_confirm(asset, analysis, side)
    if ok4h:
        risk_points += 1
    else:
        risk_points -= 1

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

    return f"""⚖️ Dynamic Position Size
Risk Level: {level}
Suggested Size: {percent}
Action: {size}"""


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
    """US equity alert window.

    Preferred mode uses New York exchange time, so Thai overnight sessions and
    daylight saving time are handled correctly. Fallback uses configured Thai
    HH:MM windows for environments without zoneinfo.
    """
    if not ENABLE_US_STOCK_ALERTS:
        return False

    if USE_US_EXCHANGE_TIME and ZoneInfo is not None:
        now_et = datetime.now(ZoneInfo("America/New_York"))
        if now_et.weekday() >= 5:
            return False
        now_m = now_et.hour * 60 + now_et.minute
        regular_start = 9 * 60 + 30
        regular_end = 16 * 60
        premarket_start = 4 * 60
        if regular_start <= now_m <= regular_end:
            return True
        if (not ENABLE_US_REGULAR_SESSION_ONLY) and US_ALLOW_PREMARKET_ALERTS and premarket_start <= now_m < regular_start:
            return True
        return False

    # Legacy Thai-time fallback. Use this only if USE_US_EXCHANGE_TIME=false.
    if not is_weekday_th():
        return False
    regular_or_after = time_in_range_th(US_SESSION_START_TH, US_SESSION_END_TH)
    premarket = False
    try:
        premarket = (not ENABLE_US_REGULAR_SESSION_ONLY) and US_ALLOW_PREMARKET_ALERTS and time_in_range_th(US_PREMARKET_START_TH, US_SESSION_START_TH)
    except Exception:
        premarket = False
    return regular_or_after or premarket


def asset_market_open_for_alert(asset):
    if not ENABLE_MARKET_HOURS_GUARD:
        return True, "Market hours guard disabled"

    atype = asset.get("asset_type")
    if atype == "THAI_STOCK":
        if not ENABLE_THAI_STOCK_ALERTS:
            return False, "Thai stock alerts disabled"
        return is_th_market_open_now(), "Thai market closed"

    if atype == "US_STOCK":
        if not ENABLE_US_STOCK_ALERTS:
            return False, "US stock alerts disabled"
        return is_us_market_open_now_th(), "US market closed or outside regular session"

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
        "thai_stock_alerts_enabled": ENABLE_THAI_STOCK_ALERTS,
        "us_stock_alerts_enabled": ENABLE_US_STOCK_ALERTS,
        "us_regular_session_only": ENABLE_US_REGULAR_SESSION_ONLY,
        "use_us_exchange_time": USE_US_EXCHANGE_TIME,
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
                        try:
                            from modules.v28_fund_validation_core import audit_signal as v28_audit_signal
                            if sig != "NONE":
                                v28_audit_signal(
                                    symbol=asset.get("symbol", symbol),
                                    asset_type=asset.get("asset_type"),
                                    sig=sig,
                                    analysis=analysis,
                                    decision="PASS" if ok_final else "FAIL",
                                    reason=reason_final,
                                    portfolio_gate=analysis.get("v28_portfolio_gate") if isinstance(analysis, dict) else None,
                                    market_open=asset_market_open_for_alert(asset)[0],
                                )
                        except Exception as e:
                            print("V28 audit warning:", e)

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
                                try:
                                    from modules.v28_fund_validation_core import audit_signal as v28_audit_signal
                                    v28_audit_signal(
                                        symbol=asset.get("symbol", symbol),
                                        asset_type=asset.get("asset_type"),
                                        sig=sig,
                                        analysis=analysis,
                                        decision="SENT",
                                        reason="LINE_SENT",
                                        portfolio_gate=analysis.get("v28_portfolio_gate") if isinstance(analysis, dict) else None,
                                        market_open=asset_market_open_for_alert(asset)[0],
                                        message=message,
                                    )
                                except Exception as e:
                                    print("V28 sent audit warning:", e)

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
# PRODUCTION FIX: AUTO SCAN + SIGNAL SEED + GOLDTRADERS DEFAULT
# ============================================================
# This block is intentionally independent from LINE alerts.
# Railway/Gunicorn imports this file as `main:app`, so code inside
# if __name__ == "__main__" is NOT executed in production.  The old
# version therefore stayed online but never generated rows in `signals`.
# This patch starts a safe background scanner on import and also exposes
# manual routes for immediate testing.

AUTO_SIGNAL_SCAN_ENABLED = os.getenv("AUTO_SIGNAL_SCAN_ENABLED", "true").lower() == "true"
AUTO_SIGNAL_SCAN_INTERVAL_SECONDS = int(os.getenv("AUTO_SIGNAL_SCAN_INTERVAL_SECONDS", "900"))
AUTO_SIGNAL_SCAN_LIMIT = int(os.getenv("AUTO_SIGNAL_SCAN_LIMIT", "8"))
AUTO_SIGNAL_SCAN_ON_STARTUP = os.getenv("AUTO_SIGNAL_SCAN_ON_STARTUP", "true").lower() == "true"
AUTO_SIGNAL_SCAN_SYMBOLS = env_list(
    "AUTO_SIGNAL_SCAN_SYMBOLS",
    os.getenv("WATCHLIST", "GOLD,NVDA,AAPL,TSLA,QQQ,SPY,AMD,META")
)
_STARTUP_WORKERS_STARTED = False


def _production_signal_type(score):
    try:
        score = int(score or 50)
    except Exception:
        score = 50
    if score >= AUTO_ALERT_MIN_SCORE:
        return "BUY"
    if score <= AUTO_ALERT_MAX_SCORE:
        return "SELL"
    if score >= 60:
        return "WATCH_BUY"
    if score <= 40:
        return "WATCH_SELL"
    return "NEUTRAL"


def _production_build_scan_report(symbol, asset, analysis, quote=None):
    quote = quote or {}
    lines = [
        f"AUTO SCAN: {symbol}",
        f"เวลา: {now_text()}",
        f"ประเภท: {asset.get('asset_type')}",
        f"ราคา: {fmt_num(analysis.get('price'))}",
        f"Score: {analysis.get('score')}",
        f"Probability: {analysis.get('probability')}%",
        f"Signal: {_production_signal_type(analysis.get('score'))}",
        f"Regime: {analysis.get('regime')}",
        f"Bias: {analysis.get('bias')}",
    ]
    if asset.get("asset_type") == "GOLD":
        try:
            usdthb = get_usd_thb_rate()
            thai_gold = get_thai_gold_price_or_estimate(analysis.get("price"), usdthb)
            lines += [
                "",
                "ราคาทองไทยอ้างอิงสมาคมค้าทองคำ:",
                f"ทองแท่งรับซื้อ: {fmt_num(thai_gold.get('bar_buy'), 0)} บาท",
                f"ทองแท่งขายออก: {fmt_num(thai_gold.get('bar_sell'), 0)} บาท",
                f"ทองรูปพรรณขายออก: {fmt_num(thai_gold.get('ornament_sell'), 0)} บาท",
                f"แหล่งข้อมูล: {thai_gold.get('source')}",
                f"อัปเดต: {thai_gold.get('updated_at')}",
            ]
        except Exception as e:
            lines.append(f"Thai gold block error: {e}")
    reasons = analysis.get("reasons") or []
    if reasons:
        lines += ["", "เหตุผล:"] + [f"- {r}" for r in reasons[:8]]
    return "\n".join(lines)


def production_scan_once(symbols=None, save_all=True):
    """Run one safe scan and save rows to signals.

    This is designed for Railway production: every symbol is isolated so
    one provider/network failure cannot crash the whole worker.
    """
    init_db()
    symbols = symbols or AUTO_SIGNAL_SCAN_SYMBOLS or WATCHLIST
    symbols = [str(x).strip().upper() for x in symbols if str(x).strip()]
    results = []
    print(f"AUTO_SCAN start count={len(symbols[:AUTO_SIGNAL_SCAN_LIMIT])} symbols={symbols[:AUTO_SIGNAL_SCAN_LIMIT]}")
    for symbol in symbols[:AUTO_SIGNAL_SCAN_LIMIT]:
        try:
            if v8_skip_symbol(symbol):
                results.append({"symbol": symbol, "ok": False, "skipped": True, "reason": "v8_skip_symbol"})
                continue
            asset = normalize_asset(symbol)
            quote, closes, highs, lows, opens, volumes = get_market_data(asset)
            analysis = analyze_signal(asset, quote, closes, highs, lows, opens, volumes)

            save_symbol = asset.get("symbol", symbol)
            save_asset_type = asset.get("asset_type")
            save_price = analysis.get("price")
            save_provider = quote.get("source") if isinstance(quote, dict) else None

            if asset.get("asset_type") == "GOLD":
                try:
                    usdthb = get_usd_thb_rate()
                    thai_gold = get_thai_gold_price_or_estimate(analysis.get("price"), usdthb)
                    if thai_gold and thai_gold.get("bar_sell"):
                        save_symbol = "THAI_GOLD"
                        save_asset_type = "THAI_GOLD"
                        save_price = thai_gold.get("bar_sell")
                        save_provider = thai_gold.get("source")
                except Exception as gold_err:
                    print("AUTO_SCAN thai gold save error:", gold_err)

            sig = _production_signal_type(analysis.get("score"))
            report = _production_build_scan_report(symbol, asset, analysis, quote)
            if save_all or sig not in {"NEUTRAL"}:
                save_signal(
                    save_symbol,
                    save_asset_type,
                    save_price,
                    analysis.get("score"),
                    analysis.get("bias"),
                    sig,
                    analysis.get("regime"),
                    analysis.get("probability"),
                    report,
                )
            results.append({
                "symbol": save_symbol,
                "asset_type": save_asset_type,
                "ok": True,
                "price": save_price,
                "score": analysis.get("score"),
                "signal": sig,
                "probability": analysis.get("probability"),
                "provider": save_provider,
            })
            print(f"AUTO_SCAN saved symbol={symbol} signal={sig} score={analysis.get('score')}")
        except Exception as e:
            print(f"AUTO_SCAN error symbol={symbol}: {e}")
            results.append({"symbol": symbol, "ok": False, "error": str(e)})
    return results


@app.route("/status", methods=["GET"])
def production_status_alias():
    try:
        conn = db()
        row = conn.execute("SELECT COUNT(*) AS c FROM signals").fetchone()
        count = int(row["c"] if row else 0)
        conn.close()
    except Exception as e:
        count = None
        print("status count error:", e)
    return jsonify({
        "ok": True,
        "service": "Repository-Stock-bot",
        "time_th": now_text(),
        "signals_count": count,
        "auto_signal_scan_enabled": AUTO_SIGNAL_SCAN_ENABLED,
        "auto_signal_scan_interval_seconds": AUTO_SIGNAL_SCAN_INTERVAL_SECONDS,
        "auto_signal_scan_symbols": AUTO_SIGNAL_SCAN_SYMBOLS,
        "goldtraders_fetch_enabled": ENABLE_GOLDTRADERS_FETCH,
        "routes": ["/health", "/status", "/dashboard", "/api/signals", "/scan-now", "/gold-test"],
    })


@app.route("/scan-now", methods=["GET", "POST"])
def production_scan_now_route():
    if not require_admin():
        return jsonify({"error": "unauthorized"}), 401
    raw_symbols = request.args.get("symbols", "").strip()
    if raw_symbols:
        symbols = [x.strip().upper() for x in raw_symbols.split(",") if x.strip()]
    else:
        symbols = AUTO_SIGNAL_SCAN_SYMBOLS
    results = production_scan_once(symbols=symbols, save_all=True)
    return jsonify({"ok": True, "time_th": now_text(), "saved_or_checked": len(results), "results": results})


@app.route("/seed-signal", methods=["GET", "POST"])
def production_seed_signal_route():
    if not require_admin():
        return jsonify({"error": "unauthorized"}), 401
    results = production_scan_once(symbols=["GOLD", "NVDA", "AAPL", "TSLA", "QQQ"], save_all=True)
    return jsonify({"ok": True, "message": "seed scan completed", "results": results})


def _production_scan_loop():
    if AUTO_SIGNAL_SCAN_ON_STARTUP:
        try:
            time.sleep(5)
            production_scan_once(save_all=True)
        except Exception as e:
            print("AUTO_SCAN startup error:", e)
    while True:
        try:
            time.sleep(max(60, AUTO_SIGNAL_SCAN_INTERVAL_SECONDS))
            production_scan_once(save_all=True)
        except Exception as e:
            print("AUTO_SCAN loop error:", e)
            time.sleep(60)


def start_production_workers_once():
    global _STARTUP_WORKERS_STARTED
    if _STARTUP_WORKERS_STARTED:
        return
    _STARTUP_WORKERS_STARTED = True
    try:
        init_db()
    except Exception as e:
        print("init_db startup warning:", e)
    if AUTO_SIGNAL_SCAN_ENABLED:
        threading.Thread(target=_production_scan_loop, daemon=True, name="auto-signal-scan").start()
        print("AUTO_SCAN worker started")
    # Optional LINE alert loop remains separate.  It only starts when both
    # ENABLE_AUTO_ALERTS=true and ALERT_USER_IDS are configured.
    if ENABLE_AUTO_ALERTS and ALERT_USER_IDS:
        threading.Thread(target=auto_alert_loop, daemon=True, name="line-auto-alert-loop").start()
        print("LINE auto alert worker started")


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
# V13 SIGNAL QUALITY LAYER - FREE 100%
# Purpose: convert the bot from a scanner into a measurable research engine.
# Adds: signal audit, historical win-rate, false signal detector, adaptive scoring,
# multi-timeframe consensus, relative strength ranking, strategy leaderboard, dashboard.
# ============================================================
V13_ENABLED = os.getenv("V13_ENABLED", "true").lower() == "true"
V13_SIGNAL_HORIZONS = [int(x) for x in os.getenv("V13_SIGNAL_HORIZONS", "1,3,5,10").split(",") if str(x).strip().isdigit()]
V13_DEFAULT_UNIVERSE = env_list("V13_UNIVERSE", "NVDA,AAPL,TSLA,AMD,MSFT,META,GOOGL,AMZN,QQQ,SPY,PLTR,AVGO,SMCI,MU,ARM,COIN,MSTR,RKLB,AAOI,IREN,CRWD,SNOW,NET,DDOG,HOOD")
V13_RS_BENCHMARK = os.getenv("V13_RS_BENCHMARK", "QQQ")
V13_MIN_CLOSED_FOR_STATS = int(os.getenv("V13_MIN_CLOSED_FOR_STATS", "20"))


def v13_init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS v13_signal_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at_utc TEXT NOT NULL,
            created_at_th TEXT NOT NULL,
            symbol TEXT NOT NULL,
            asset_type TEXT,
            side TEXT,
            strategy TEXT,
            entry_price REAL,
            score INTEGER,
            adaptive_score INTEGER,
            probability INTEGER,
            bias TEXT,
            regime TEXT,
            breadth_regime TEXT,
            mtf_consensus TEXT,
            rs_score REAL,
            quality_score INTEGER,
            false_risk_score INTEGER,
            explanation_json TEXT,
            result_json TEXT,
            status TEXT DEFAULT 'OPEN',
            evaluated_at_utc TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_v13_signal_symbol ON v13_signal_audit(symbol)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_v13_signal_created ON v13_signal_audit(created_at_utc)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_v13_signal_side ON v13_signal_audit(side)")
    conn.commit()
    conn.close()


def v13_side_from_signal(signal_type, score=None, bias=None):
    text = f"{signal_type or ''} {bias or ''}".upper()
    if "CALL" in text or "BUY" in text or "BULL" in text:
        return "CALL"
    if "PUT" in text or "SELL" in text or "BEAR" in text:
        return "PUT"
    try:
        sc = int(score)
        if sc >= 75:
            return "CALL"
        if sc <= 35:
            return "PUT"
    except Exception:
        pass
    return "WAIT"


def v13_detect_strategy(report, side, score=None):
    text = str(report or "").upper()
    if "VWAP" in text:
        return "VWAP_RECLAIM" if side == "CALL" else "VWAP_REJECT"
    if "PULLBACK" in text or "ย่อ" in text:
        return "PULLBACK"
    if "BREAKOUT" in text or "เบรก" in text:
        return "BREAKOUT"
    if "OPTIONS" in text or "OPTION" in text:
        return "OPTIONS_HYBRID"
    if score is not None and score >= 88:
        return "HIGH_MOMENTUM"
    if score is not None and score <= 15:
        return "HIGH_BEARISH_MOMENTUM"
    return "CORE_SIGNAL"


def v13_safe_breadth_summary():
    try:
        if "v10_true_market_breadth" in globals():
            b = v10_true_market_breadth()
            return b.get("breadth_regime") or b.get("regime") or "UNKNOWN"
    except Exception:
        pass
    try:
        if "v121_market_internals" in globals():
            i = v121_market_internals()
            return i.get("internals_regime") or "UNKNOWN"
    except Exception:
        pass
    return "UNKNOWN"


def v13_relative_strength_score(symbol, benchmark=None, period="6mo"):
    benchmark = benchmark or V13_RS_BENCHMARK
    sym = resolve_delisted_symbol(symbol).upper().replace(".BK", "").replace(".SET", "")
    try:
        s1 = v12_yf_symbol(sym) if "v12_yf_symbol" in globals() else normalize_asset(sym)["yf_symbol"]
        s2 = v12_yf_symbol(benchmark) if "v12_yf_symbol" in globals() else benchmark
        data = yf.download([s1, s2], period=period, interval="1d", progress=False, auto_adjust=True, threads=False)
        if data is None or data.empty:
            return None
        close = data["Close"] if "Close" in data else data
        c1 = close[s1].dropna() if s1 in close else close.iloc[:, 0].dropna()
        c2 = close[s2].dropna() if s2 in close else close.iloc[:, -1].dropna()
        if len(c1) < 30 or len(c2) < 30:
            return None
        r1_20 = c1.iloc[-1] / c1.iloc[-20] - 1
        r2_20 = c2.iloc[-1] / c2.iloc[-20] - 1
        r1_60 = c1.iloc[-1] / c1.iloc[-60] - 1 if len(c1) >= 60 else r1_20
        r2_60 = c2.iloc[-1] / c2.iloc[-60] - 1 if len(c2) >= 60 else r2_20
        raw = ((r1_20 - r2_20) * 0.6 + (r1_60 - r2_60) * 0.4) * 100
        return round(max(0, min(100, 50 + raw * 5)), 2)
    except Exception:
        return None


def v13_mtf_consensus(symbol):
    try:
        asset = normalize_asset(symbol)
        quote, closes, highs, lows, opens, volumes = get_market_data(asset)
        analysis = analyze_signal(asset, quote, closes, highs, lows, opens, volumes)
        alignment = analysis.get("alignment") or "N/A"
        states = analysis.get("mtf_states") or []
        bulls = sum(1 for _, s in states if str(s).upper() == "BULLISH")
        bears = sum(1 for _, s in states if str(s).upper() == "BEARISH")
        total = len(states)
        pct = round(max(bulls, bears) / total * 100, 2) if total else 0
        direction = "BULLISH" if bulls > bears else "BEARISH" if bears > bulls else "MIXED"
        return {"alignment": alignment, "states": states, "direction": direction, "consensus_pct": pct}
    except Exception as e:
        return {"alignment": "N/A", "states": [], "direction": "UNKNOWN", "consensus_pct": 0, "error": str(e)[:120]}


def v13_adaptive_score(symbol, base_score, side, regime=None, breadth=None, rs_score=None, mtf=None):
    try:
        score = int(base_score or 50)
    except Exception:
        score = 50
    notes = []
    reg = str(regime or "").upper()
    br = str(breadth or "").upper()
    direction = str((mtf or {}).get("direction", "")).upper() if isinstance(mtf, dict) else ""
    consensus = float((mtf or {}).get("consensus_pct", 0) or 0) if isinstance(mtf, dict) else 0

    if side == "CALL":
        if "RISK_ON" in reg or "UPTREND" in reg:
            score += 5; notes.append("Regime supports CALL")
        if "RISK_OFF" in reg or "DOWNTREND" in reg:
            score -= 8; notes.append("Regime fights CALL")
        if "BEAR" in br:
            score -= 6; notes.append("Breadth weak for CALL")
        if direction == "BULLISH" and consensus >= 60:
            score += 5; notes.append("MTF confirms CALL")
        if direction == "BEARISH" and consensus >= 60:
            score -= 7; notes.append("MTF rejects CALL")
        if rs_score is not None:
            if rs_score >= 65: score += 5; notes.append("Relative strength positive")
            elif rs_score <= 40: score -= 5; notes.append("Relative strength weak")
    elif side == "PUT":
        if "RISK_OFF" in reg or "DOWNTREND" in reg:
            score = 100 - max(0, 100 - score - 5); notes.append("Regime supports PUT")
        if "RISK_ON" in reg or "UPTREND" in reg:
            score += 6; notes.append("Risk-on market reduces PUT quality")
        if direction == "BEARISH" and consensus >= 60:
            score -= 5; notes.append("MTF confirms PUT")
        if direction == "BULLISH" and consensus >= 60:
            score += 7; notes.append("MTF rejects PUT")
        if rs_score is not None and rs_score >= 65:
            score += 5; notes.append("Strong RS makes PUT riskier")
    return {"adaptive_score": int(max(0, min(100, score))), "notes": notes}


def v13_false_signal_risk(side, regime=None, breadth=None, mtf=None, rs_score=None):
    risk = 20
    notes = []
    reg = str(regime or "").upper()
    br = str(breadth or "").upper()
    direction = str((mtf or {}).get("direction", "")).upper() if isinstance(mtf, dict) else ""
    consensus = float((mtf or {}).get("consensus_pct", 0) or 0) if isinstance(mtf, dict) else 0
    if side == "CALL":
        if "BEAR" in br or "RISK_OFF" in reg:
            risk += 25; notes.append("CALL against weak breadth/regime")
        if direction == "BEARISH" and consensus >= 60:
            risk += 25; notes.append("CALL against MTF bearish consensus")
        if rs_score is not None and rs_score < 40:
            risk += 15; notes.append("CALL with weak relative strength")
    elif side == "PUT":
        if "BULL" in br or "RISK_ON" in reg:
            risk += 20; notes.append("PUT against risk-on/bullish breadth")
        if direction == "BULLISH" and consensus >= 60:
            risk += 25; notes.append("PUT against MTF bullish consensus")
        if rs_score is not None and rs_score > 65:
            risk += 15; notes.append("PUT against strong relative strength")
    else:
        risk += 15; notes.append("WAIT/unclear side")
    return {"false_risk_score": int(max(0, min(100, risk))), "notes": notes}


def v13_signal_quality_score(adaptive_score, false_risk, side):
    if side == "CALL":
        base = adaptive_score
    elif side == "PUT":
        base = 100 - adaptive_score
    else:
        base = 40
    return int(max(0, min(100, base * 0.75 + (100 - false_risk) * 0.25)))


def save_signal_audit(symbol, asset_type, price, score, bias, signal_type, regime, probability, report):
    if not V13_ENABLED:
        return False
    side = v13_side_from_signal(signal_type, score, bias)
    if side == "WAIT":
        return False
    sym = resolve_delisted_symbol(symbol).upper().replace(".BK", "").replace(".SET", "")
    mtf = v13_mtf_consensus(sym)
    rs = v13_relative_strength_score(sym) if asset_type == "US_STOCK" else None
    breadth = v13_safe_breadth_summary() if asset_type == "US_STOCK" else "N/A"
    adaptive = v13_adaptive_score(sym, score, side, regime, breadth, rs, mtf)
    false_risk = v13_false_signal_risk(side, regime, breadth, mtf, rs)
    quality = v13_signal_quality_score(adaptive["adaptive_score"], false_risk["false_risk_score"], side)
    strategy = v13_detect_strategy(report, side, score)
    explanation = {
        "signal_type": signal_type,
        "adaptive_notes": adaptive["notes"],
        "false_risk_notes": false_risk["notes"],
        "report_excerpt": str(report or "")[:1000]
    }
    conn = db()
    conn.execute("""
        INSERT INTO v13_signal_audit(
            created_at_utc, created_at_th, symbol, asset_type, side, strategy, entry_price,
            score, adaptive_score, probability, bias, regime, breadth_regime, mtf_consensus,
            rs_score, quality_score, false_risk_score, explanation_json, result_json, status
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        datetime.now(timezone.utc).isoformat(), now_text(), sym, asset_type, side, strategy,
        safe_float(price), int(score or 50), adaptive["adaptive_score"], int(probability or 0), bias,
        regime, breadth, json.dumps(mtf, ensure_ascii=False), rs, quality, false_risk["false_risk_score"],
        json.dumps(explanation, ensure_ascii=False), json.dumps({}, ensure_ascii=False), "OPEN"
    ))
    conn.commit(); conn.close()
    return True


def v13_price_at_or_after(symbol, target_dt):
    try:
        yf_symbol = v12_yf_symbol(symbol) if "v12_yf_symbol" in globals() else normalize_asset(symbol)["yf_symbol"]
        start = (target_dt - timedelta(days=5)).date().isoformat()
        end = (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()
        data = yf.Ticker(yf_symbol).history(start=start, end=end, interval="1d", auto_adjust=False)
        if data is None or data.empty:
            return None, None
        data = data.dropna()
        for idx, row in data.iterrows():
            idx_dt = idx.to_pydatetime()
            if idx_dt.tzinfo is None:
                idx_dt = idx_dt.replace(tzinfo=timezone.utc)
            else:
                idx_dt = idx_dt.astimezone(timezone.utc)
            if idx_dt >= target_dt:
                return float(row["Close"]), idx_dt.isoformat()
        row = data.iloc[-1]
        return float(row["Close"]), data.index[-1].to_pydatetime().isoformat()
    except Exception:
        return None, None


def v13_update_audit_results(limit=200):
    conn = db(); cur = conn.cursor()
    rows = cur.execute("SELECT * FROM v13_signal_audit WHERE status!='CLOSED' ORDER BY id ASC LIMIT ?", (int(limit),)).fetchall()
    updated = 0
    now_utc = datetime.now(timezone.utc)
    for r in rows:
        try:
            created = datetime.fromisoformat(str(r["created_at_utc"]).replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            entry = safe_float(r["entry_price"])
            if not entry:
                continue
            results = json.loads(r["result_json"] or "{}")
            closed_all = True
            for h in V13_SIGNAL_HORIZONS:
                key = f"{h}d"
                if key in results:
                    continue
                if now_utc < created + timedelta(days=h):
                    closed_all = False
                    continue
                px, px_time = v13_price_at_or_after(r["symbol"], created + timedelta(days=h))
                if px is None:
                    closed_all = False
                    continue
                ret = (px / entry - 1) * 100
                side = str(r["side"] or "").upper()
                win = 1 if (side == "CALL" and ret > 0) or (side == "PUT" and ret < 0) else 0
                results[key] = {"price": round(px, 4), "price_time": px_time, "return_pct": round(ret, 3), "win": win}
            status = "CLOSED" if closed_all else "OPEN"
            cur.execute("UPDATE v13_signal_audit SET result_json=?, status=?, evaluated_at_utc=? WHERE id=?", (json.dumps(results, ensure_ascii=False), status, now_utc.isoformat(), r["id"]))
            updated += 1
        except Exception as e:
            print("v13_update_audit_results row error:", e)
            continue
    conn.commit(); conn.close()
    return updated


def v13_winrate_stats(symbol=None, horizon="5d"):
    v13_update_audit_results()
    conn = db(); cur = conn.cursor()
    params = []
    where = "WHERE side IN ('CALL','PUT')"
    if symbol:
        where += " AND symbol=?"; params.append(resolve_delisted_symbol(symbol).upper().replace(".BK", "").replace(".SET", ""))
    rows = cur.execute(f"SELECT * FROM v13_signal_audit {where} ORDER BY id DESC LIMIT 2000", params).fetchall()
    conn.close()
    closed = []
    for r in rows:
        res = json.loads(r["result_json"] or "{}")
        if horizon in res:
            d = dict(r); d["horizon_result"] = res[horizon]; closed.append(d)
    total = len(closed)
    wins = sum(1 for r in closed if int(r["horizon_result"].get("win", 0)) == 1)
    avg_ret = sum(float(r["horizon_result"].get("return_pct", 0)) for r in closed) / total if total else 0
    by_side = {}
    by_strategy = {}
    for bucket_name, key in [("by_side", "side"), ("by_strategy", "strategy")]:
        target = by_side if key == "side" else by_strategy
        for r in closed:
            k = r.get(key) or "UNKNOWN"
            target.setdefault(k, []).append(r)
        for k, arr in list(target.items()):
            target[k] = {
                "signals": len(arr),
                "win_rate_pct": round(sum(1 for x in arr if int(x["horizon_result"].get("win", 0)) == 1) / len(arr) * 100, 2),
                "avg_return_pct": round(sum(float(x["horizon_result"].get("return_pct", 0)) for x in arr) / len(arr), 3),
                "avg_quality_score": round(sum(float(x["quality_score"] or 0) for x in arr) / len(arr), 2),
            }
    return {
        "version": "V13 Historical Win Rate Engine",
        "symbol": symbol.upper() if symbol else "ALL",
        "horizon": horizon,
        "closed_signals": total,
        "win_rate_pct": round(wins / total * 100, 2) if total else 0,
        "avg_return_pct": round(avg_ret, 3),
        "by_side": by_side,
        "by_strategy": by_strategy,
        "sample_warning": "ต้องมี closed signals อย่างน้อยประมาณ %s รายการก่อนใช้สถิติตัดสินใจจริง" % V13_MIN_CLOSED_FOR_STATS,
        "latest_closed": [{k: r[k] for k in ["id", "created_at_th", "symbol", "side", "strategy", "entry_price", "score", "adaptive_score", "quality_score", "false_risk_score"] if k in r} | {"result": r["horizon_result"]} for r in closed[:25]]
    }


def v13_false_signal_detector(horizon="5d"):
    stats = v13_winrate_stats(None, horizon)
    conn = db(); rows = conn.execute("SELECT * FROM v13_signal_audit WHERE side IN ('CALL','PUT') ORDER BY id DESC LIMIT 2000").fetchall(); conn.close()
    groups = {}
    for r in rows:
        res = json.loads(r["result_json"] or "{}")
        if horizon not in res:
            continue
        key_parts = [str(r["side"]), str(r["strategy"]), str(r["regime"] or "UNKNOWN"), str(r["breadth_regime"] or "UNKNOWN")]
        try:
            mtf = json.loads(r["mtf_consensus"] or "{}")
            key_parts.append(mtf.get("direction", "UNKNOWN"))
        except Exception:
            key_parts.append("UNKNOWN")
        key = " | ".join(key_parts)
        groups.setdefault(key, []).append(r)
    rows_out = []
    for key, arr in groups.items():
        if len(arr) < 3:
            continue
        losses = sum(1 for x in arr if int(json.loads(x["result_json"] or "{}")[horizon].get("win", 0)) == 0)
        loss_rate = losses / len(arr) * 100
        avg_false_risk = sum(float(x["false_risk_score"] or 0) for x in arr) / len(arr)
        rows_out.append({"pattern": key, "signals": len(arr), "loss_rate_pct": round(loss_rate, 2), "avg_false_risk_score": round(avg_false_risk, 2)})
    rows_out = sorted(rows_out, key=lambda x: (x["loss_rate_pct"], x["signals"]), reverse=True)
    return {"version": "V13 False Signal Detector", "horizon": horizon, "overall": {"closed_signals": stats["closed_signals"], "win_rate_pct": stats["win_rate_pct"]}, "high_risk_patterns": rows_out[:30], "rule": "patterns need at least 3 closed samples; treat early results as exploratory"}


def v13_strategy_leaderboard(horizon="5d"):
    stats = v13_winrate_stats(None, horizon)
    rows = []
    for strategy, v in stats.get("by_strategy", {}).items():
        expectancy = v["avg_return_pct"] * (v["win_rate_pct"] / 100)
        rows.append({"strategy": strategy, **v, "expectancy_score": round(expectancy, 3)})
    rows = sorted(rows, key=lambda x: (x["expectancy_score"], x["win_rate_pct"], x["signals"]), reverse=True)
    return {"version": "V13 Strategy Leaderboard", "horizon": horizon, "leaderboard": rows, "note": "จัดอันดับจากผลลัพธ์ที่ปิดแล้วใน signal_audit ไม่ใช่การคาดเดา"}


def v13_rs_ranking(limit=None):
    try:
        n = max(5, min(50, int(limit or request.args.get("limit", 20))))
    except Exception:
        n = 20
    out = []
    for sym in V13_DEFAULT_UNIVERSE[:max(n, 20)]:
        try:
            s = resolve_delisted_symbol(sym).upper().replace(".BK", "").replace(".SET", "")
            rs = v13_relative_strength_score(s)
            if rs is None:
                continue
            out.append({"symbol": s, "benchmark": V13_RS_BENCHMARK, "rs_score": rs})
        except Exception:
            continue
    out = sorted(out, key=lambda x: x["rs_score"], reverse=True)[:n]
    return {"version": "V13 Relative Strength Ranking", "ranking": out}


def v13_quality_snapshot(symbol):
    sym = resolve_delisted_symbol(symbol).upper().replace(".BK", "").replace(".SET", "")
    ex = None
    try:
        ex = v10_explainable_score(sym) if "v10_explainable_score" in globals() else None
    except Exception as e:
        ex = {"error": str(e)[:160]}
    base_score = ex.get("final_score") if isinstance(ex, dict) else 50
    decision = ex.get("decision", "WAIT") if isinstance(ex, dict) else "WAIT"
    side = "CALL" if "CALL" in decision else "PUT" if "PUT" in decision else v13_side_from_signal(decision, base_score)
    regime = (ex.get("regime") or {}).get("label") if isinstance(ex, dict) and isinstance(ex.get("regime"), dict) else None
    mtf = v13_mtf_consensus(sym)
    rs = v13_relative_strength_score(sym)
    breadth = v13_safe_breadth_summary()
    adaptive = v13_adaptive_score(sym, base_score, side, regime, breadth, rs, mtf)
    false_risk = v13_false_signal_risk(side, regime, breadth, mtf, rs)
    quality = v13_signal_quality_score(adaptive["adaptive_score"], false_risk["false_risk_score"], side)
    return {"version": "V13 Signal Quality Snapshot", "symbol": sym, "side": side, "base_explainable_score": base_score, "adaptive_score": adaptive, "false_signal_risk": false_risk, "signal_quality_score": quality, "mtf_consensus": mtf, "relative_strength_score": rs, "breadth_regime": breadth, "source_explainable_score": ex}


def v13_dashboard():
    horizon = request.args.get("horizon", "5d") if "request" in globals() else "5d"
    winrate = v13_winrate_stats(None, horizon)
    false_signals = v13_false_signal_detector(horizon)
    leaderboard = v13_strategy_leaderboard(horizon)
    rs = v13_rs_ranking(10)
    return {
        "version": "V13 Signal Quality Layer Free 100%",
        "time": now_text(),
        "executive_summary": {
            "closed_signals": winrate.get("closed_signals"),
            "win_rate_pct": winrate.get("win_rate_pct"),
            "avg_return_pct": winrate.get("avg_return_pct"),
            "best_strategy": (leaderboard.get("leaderboard") or [{}])[0],
            "highest_false_signal_pattern": (false_signals.get("high_risk_patterns") or [{}])[0],
            "top_relative_strength": (rs.get("ranking") or [{}])[:5]
        },
        "winrate": winrate,
        "strategy_leaderboard": leaderboard,
        "false_signal_detector": false_signals,
        "relative_strength_ranking": rs,
        "routes": ["/v13/status", "/v13/dashboard", "/v13/audit", "/v13/winrate", "/v13/false-signals", "/v13/adaptive/<symbol>", "/v13/mtf/<symbol>", "/v13/rs-ranking", "/v13/leaderboard"]
    }


@app.route("/v13/status", methods=["GET"])
def v13_status_route():
    return jsonify({
        "version": "V13 Signal Quality Layer Free 100%",
        "enabled": V13_ENABLED,
        "bugfixes": {
            "us_session_start_th": US_SESSION_START_TH,
            "us_session_end_th": US_SESSION_END_TH,
            "us_allow_premarket_alerts": US_ALLOW_PREMARKET_ALERTS,
            "premarket_reminder_enabled": ENABLE_PREMARKET_REMINDER,
            "premarket_reminder_th": PREMARKET_REMINDER_TH,
            "top5_daily_time_th": TOP5_DAILY_TIME_TH,
            "intuch_alias": DELISTED_SYMBOL_ALIASES.get("INTUCH")
        },
        "modules": ["Signal Audit Engine", "Historical Win Rate Engine", "False Signal Detector", "Adaptive Scoring", "Multi-Timeframe Consensus", "Relative Strength Ranking", "Strategy Leaderboard", "Signal Quality Dashboard"],
        "routes": ["/v13/dashboard", "/v13/audit", "/v13/winrate", "/v13/false-signals", "/v13/adaptive/<symbol>", "/v13/mtf/<symbol>", "/v13/rs-ranking", "/v13/leaderboard"]
    })


@app.route("/v13/dashboard", methods=["GET"])
def v13_dashboard_route():
    return jsonify(v13_dashboard())


@app.route("/v13/audit", methods=["GET"])
def v13_audit_route():
    v13_update_audit_results()
    conn = db(); rows = conn.execute("SELECT * FROM v13_signal_audit ORDER BY id DESC LIMIT 100").fetchall(); conn.close()
    return jsonify({"version": "V13 Signal Audit Engine", "count": len(rows), "latest": [dict(r) for r in rows]})


@app.route("/v13/winrate", methods=["GET"])
def v13_winrate_route():
    return jsonify(v13_winrate_stats(request.args.get("symbol"), request.args.get("horizon", "5d")))


@app.route("/v13/false-signals", methods=["GET"])
def v13_false_signals_route():
    return jsonify(v13_false_signal_detector(request.args.get("horizon", "5d")))


@app.route("/v13/adaptive/<symbol>", methods=["GET"])
def v13_adaptive_route(symbol):
    return jsonify(v13_quality_snapshot(symbol))


@app.route("/v13/mtf/<symbol>", methods=["GET"])
def v13_mtf_route(symbol):
    return jsonify(v13_mtf_consensus(symbol))


@app.route("/v13/rs-ranking", methods=["GET"])
def v13_rs_ranking_route():
    return jsonify(v13_rs_ranking(request.args.get("limit")))


@app.route("/v13/leaderboard", methods=["GET"])
def v13_leaderboard_route():
    return jsonify(v13_strategy_leaderboard(request.args.get("horizon", "5d")))

init_db()
v10_init_db()
v11_init_db()
v13_init_db()

# __main__ runner moved to end by V30 so all appended institutional layers are registered before app.run.

# ============================================================
# V24 PROFESSIONAL QUANT PLATFORM
# Walk Forward / Monte Carlo / Expectancy / Sharpe / Profit Factor
# Kelly Position Sizing / Auto Portfolio Allocation
# Appended as a non-destructive layer on top of the latest monolith.
# ============================================================

V24_VERSION = "V24.0 Professional Quant Platform"

V24_DEFAULT_STARTING_CAPITAL = float(os.getenv("V24_STARTING_CAPITAL", "10000"))
V24_MAX_ALLOC_PER_SYMBOL = float(os.getenv("V24_MAX_ALLOC_PER_SYMBOL", "0.18"))
V24_MAX_ALLOC_PER_SECTOR = float(os.getenv("V24_MAX_ALLOC_PER_SECTOR", "0.35"))
V24_MAX_KELLY_FRACTION = float(os.getenv("V24_MAX_KELLY_FRACTION", "0.25"))
V24_MONTE_CARLO_RUNS = int(os.getenv("V24_MONTE_CARLO_RUNS", "1000"))
V24_MONTE_CARLO_TRADES = int(os.getenv("V24_MONTE_CARLO_TRADES", "100"))
V24_RISK_FREE_RATE = float(os.getenv("V24_RISK_FREE_RATE", "0.00"))

V24_SECTOR_MAP = {
    "NVDA":"Semiconductor", "AMD":"Semiconductor", "AVGO":"Semiconductor", "TSM":"Semiconductor",
    "MRVL":"Semiconductor", "AMKR":"Semiconductor", "INTC":"Semiconductor", "MU":"Semiconductor",
    "AAOI":"Semiconductor", "AEHR":"Semiconductor", "WDC":"Semiconductor", "AXTI":"Semiconductor",
    "AAPL":"Mega Cap Tech", "MSFT":"Mega Cap Tech", "AMZN":"Mega Cap Tech", "META":"Mega Cap Tech",
    "GOOG":"Mega Cap Tech", "GOOGL":"Mega Cap Tech", "NFLX":"Mega Cap Tech",
    "TSLA":"EV / High Beta", "PLTR":"AI / Data", "CRWD":"Cybersecurity", "SNOW":"Cloud", "NET":"Cloud",
    "RKLB":"Space / Aerospace", "ASTS":"Space / Telecom", "AVAV":"Defense / Drone", "KTOS":"Defense",
    "OKLO":"Nuclear / Energy", "CEG":"Nuclear / Energy", "VST":"Energy", "LEU":"Uranium", "UUUU":"Uranium",
    "HOOD":"Fintech", "COIN":"Crypto", "MSTR":"Crypto", "IREN":"Crypto", "CIFR":"Crypto",
    "IONQ":"Quantum", "RGTI":"Quantum", "QBTS":"Quantum", "QUBT":"Quantum",
    "QQQ":"ETF", "SPY":"ETF", "IWM":"ETF", "TQQQ":"ETF", "SOXL":"ETF", "SQQQ":"ETF",
    "GOLD":"Gold", "XAUUSD":"Gold", "XAU/USD":"Gold",
}


def v24_safe_float(x, default=0.0):
    try:
        if x is None or x == "":
            return default
        return float(str(x).replace(",", "").strip())
    except Exception:
        return default


def v24_now():
    try:
        return now_text()
    except Exception:
        return (datetime.now(timezone.utc) + timedelta(hours=7)).strftime("%d/%m/%Y %H:%M")


def v24_conn_execute(sql, params=(), fetch="none"):
    conn = db()
    try:
        cur = conn.execute(sql, params or ())
        if fetch == "one":
            row = cur.fetchone()
            return dict(row) if row else None
        if fetch == "all":
            rows = cur.fetchall()
            return [dict(r) for r in rows]
        conn.commit()
        return None
    finally:
        conn.close()


def v24_init_db():
    v24_conn_execute("""
        CREATE TABLE IF NOT EXISTS quant_signal_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            sector TEXT,
            strategy TEXT,
            side TEXT,
            score REAL,
            risk_grade TEXT,
            entry REAL,
            tp1 REAL,
            tp2 REAL,
            sl REAL,
            outcome TEXT DEFAULT 'PENDING',
            exit_price REAL,
            r_multiple REAL DEFAULT 0,
            pnl REAL DEFAULT 0,
            holding_minutes INTEGER DEFAULT 0,
            source TEXT DEFAULT 'v24',
            notes TEXT
        )
    """)
    v24_conn_execute("""
        CREATE TABLE IF NOT EXISTS quant_portfolio_allocations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            sector TEXT,
            weight REAL,
            kelly_fraction REAL,
            score REAL,
            reason TEXT
        )
    """)
    v24_conn_execute("""
        CREATE TABLE IF NOT EXISTS quant_walk_forward_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            train_count INTEGER,
            test_count INTEGER,
            train_expectancy REAL,
            test_expectancy REAL,
            test_hit_rate REAL,
            notes TEXT
        )
    """)


def v24_sector(symbol):
    return V24_SECTOR_MAP.get(str(symbol or "").upper(), "Other")


def v24_read_outcomes(limit=1000):
    """Read outcome records from V24 table first, then fall back to legacy tables when present."""
    rows = []
    try:
        rows = v24_conn_execute(
            "SELECT * FROM quant_signal_outcomes WHERE outcome!='PENDING' ORDER BY id DESC LIMIT ?",
            (int(limit),), "all"
        ) or []
    except Exception:
        rows = []
    if rows:
        return list(reversed(rows))

    # Fallback 1: closed_outcomes if journal module exists.
    try:
        rows = v24_conn_execute(
            "SELECT symbol, strategy, side, r_multiple, pnl, result AS outcome, closed_at AS created_at FROM closed_outcomes ORDER BY id DESC LIMIT ?",
            (int(limit),), "all"
        ) or []
        if rows:
            for r in rows:
                r.setdefault("sector", v24_sector(r.get("symbol")))
            return list(reversed(rows))
    except Exception:
        pass

    # Fallback 2: signals table has no outcome, so return empty rather than inventing results.
    return []


def v24_metric_summary(rows):
    rs = [v24_safe_float(r.get("r_multiple"), 0.0) for r in rows]
    wins = [x for x in rs if x > 0]
    losses = [x for x in rs if x < 0]
    n = len(rs)
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    expectancy = (sum(rs) / n) if n else 0.0
    hit_rate = (len(wins) / n * 100.0) if n else 0.0
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (gross_win if gross_win > 0 else 0.0)
    avg_win = (sum(wins) / len(wins)) if wins else 0.0
    avg_loss = (abs(sum(losses)) / len(losses)) if losses else 0.0
    kelly = 0.0
    if avg_win > 0 and avg_loss > 0 and n > 0:
        p = len(wins) / n
        b = avg_win / avg_loss
        kelly = p - ((1 - p) / b)
        kelly = max(0.0, min(V24_MAX_KELLY_FRACTION, kelly))
    sharpe = 0.0
    if len(rs) >= 2:
        mean = sum(rs) / len(rs)
        var = sum((x - mean) ** 2 for x in rs) / (len(rs) - 1)
        sd = var ** 0.5
        sharpe = ((mean - V24_RISK_FREE_RATE) / sd) if sd else 0.0
    return {
        "signals": n,
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": n - len(wins) - len(losses),
        "hit_rate": round(hit_rate, 2),
        "expectancy_r": round(expectancy, 4),
        "profit_factor": round(profit_factor, 4),
        "avg_win_r": round(avg_win, 4),
        "avg_loss_r": round(avg_loss, 4),
        "kelly_fraction": round(kelly, 4),
        "sharpe_ratio": round(sharpe, 4),
        "total_r": round(sum(rs), 4),
    }


def v24_group_metrics(rows, key):
    groups = {}
    for r in rows:
        k = str(r.get(key) or "UNKNOWN").upper() if key == "symbol" else str(r.get(key) or "UNKNOWN")
        groups.setdefault(k, []).append(r)
    out = []
    for k, vals in groups.items():
        m = v24_metric_summary(vals)
        m[key] = k
        out.append(m)
    out.sort(key=lambda x: (x.get("profit_factor", 0), x.get("expectancy_r", 0), x.get("signals", 0)), reverse=True)
    return out


def v24_monte_carlo(rows=None, runs=None, trades=None):
    rows = rows if rows is not None else v24_read_outcomes()
    returns = [v24_safe_float(r.get("r_multiple"), 0.0) for r in rows if r.get("r_multiple") is not None]
    runs = int(runs or V24_MONTE_CARLO_RUNS)
    trades = int(trades or V24_MONTE_CARLO_TRADES)
    if len(returns) < 5:
        return {"ok": False, "message": "Need at least 5 closed outcomes", "closed_outcomes": len(returns)}
    finals, max_dds = [], []
    for _ in range(max(1, runs)):
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for _ in range(max(1, trades)):
            equity += random.choice(returns)
            peak = max(peak, equity)
            max_dd = min(max_dd, equity - peak)
        finals.append(equity)
        max_dds.append(max_dd)
    finals.sort(); max_dds.sort()
    def pct(arr, p):
        if not arr: return 0.0
        idx = min(len(arr)-1, max(0, int(len(arr) * p)))
        return round(arr[idx], 4)
    return {
        "ok": True,
        "runs": runs,
        "trades_per_run": trades,
        "final_r_p10": pct(finals, 0.10),
        "final_r_p50": pct(finals, 0.50),
        "final_r_p90": pct(finals, 0.90),
        "max_dd_r_p10": pct(max_dds, 0.10),
        "max_dd_r_p50": pct(max_dds, 0.50),
        "max_dd_r_p90": pct(max_dds, 0.90),
    }


def v24_walk_forward(train_ratio=0.70):
    rows = v24_read_outcomes(2000)
    if len(rows) < 20:
        return {"ok": False, "message": "Need at least 20 closed outcomes for walk-forward", "closed_outcomes": len(rows)}
    split = max(1, min(len(rows)-1, int(len(rows) * float(train_ratio))))
    train = rows[:split]
    test = rows[split:]
    train_m = v24_metric_summary(train)
    test_m = v24_metric_summary(test)
    try:
        v24_conn_execute(
            "INSERT INTO quant_walk_forward_runs (created_at, train_count, test_count, train_expectancy, test_expectancy, test_hit_rate, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (v24_now(), len(train), len(test), train_m.get("expectancy_r"), test_m.get("expectancy_r"), test_m.get("hit_rate"), "auto run")
        )
    except Exception:
        pass
    return {"ok": True, "train": train_m, "test": test_m, "train_count": len(train), "test_count": len(test)}


def v24_auto_portfolio_allocation(candidates=None, max_positions=5):
    """Rank and allocate candidate alerts/signals using expectancy + Kelly + sector caps."""
    candidates = candidates or []
    rows = v24_read_outcomes(2000)
    symbol_stats = {r.get("symbol"): r for r in v24_group_metrics(rows, "symbol")}
    sector_alloc = {}
    chosen = []

    normalized = []
    for c in candidates:
        symbol = str(c.get("symbol") or "").upper()
        if not symbol:
            continue
        sector = c.get("sector") or v24_sector(symbol)
        base_score = v24_safe_float(c.get("score"), 50)
        stat = symbol_stats.get(symbol, {})
        expectancy = v24_safe_float(stat.get("expectancy_r"), 0)
        pf = v24_safe_float(stat.get("profit_factor"), 0)
        kelly = v24_safe_float(stat.get("kelly_fraction"), 0.03)
        rank_score = base_score + expectancy * 8 + min(pf, 3) * 3 + kelly * 40
        normalized.append({**c, "symbol": symbol, "sector": sector, "rank_score": round(rank_score, 4), "kelly_fraction": round(kelly, 4)})

    normalized.sort(key=lambda x: x.get("rank_score", 0), reverse=True)
    for c in normalized:
        if len(chosen) >= int(max_positions):
            break
        sector = c.get("sector") or "Other"
        if sector_alloc.get(sector, 0) >= V24_MAX_ALLOC_PER_SECTOR:
            c["rejected_reason"] = "sector cap"
            continue
        weight = min(V24_MAX_ALLOC_PER_SYMBOL, max(0.02, c.get("kelly_fraction", 0.03)))
        if sector_alloc.get(sector, 0) + weight > V24_MAX_ALLOC_PER_SECTOR:
            weight = max(0.0, V24_MAX_ALLOC_PER_SECTOR - sector_alloc.get(sector, 0))
        if weight <= 0:
            continue
        sector_alloc[sector] = sector_alloc.get(sector, 0) + weight
        c["weight"] = round(weight, 4)
        chosen.append(c)
        try:
            v24_conn_execute(
                "INSERT INTO quant_portfolio_allocations (created_at, symbol, sector, weight, kelly_fraction, score, reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (v24_now(), c.get("symbol"), sector, c.get("weight"), c.get("kelly_fraction"), c.get("score"), "v24 auto allocation")
            )
        except Exception:
            pass
    return {"ok": True, "selected": chosen, "sector_allocation": {k: round(v, 4) for k, v in sector_alloc.items()}, "candidates": len(candidates)}


def v24_quant_snapshot():
    rows = v24_read_outcomes(2000)
    return {
        "ok": True,
        "version": V24_VERSION,
        "overall": v24_metric_summary(rows),
        "by_symbol": v24_group_metrics(rows, "symbol")[:20],
        "by_sector": v24_group_metrics([{**r, "sector": r.get("sector") or v24_sector(r.get("symbol"))} for r in rows], "sector")[:20],
        "by_strategy": v24_group_metrics(rows, "strategy")[:20],
        "monte_carlo": v24_monte_carlo(rows),
    }


def v24_html_table(rows, cols):
    if not rows:
        return "<p>No data yet.</p>"
    th = "".join(f"<th>{c}</th>" for c in cols)
    trs = []
    for r in rows:
        trs.append("<tr>" + "".join(f"<td>{r.get(c, '')}</td>" for c in cols) + "</tr>")
    return f"<table border='1' cellpadding='6' cellspacing='0'><tr>{th}</tr>{''.join(trs)}</table>"


@app.route('/v24')
@app.route('/v24/dashboard')
def v24_dashboard():
    s = v24_quant_snapshot()
    html = f"""
    <html><head><meta charset='utf-8'><title>{V24_VERSION}</title></head>
    <body style='font-family:Arial; padding:24px;'>
    <h1>{V24_VERSION}</h1>
    <h2>Overall Quant Metrics</h2>
    <pre>{json.dumps(s['overall'], ensure_ascii=False, indent=2)}</pre>
    <h2>Top Option Symbols</h2>
    {v24_html_table(s['by_symbol'], ['symbol','signals','hit_rate','profit_factor','expectancy_r','kelly_fraction','sharpe_ratio'])}
    <h2>Sector Ranking</h2>
    {v24_html_table(s['by_sector'], ['sector','signals','hit_rate','profit_factor','expectancy_r','kelly_fraction','sharpe_ratio'])}
    <h2>Strategy Ranking</h2>
    {v24_html_table(s['by_strategy'], ['strategy','signals','hit_rate','profit_factor','expectancy_r','kelly_fraction','sharpe_ratio'])}
    <h2>Monte Carlo</h2>
    <pre>{json.dumps(s['monte_carlo'], ensure_ascii=False, indent=2)}</pre>
    <p><a href='/v24/json'>JSON</a> | <a href='/v24/monte-carlo'>Monte Carlo</a> | <a href='/v24/walk-forward'>Walk Forward</a></p>
    </body></html>
    """
    return Response(html, mimetype='text/html')


@app.route('/v24/json')
def v24_json():
    return jsonify(v24_quant_snapshot())


@app.route('/v24/monte-carlo')
def v24_route_monte_carlo():
    runs = request.args.get('runs')
    trades = request.args.get('trades')
    return jsonify(v24_monte_carlo(runs=int(runs) if runs else None, trades=int(trades) if trades else None))


@app.route('/v24/walk-forward')
def v24_route_walk_forward():
    ratio = v24_safe_float(request.args.get('train_ratio'), 0.70)
    return jsonify(v24_walk_forward(ratio))


@app.route('/v24/expectancy')
def v24_route_expectancy():
    rows = v24_read_outcomes(2000)
    return jsonify({"ok": True, "overall": v24_metric_summary(rows), "by_symbol": v24_group_metrics(rows, 'symbol')[:50], "by_strategy": v24_group_metrics(rows, 'strategy')[:50]})


@app.route('/v24/portfolio/allocation-preview')
def v24_route_allocation_preview():
    # Optional query: symbols=NVDA,AAPL,TSLA&scores=91,88,86
    symbols = [x.strip().upper() for x in str(request.args.get('symbols') or 'NVDA,AAPL,MSFT,TSLA,AMD,QQQ,SPY,GOLD').split(',') if x.strip()]
    scores = [v24_safe_float(x, 80) for x in str(request.args.get('scores') or '').split(',') if x.strip()]
    candidates = []
    for i, sym in enumerate(symbols):
        candidates.append({"symbol": sym, "sector": v24_sector(sym), "score": scores[i] if i < len(scores) else 80})
    return jsonify(v24_auto_portfolio_allocation(candidates))


@app.route('/v24/outcome/add', methods=['GET', 'POST'])
def v24_route_add_outcome():
    data = request.get_json(silent=True) or request.args
    symbol = str(data.get('symbol') or '').upper()
    if not symbol:
        return jsonify({"ok": False, "error": "symbol required"}), 400
    side = str(data.get('side') or 'CALL').upper()
    strategy = str(data.get('strategy') or 'MANUAL').upper()
    entry = v24_safe_float(data.get('entry'), 0)
    tp1 = v24_safe_float(data.get('tp1'), 0)
    tp2 = v24_safe_float(data.get('tp2'), 0)
    sl = v24_safe_float(data.get('sl'), 0)
    outcome = str(data.get('outcome') or 'PENDING').upper()
    exit_price = v24_safe_float(data.get('exit_price'), 0)
    r_multiple = v24_safe_float(data.get('r_multiple'), 0)
    pnl = v24_safe_float(data.get('pnl'), 0)
    score = v24_safe_float(data.get('score'), 0)
    risk_grade = str(data.get('risk_grade') or '')
    sector = str(data.get('sector') or v24_sector(symbol))
    v24_conn_execute(
        "INSERT INTO quant_signal_outcomes (created_at, symbol, sector, strategy, side, score, risk_grade, entry, tp1, tp2, sl, outcome, exit_price, r_multiple, pnl, source, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (v24_now(), symbol, sector, strategy, side, score, risk_grade, entry, tp1, tp2, sl, outcome, exit_price, r_multiple, pnl, 'manual', str(data.get('notes') or ''))
    )
    return jsonify({"ok": True, "message": "V24 outcome saved", "symbol": symbol, "outcome": outcome})


try:
    v24_init_db()
except Exception as e:
    print('v24 init error:', e)

# ============================================================
# END V24 PROFESSIONAL QUANT PLATFORM
# ============================================================


# ============================================================
# V25.1 PROFESSIONAL EXECUTION INTELLIGENCE — MARKET CONTEXT AI
# FOMC / Earnings / VIX / SPY EMA200 context layer before alerts.
# Non-destructive layer appended on top of current production monolith.
# ============================================================

V25_VERSION = "V25.1 Professional Execution Intelligence — Market Context AI"
V25_VIX_HIGH = float(os.getenv("V25_VIX_HIGH", "25"))
V25_VIX_EXTREME = float(os.getenv("V25_VIX_EXTREME", "32"))
V25_EARNINGS_BLOCK_DAYS = int(os.getenv("V25_EARNINGS_BLOCK_DAYS", "1"))
V25_EARNINGS_CAUTION_DAYS = int(os.getenv("V25_EARNINGS_CAUTION_DAYS", "3"))
V25_CONTEXT_STRICT = os.getenv("V25_CONTEXT_STRICT", "true").lower() in {"1", "true", "yes", "on"}
V25_FOMC_DATES = {x.strip() for x in os.getenv("V25_FOMC_DATES", "").split(",") if x.strip()}
V25_CACHE = {}


def v25_today_th():
    return (datetime.now(timezone.utc) + timedelta(hours=7)).strftime("%Y-%m-%d")


def v25_now_th():
    return (datetime.now(timezone.utc) + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")


def v25_cache_get(key, ttl=300):
    item = V25_CACHE.get(key)
    if not item:
        return None
    ts, val = item
    if time.time() - ts > ttl:
        V25_CACHE.pop(key, None)
        return None
    return val


def v25_cache_set(key, val):
    V25_CACHE[key] = (time.time(), val)
    return val


def v25_safe_float(x, default=None):
    try:
        if x is None or x == "":
            return default
        return float(str(x).replace(",", "").strip())
    except Exception:
        return default


def v25_yf_history(symbol, period="1y", interval="1d"):
    key = f"v25_yf:{symbol}:{period}:{interval}"
    cached = v25_cache_get(key, ttl=600)
    if cached is not None:
        return cached
    try:
        data = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
        if data is None or data.empty:
            return v25_cache_set(key, None)
        return v25_cache_set(key, data.dropna())
    except Exception as e:
        print("v25_yf_history error", symbol, e)
        return v25_cache_set(key, None)


def v25_latest_close(symbol):
    data = v25_yf_history(symbol, period="10d", interval="1d")
    try:
        if data is not None and not data.empty:
            return float(data["Close"].dropna().iloc[-1])
    except Exception:
        pass
    return None


def v25_ema(values, period):
    vals = list(values or [])
    if len(vals) < period:
        return None
    k = 2 / (period + 1)
    ema_val = vals[0]
    for price in vals[1:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val


def v25_spy_context():
    data = v25_yf_history("SPY", period="2y", interval="1d")
    if data is None or data.empty:
        return {"ok": False, "symbol": "SPY", "reason": "no_data"}
    closes = [float(x) for x in data["Close"].dropna().tolist()]
    price = closes[-1] if closes else None
    ema200 = v25_ema(closes, 200)
    above = bool(price and ema200 and price >= ema200)
    return {
        "ok": True,
        "symbol": "SPY",
        "price": round(price, 2) if price else None,
        "ema200": round(ema200, 2) if ema200 else None,
        "above_ema200": above,
        "bias": "RISK_ON" if above else "RISK_OFF",
    }


def v25_vix_context():
    # Yahoo usually supports ^VIX. Fallback stays neutral if unavailable.
    vix = v25_latest_close("^VIX")
    status = "UNKNOWN"
    penalty = 0
    if vix is not None:
        if vix >= V25_VIX_EXTREME:
            status = "EXTREME_RISK"
            penalty = -14
        elif vix >= V25_VIX_HIGH:
            status = "HIGH_RISK"
            penalty = -9
        elif vix >= 20:
            status = "ELEVATED"
            penalty = -4
        else:
            status = "NORMAL"
            penalty = 0
    return {"ok": vix is not None, "vix": round(vix, 2) if vix else None, "status": status, "call_score_adjustment": penalty}


def v25_is_fomc_today():
    today = v25_today_th()
    if today in V25_FOMC_DATES:
        return {"is_fomc": True, "source": "V25_FOMC_DATES", "date": today, "score_adjustment": -10}

    # Optional lightweight Finnhub economic-calendar attempt. If unavailable, return neutral.
    if FINNHUB_API_KEY:
        try:
            r = requests.get(
                "https://finnhub.io/api/v1/calendar/economic",
                params={"from": today, "to": today, "token": FINNHUB_API_KEY},
                headers=REQUEST_HEADERS,
                timeout=12,
            )
            data = r.json() if r is not None else {}
            events = data.get("economicCalendar") or data.get("events") or []
            hits = []
            for ev in events:
                title = str(ev.get("event") or ev.get("title") or ev.get("name") or "")
                if any(k in title.upper() for k in ["FOMC", "FED INTEREST", "FEDERAL RESERVE", "RATE DECISION"]):
                    hits.append(title)
            if hits:
                return {"is_fomc": True, "source": "Finnhub economic calendar", "date": today, "events": hits[:3], "score_adjustment": -10}
        except Exception as e:
            print("v25_fomc_finnhub error", e)

    return {"is_fomc": False, "source": "none", "date": today, "score_adjustment": 0}


def v25_parse_date(value):
    if not value:
        return None
    try:
        if isinstance(value, (list, tuple)) and value:
            value = value[0]
        s = str(value)
        # Handles pandas Timestamp, date strings, ISO strings.
        return datetime.fromisoformat(s[:10]).date()
    except Exception:
        try:
            return value.date()
        except Exception:
            return None


def v25_earnings_context(symbol):
    sym = str(symbol or "").upper().strip()
    if not sym or sym in {"SPY", "QQQ", "IWM", "GOLD", "XAUUSD", "XAU/USD"}:
        return {"ok": False, "symbol": sym, "has_earnings": False, "reason": "not_applicable", "score_adjustment": 0}
    key = f"v25_earn:{sym}"
    cached = v25_cache_get(key, ttl=3600)
    if cached is not None:
        return cached
    today = datetime.now(timezone.utc).date()
    try:
        t = yf.Ticker(sym)
        dt = None
        try:
            ed = t.get_earnings_dates(limit=4)
            if ed is not None and not ed.empty:
                for idx in list(ed.index):
                    d = v25_parse_date(idx)
                    if d and d >= today:
                        dt = d
                        break
        except Exception:
            pass
        if dt is None:
            try:
                info = t.get_info() or {}
                raw = info.get("earningsDate") or info.get("earningsTimestamp")
                if isinstance(raw, (int, float)):
                    dt = datetime.utcfromtimestamp(int(raw)).date()
                else:
                    dt = v25_parse_date(raw)
            except Exception:
                pass
        if not dt:
            return v25_cache_set(key, {"ok": False, "symbol": sym, "has_earnings": False, "reason": "no_upcoming_earnings_found", "score_adjustment": 0})
        days = (dt - today).days
        if 0 <= days <= V25_EARNINGS_BLOCK_DAYS:
            adj, risk = -18, "BLOCK_OR_REDUCE_SIZE"
        elif 0 <= days <= V25_EARNINGS_CAUTION_DAYS:
            adj, risk = -10, "CAUTION_REDUCE_SIZE"
        else:
            adj, risk = 0, "OK"
        return v25_cache_set(key, {"ok": True, "symbol": sym, "has_earnings": True, "earnings_date": str(dt), "days_to_earnings": days, "risk": risk, "score_adjustment": adj})
    except Exception as e:
        return v25_cache_set(key, {"ok": False, "symbol": sym, "has_earnings": False, "reason": str(e), "score_adjustment": 0})


def v25_symbol_type(symbol):
    sym = str(symbol or "").upper().strip()
    if sym in {"GOLD", "XAU", "XAUUSD", "XAU/USD"}:
        return "GOLD"
    if sym in {"QQQ", "SPY", "IWM", "TQQQ", "SOXL", "SQQQ"}:
        return "ETF"
    return "US_STOCK"


def v25_market_context(symbol="NVDA"):
    sym = str(symbol or "NVDA").upper().strip()
    fomc = v25_is_fomc_today()
    vix = v25_vix_context()
    spy = v25_spy_context()
    earnings = v25_earnings_context(sym)

    context_score = 100
    reasons = []
    blockers = []

    if fomc.get("is_fomc"):
        context_score += int(fomc.get("score_adjustment") or -10)
        reasons.append("FOMC / Fed event today: reduce conviction")
        if V25_CONTEXT_STRICT:
            blockers.append("FOMC_DAY")

    if vix.get("status") in {"HIGH_RISK", "EXTREME_RISK"}:
        context_score += int(vix.get("call_score_adjustment") or 0)
        reasons.append(f"VIX {vix.get('vix')} = {vix.get('status')}: reduce CALL/high-beta score")
        if vix.get("status") == "EXTREME_RISK":
            blockers.append("VIX_EXTREME")

    if spy.get("ok") and not spy.get("above_ema200"):
        context_score -= 12
        reasons.append("SPY below EMA200: market risk-off")
        if V25_CONTEXT_STRICT:
            blockers.append("SPY_BELOW_EMA200")
    elif spy.get("ok") and spy.get("above_ema200"):
        reasons.append("SPY above EMA200: market risk-on background")

    if earnings.get("score_adjustment"):
        context_score += int(earnings.get("score_adjustment") or 0)
        reasons.append(f"Earnings risk in {earnings.get('days_to_earnings')} day(s): {earnings.get('risk')}")
        if earnings.get("risk") == "BLOCK_OR_REDUCE_SIZE" and V25_CONTEXT_STRICT:
            blockers.append("EARNINGS_NEAR")

    context_score = max(0, min(100, int(context_score)))
    return {
        "ok": True,
        "version": V25_VERSION,
        "symbol": sym,
        "asset_type": v25_symbol_type(sym),
        "timestamp_th": v25_now_th(),
        "context_score": context_score,
        "risk_mode": "BLOCK" if blockers else "NORMAL" if context_score >= 80 else "CAUTION",
        "blockers": blockers,
        "reasons": reasons or ["No major market-context blocker detected"],
        "fomc": fomc,
        "earnings": earnings,
        "vix": vix,
        "spy": spy,
    }


def v25_adjust_score(symbol, base_score, side="CALL"):
    base = int(v25_safe_float(base_score, 50) or 50)
    ctx = v25_market_context(symbol)
    adjusted = base
    adjustments = []

    # FOMC / earnings / SPY are already represented by context score gap.
    context_gap = ctx.get("context_score", 100) - 100
    if context_gap:
        adjusted += int(context_gap)
        adjustments.append({"source": "market_context", "points": int(context_gap)})

    # Extra explicit CALL penalty on high VIX.
    if str(side or "CALL").upper().startswith("CALL") and ctx.get("vix", {}).get("status") in {"HIGH_RISK", "EXTREME_RISK"}:
        extra = -4 if ctx["vix"]["status"] == "HIGH_RISK" else -8
        adjusted += extra
        adjustments.append({"source": "vix_call_extra", "points": extra})

    adjusted = max(0, min(100, int(adjusted)))
    decision = "ALLOW"
    if ctx.get("blockers"):
        decision = "BLOCK"
    elif adjusted < 85:
        decision = "REJECT_SCORE_AFTER_CONTEXT"
    elif ctx.get("context_score", 100) < 80:
        decision = "CAUTION_REDUCE_SIZE"

    result = {
        "ok": True,
        "symbol": str(symbol or "").upper(),
        "side": str(side or "CALL").upper(),
        "base_score": base,
        "adjusted_score": adjusted,
        "decision": decision,
        "adjustments": adjustments,
        "context": ctx,
    }
    v25_save_context_snapshot(result)
    return result


def v25_save_context_snapshot(result):
    try:
        v24_conn_execute("""
            CREATE TABLE IF NOT EXISTS market_context_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                symbol TEXT,
                side TEXT,
                base_score REAL,
                adjusted_score REAL,
                decision TEXT,
                context_score REAL,
                blockers TEXT,
                payload TEXT
            )
        """)
        ctx = result.get("context", {}) or {}
        v24_conn_execute(
            "INSERT INTO market_context_snapshots (created_at, symbol, side, base_score, adjusted_score, decision, context_score, blockers, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (v25_now_th(), result.get("symbol"), result.get("side"), result.get("base_score"), result.get("adjusted_score"), result.get("decision"), ctx.get("context_score"), ",".join(ctx.get("blockers") or []), json.dumps(result, ensure_ascii=False)[:8000])
        )
    except Exception as e:
        print("v25_save_context_snapshot error", e)


def v25_context_dashboard_html(symbol="NVDA"):
    ctx = v25_market_context(symbol)
    sample = v25_adjust_score(symbol, request.args.get("score") or 91, request.args.get("side") or "CALL")
    rows = []
    try:
        rows = v24_conn_execute("SELECT created_at, symbol, side, base_score, adjusted_score, decision, context_score, blockers FROM market_context_snapshots ORDER BY id DESC LIMIT 25", fetch="all") or []
    except Exception:
        rows = []
    table = "<p>No context snapshots yet.</p>"
    if rows:
        table = "<table border='1' cellpadding='6' cellspacing='0'><tr><th>Time</th><th>Symbol</th><th>Side</th><th>Base</th><th>Adjusted</th><th>Decision</th><th>Context</th><th>Blockers</th></tr>" + "".join(
            f"<tr><td>{r.get('created_at')}</td><td>{r.get('symbol')}</td><td>{r.get('side')}</td><td>{r.get('base_score')}</td><td>{r.get('adjusted_score')}</td><td>{r.get('decision')}</td><td>{r.get('context_score')}</td><td>{r.get('blockers')}</td></tr>" for r in rows
        ) + "</table>"
    return f"""
    <html><head><meta charset='utf-8'><title>{V25_VERSION}</title></head>
    <body style='font-family:Arial; padding:24px;'>
      <h1>{V25_VERSION}</h1>
      <h2>Market Context: {symbol.upper()}</h2>
      <pre>{json.dumps(ctx, ensure_ascii=False, indent=2)}</pre>
      <h2>Sample Adjusted Score</h2>
      <pre>{json.dumps(sample, ensure_ascii=False, indent=2)}</pre>
      <h2>Recent Context Snapshots</h2>
      {table}
      <p><a href='/v25/context/{symbol.upper()}'>JSON Context</a> | <a href='/v25/adjust-score?symbol={symbol.upper()}&score=91&side=CALL'>Adjust Score JSON</a> | <a href='/v24'>V24 Quant</a></p>
    </body></html>
    """


@app.route('/v25')
@app.route('/v25/dashboard')
def v25_dashboard():
    symbol = request.args.get('symbol') or 'NVDA'
    return Response(v25_context_dashboard_html(symbol), mimetype='text/html')


@app.route('/v25/health')
def v25_health():
    return jsonify({"ok": True, "version": V25_VERSION})


@app.route('/v25/context')
def v25_route_context_default():
    return jsonify(v25_market_context(request.args.get('symbol') or 'NVDA'))


@app.route('/v25/context/<symbol>')
def v25_route_context(symbol):
    return jsonify(v25_market_context(symbol))


@app.route('/v25/adjust-score')
def v25_route_adjust_score():
    return jsonify(v25_adjust_score(request.args.get('symbol') or 'NVDA', request.args.get('score') or 91, request.args.get('side') or 'CALL'))


try:
    # Ensure V25 table exists at import time under gunicorn.
    v25_save_context_snapshot({"symbol": "INIT", "side": "NA", "base_score": 0, "adjusted_score": 0, "decision": "INIT", "context": {"context_score": 100, "blockers": []}})
except Exception as e:
    print('v25 init warning:', e)

# ============================================================
# END V25.1 MARKET CONTEXT AI
# ============================================================

# ============================================================
# V25.2 EARNINGS INTELLIGENCE ENGINE
# ต่อจาก V25.1 Market Context AI โดยไม่ลบระบบเดิม
# ============================================================
V25_2_VERSION = "V25.2 Earnings Intelligence Engine"
V25_EARNINGS_BLOCK_DAYS = int(os.getenv("V25_EARNINGS_BLOCK_DAYS", "1"))
V25_EARNINGS_CAUTION_DAYS = int(os.getenv("V25_EARNINGS_CAUTION_DAYS", "5"))
V25_EARNINGS_LOOKAHEAD_DAYS = int(os.getenv("V25_EARNINGS_LOOKAHEAD_DAYS", "21"))
V25_EARNINGS_REDUCE_SIZE_PCT = int(os.getenv("V25_EARNINGS_REDUCE_SIZE_PCT", "50"))
V25_EARNINGS_STRICT_BLOCK = os.getenv("V25_EARNINGS_STRICT_BLOCK", "true").lower() in {"1", "true", "yes", "on"}


def v25_2_init_db():
    try:
        v24_conn_execute("""
            CREATE TABLE IF NOT EXISTS earnings_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                earnings_date TEXT,
                session TEXT,
                days_to_earnings INTEGER,
                risk_level TEXT,
                action TEXT,
                score_adjustment REAL DEFAULT 0,
                position_size_factor REAL DEFAULT 1,
                source TEXT,
                payload TEXT
            )
        """)
        v24_conn_execute("""
            CREATE TABLE IF NOT EXISTS earnings_blocked_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT,
                base_score REAL,
                adjusted_score REAL,
                reason TEXT,
                earnings_date TEXT,
                days_to_earnings INTEGER,
                risk_level TEXT,
                payload TEXT
            )
        """)
    except Exception as e:
        print("v25_2_init_db error", e)


def v25_2_today_th_date():
    return (datetime.now(timezone.utc) + timedelta(hours=7)).date()


def v25_2_parse_date_any(x):
    if not x:
        return None
    try:
        if isinstance(x, datetime):
            return x.date()
        # pandas Timestamp also supports date()
        if hasattr(x, "date"):
            return x.date()
        if isinstance(x, (int, float)):
            return datetime.utcfromtimestamp(int(x)).date()
        s = str(x).strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(s[:10], fmt).date()
            except Exception:
                pass
        # ISO fallback
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        except Exception:
            return None
    except Exception:
        return None


def v25_2_finnhub_earnings(symbol):
    if not FINNHUB_API_KEY:
        return None
    try:
        today = v25_2_today_th_date()
        to_date = today + timedelta(days=V25_EARNINGS_LOOKAHEAD_DAYS)
        r = requests.get(
            "https://finnhub.io/api/v1/calendar/earnings",
            params={"from": str(today), "to": str(to_date), "symbol": str(symbol).upper(), "token": FINNHUB_API_KEY},
            headers=REQUEST_HEADERS,
            timeout=20,
        )
        data = r.json()
        rows = data.get("earningsCalendar") if isinstance(data, dict) else None
        if not rows:
            return None
        row = rows[0]
        dt = v25_2_parse_date_any(row.get("date"))
        if not dt:
            return None
        hour = str(row.get("hour") or "").lower()
        if "amc" in hour or "after" in hour:
            session = "After Market"
        elif "bmo" in hour or "before" in hour:
            session = "Before Open"
        else:
            session = row.get("hour") or "Unknown"
        return {"date": dt, "session": session, "source": "Finnhub", "raw": row}
    except Exception as e:
        print("v25_2_finnhub_earnings error", symbol, e)
        return None


def v25_2_yahoo_earnings(symbol):
    try:
        t = yf.Ticker(str(symbol).upper())
        # Best current yfinance method
        try:
            ed = t.get_earnings_dates(limit=4)
            if ed is not None and not ed.empty:
                idx = list(ed.index)
                today = v25_2_today_th_date()
                future = []
                for x in idx:
                    dt = v25_2_parse_date_any(x)
                    if dt and dt >= today:
                        future.append(dt)
                if future:
                    return {"date": min(future), "session": "Unknown", "source": "Yahoo Finance", "raw": "get_earnings_dates"}
        except Exception:
            pass
        # info fallback
        try:
            info = t.get_info() or {}
        except Exception:
            info = getattr(t, "info", {}) or {}
        for key in ("earningsTimestamp", "earningsDate", "earningsTimestampStart", "earningsTimestampEnd"):
            raw = info.get(key)
            if isinstance(raw, list) and raw:
                raw = raw[0]
            dt = v25_2_parse_date_any(raw)
            if dt:
                return {"date": dt, "session": "Unknown", "source": "Yahoo Finance info", "raw": {key: str(raw)}}
    except Exception as e:
        print("v25_2_yahoo_earnings error", symbol, e)
    return None


def v25_2_earnings_lookup(symbol):
    sym = str(symbol or "").upper().strip()
    if not sym or sym in {"GOLD", "XAU", "XAUUSD", "XAU/USD", "SPY", "QQQ", "IWM", "TQQQ", "SOXL", "SQQQ"}:
        return {"ok": True, "symbol": sym, "has_earnings": False, "reason": "no_company_earnings_for_asset"}
    cached = cache_get(f"V25_2_EARNINGS:{sym}")
    if cached:
        return cached
    event = v25_2_finnhub_earnings(sym) or v25_2_yahoo_earnings(sym)
    if not event:
        result = {"ok": True, "symbol": sym, "has_earnings": False, "reason": "no_upcoming_earnings_found", "score_adjustment": 0, "position_size_factor": 1.0, "action": "ALLOW"}
        cache_set(f"V25_2_EARNINGS:{sym}", result)
        return result
    today = v25_2_today_th_date()
    days = (event["date"] - today).days
    if days < 0:
        risk_level = "PAST"
        action = "ALLOW"
        score_adj = 0
        size_factor = 1.0
    elif days <= V25_EARNINGS_BLOCK_DAYS:
        risk_level = "EXTREME"
        action = "BLOCK" if V25_EARNINGS_STRICT_BLOCK else "REDUCE_SIZE"
        score_adj = -22
        size_factor = 0.25
    elif days <= 2:
        risk_level = "HIGH"
        action = "REDUCE_SIZE"
        score_adj = -16
        size_factor = V25_EARNINGS_REDUCE_SIZE_PCT / 100.0
    elif days <= V25_EARNINGS_CAUTION_DAYS:
        risk_level = "CAUTION"
        action = "REDUCE_SIZE"
        score_adj = -8
        size_factor = 0.75
    else:
        risk_level = "NORMAL"
        action = "ALLOW"
        score_adj = 0
        size_factor = 1.0
    result = {
        "ok": True,
        "version": V25_2_VERSION,
        "symbol": sym,
        "has_earnings": True,
        "earnings_date": str(event["date"]),
        "session": event.get("session") or "Unknown",
        "days_to_earnings": days,
        "risk_level": risk_level,
        "action": action,
        "score_adjustment": score_adj,
        "position_size_factor": round(size_factor, 2),
        "source": event.get("source"),
    }
    try:
        v24_conn_execute(
            "INSERT INTO earnings_events (created_at, symbol, earnings_date, session, days_to_earnings, risk_level, action, score_adjustment, position_size_factor, source, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (v25_now_th(), sym, result.get("earnings_date"), result.get("session"), days, risk_level, action, score_adj, round(size_factor, 2), event.get("source"), json.dumps(result, ensure_ascii=False)[:8000])
        )
    except Exception as e:
        print("v25_2 save earnings_event error", e)
    cache_set(f"V25_2_EARNINGS:{sym}", result)
    return result


# Override V25.1 earnings context so Market Context AI uses the stronger V25.2 engine.
def v25_earnings_context(symbol):
    return v25_2_earnings_lookup(symbol)


def v25_2_adjust_for_earnings(symbol, base_score, side="CALL"):
    base = int(v25_safe_float(base_score, 50) or 50)
    e = v25_2_earnings_lookup(symbol)
    adjusted = max(0, min(100, base + int(e.get("score_adjustment") or 0)))
    decision = "ALLOW"
    reason = "NO_EARNINGS_BLOCKER"
    if e.get("action") == "BLOCK":
        decision = "BLOCK"
        reason = f"EARNINGS_{e.get('risk_level')}_{e.get('days_to_earnings')}_DAYS"
    elif e.get("action") == "REDUCE_SIZE":
        decision = "REDUCE_SIZE"
        reason = f"EARNINGS_{e.get('risk_level')}_{e.get('days_to_earnings')}_DAYS"
    payload = {"ok": True, "version": V25_2_VERSION, "symbol": str(symbol).upper(), "side": str(side).upper(), "base_score": base, "adjusted_score": adjusted, "decision": decision, "reason": reason, "earnings": e}
    if decision == "BLOCK":
        try:
            v24_conn_execute(
                "INSERT INTO earnings_blocked_signals (created_at, symbol, side, base_score, adjusted_score, reason, earnings_date, days_to_earnings, risk_level, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (v25_now_th(), payload["symbol"], payload["side"], base, adjusted, reason, e.get("earnings_date"), e.get("days_to_earnings"), e.get("risk_level"), json.dumps(payload, ensure_ascii=False)[:8000])
            )
        except Exception as ex:
            print("v25_2 save blocked error", ex)
    return payload


def v25_2_earnings_calendar(symbols=None):
    if symbols is None:
        symbols = ["NVDA", "AAPL", "TSLA", "AMD", "MSFT", "META", "AMZN", "GOOGL", "AVGO", "PLTR"]
    out = []
    for s in symbols:
        try:
            out.append(v25_2_earnings_lookup(s))
        except Exception as e:
            out.append({"ok": False, "symbol": s, "error": str(e)})
    return out


def v25_2_dashboard_html():
    symbol = request.args.get("symbol") or "NVDA"
    risk = v25_2_adjust_for_earnings(symbol, request.args.get("score") or 91, request.args.get("side") or "CALL")
    cal = v25_2_earnings_calendar()
    events = []
    blocked = []
    try:
        events = v24_conn_execute("SELECT created_at, symbol, earnings_date, session, days_to_earnings, risk_level, action, score_adjustment, position_size_factor, source FROM earnings_events ORDER BY id DESC LIMIT 40", fetch="all") or []
        blocked = v24_conn_execute("SELECT created_at, symbol, side, base_score, adjusted_score, reason, earnings_date, days_to_earnings, risk_level FROM earnings_blocked_signals ORDER BY id DESC LIMIT 25", fetch="all") or []
    except Exception:
        pass
    def html_table(rows):
        if not rows:
            return "<p>No records yet.</p>"
        keys = list(rows[0].keys())
        return "<table border='1' cellpadding='6' cellspacing='0'><tr>" + "".join(f"<th>{k}</th>" for k in keys) + "</tr>" + "".join("<tr>" + "".join(f"<td>{r.get(k)}</td>" for k in keys) + "</tr>" for r in rows) + "</table>"
    return f"""
    <html><head><meta charset='utf-8'><title>{V25_2_VERSION}</title></head>
    <body style='font-family:Arial; padding:24px;'>
      <h1>{V25_2_VERSION}</h1>
      <h2>Earnings Risk: {symbol.upper()}</h2>
      <pre>{json.dumps(risk, ensure_ascii=False, indent=2)}</pre>
      <h2>Upcoming Earnings Watchlist</h2>
      <pre>{json.dumps(cal, ensure_ascii=False, indent=2)}</pre>
      <h2>Recent Earnings Events</h2>{html_table(events)}
      <h2>Blocked Signals</h2>{html_table(blocked)}
      <p><a href='/v25/earnings/{symbol.upper()}'>Earnings JSON</a> | <a href='/v25/earnings-risk?symbol={symbol.upper()}&score=91&side=CALL'>Risk JSON</a> | <a href='/v25'>V25.1 Market Context</a></p>
    </body></html>
    """


@app.route('/v25/earnings')
def v25_2_route_earnings_calendar():
    raw = request.args.get('symbols') or ''
    symbols = [x.strip().upper() for x in raw.split(',') if x.strip()] or None
    return jsonify({"ok": True, "version": V25_2_VERSION, "calendar": v25_2_earnings_calendar(symbols)})


@app.route('/v25/earnings/<symbol>')
def v25_2_route_earnings_symbol(symbol):
    return jsonify(v25_2_earnings_lookup(symbol))


@app.route('/v25/earnings-calendar')
def v25_2_route_earnings_calendar_alias():
    return v25_2_route_earnings_calendar()


@app.route('/v25/earnings-risk')
def v25_2_route_earnings_risk():
    return jsonify(v25_2_adjust_for_earnings(request.args.get('symbol') or 'NVDA', request.args.get('score') or 91, request.args.get('side') or 'CALL'))


@app.route('/v25/earnings-dashboard')
def v25_2_route_dashboard():
    return Response(v25_2_dashboard_html(), mimetype='text/html')


try:
    v25_2_init_db()
except Exception as e:
    print('v25.2 init warning:', e)

# ============================================================
# END V25.2 EARNINGS INTELLIGENCE ENGINE
# ============================================================



# ============================================================
# V25.3 OPTION FLOW INTELLIGENCE ENGINE
# Free-data implementation using yfinance option-chain snapshots.
# Adds Put/Call Ratio, Open Interest magnet levels, unusual-volume proxy,
# Flow Score, database persistence, dashboard, and alert filter hooks.
# ============================================================

V25_3_VERSION = "V25.3 Option Flow Intelligence"

# Symbols where option-flow scoring is meaningful. Gold/Thai stocks are excluded.
V25_3_OPTION_SYMBOLS = [
    x.strip().upper()
    for x in os.getenv(
        "V25_3_OPTION_SYMBOLS",
        "NVDA,AAPL,MSFT,AMZN,META,GOOGL,GOOG,TSLA,AMD,AVGO,PLTR,TSM,QQQ,SPY,IWM,SOXL,TQQQ,NFLX,MRVL,CRDO,HOOD,SMCI,COIN,MSTR,ARM,INTC"
    ).split(",")
    if x.strip()
]

V25_3_MIN_FLOW_SCORE = int(os.getenv("V25_3_MIN_FLOW_SCORE", "80"))
V25_3_MIN_TECHNICAL_SCORE = int(os.getenv("V25_3_MIN_TECHNICAL_SCORE", "85"))
V25_3_CHAIN_EXPIRY_INDEX = int(os.getenv("V25_3_CHAIN_EXPIRY_INDEX", "0"))


def v25_3_now_iso():
    try:
        return datetime.now(timezone.utc).isoformat()
    except Exception:
        return datetime.utcnow().isoformat()


def v25_3_num(x, default=0.0):
    try:
        if x is None or x == "":
            return default
        return float(str(x).replace(",", "").strip())
    except Exception:
        return default


def v25_3_init_db():
    """Create V25.3 option-flow tables. Works with the existing db adapter."""
    v24_conn_execute("""
        CREATE TABLE IF NOT EXISTS option_flow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            expiration TEXT,
            call_volume REAL DEFAULT 0,
            put_volume REAL DEFAULT 0,
            put_call_ratio REAL DEFAULT 0,
            bullish_score REAL DEFAULT 0,
            bearish_score REAL DEFAULT 0,
            option_flow_score REAL DEFAULT 0,
            flow_bias TEXT,
            technical_score REAL DEFAULT 0,
            final_score REAL DEFAULT 0,
            source TEXT DEFAULT 'yfinance',
            notes TEXT
        )
    """)
    v24_conn_execute("""
        CREATE TABLE IF NOT EXISTS option_oi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            expiration TEXT,
            contract_type TEXT,
            strike REAL,
            open_interest REAL DEFAULT 0,
            volume REAL DEFAULT 0,
            last_price REAL,
            implied_volatility REAL,
            oi_rank INTEGER DEFAULT 0,
            magnet_level REAL,
            source TEXT DEFAULT 'yfinance'
        )
    """)
    v24_conn_execute("""
        CREATE TABLE IF NOT EXISTS option_unusual_volume (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            expiration TEXT,
            contract_type TEXT,
            strike REAL,
            volume REAL DEFAULT 0,
            open_interest REAL DEFAULT 0,
            unusual_ratio REAL DEFAULT 0,
            direction TEXT,
            source TEXT DEFAULT 'yfinance'
        )
    """)
    v24_conn_execute("""
        CREATE TABLE IF NOT EXISTS option_flow_alert_filter (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            technical_score REAL,
            flow_score REAL,
            final_score REAL,
            passed INTEGER DEFAULT 0,
            reason TEXT,
            side TEXT,
            risk_grade TEXT
        )
    """)


def v25_3_safe_option_rows(df, contract_type):
    rows = []
    if df is None:
        return rows
    try:
        records = df.to_dict("records")
    except Exception:
        return rows
    for r in records:
        strike = v25_3_num(r.get("strike"))
        volume = v25_3_num(r.get("volume"))
        oi = v25_3_num(r.get("openInterest"))
        last_price = v25_3_num(r.get("lastPrice"))
        iv = v25_3_num(r.get("impliedVolatility"))
        rows.append({
            "contract_type": contract_type,
            "strike": strike,
            "volume": volume,
            "open_interest": oi,
            "last_price": last_price,
            "implied_volatility": iv,
            "contract_symbol": r.get("contractSymbol"),
        })
    return rows


def v25_3_fetch_option_chain(symbol, expiry_index=None):
    """Fetch current option chain using yfinance.

    Note: free sources usually do not provide full historical average option volume,
    so unusual volume is calculated as a conservative proxy from current volume vs OI
    and chain median volume.
    """
    symbol = str(symbol or "NVDA").upper().strip()
    expiry_index = V25_3_CHAIN_EXPIRY_INDEX if expiry_index is None else int(expiry_index)
    t = yf.Ticker(symbol)
    expirations = list(getattr(t, "options", []) or [])
    if not expirations:
        raise RuntimeError(f"No option expirations found for {symbol}")
    expiry_index = max(0, min(expiry_index, len(expirations) - 1))
    expiration = expirations[expiry_index]
    chain = t.option_chain(expiration)
    calls = v25_3_safe_option_rows(getattr(chain, "calls", None), "CALL")
    puts = v25_3_safe_option_rows(getattr(chain, "puts", None), "PUT")
    return {
        "ok": True,
        "symbol": symbol,
        "expiration": expiration,
        "expirations": expirations[:12],
        "calls": calls,
        "puts": puts,
        "source": "yfinance",
    }


def v25_3_calculate_flow(symbol, technical_score=0, side="CALL", expiry_index=None):
    symbol = str(symbol or "NVDA").upper().strip()
    technical_score = v25_3_num(technical_score, 0)
    side = str(side or "CALL").upper()
    chain = v25_3_fetch_option_chain(symbol, expiry_index)
    calls = chain["calls"]
    puts = chain["puts"]
    expiration = chain["expiration"]

    call_volume = sum(v25_3_num(x.get("volume")) for x in calls)
    put_volume = sum(v25_3_num(x.get("volume")) for x in puts)
    pcr = (put_volume / call_volume) if call_volume > 0 else 9.99

    all_rows = calls + puts
    sorted_oi = sorted(all_rows, key=lambda x: v25_3_num(x.get("open_interest")), reverse=True)
    top_oi = sorted_oi[:20]
    magnet = top_oi[0]["strike"] if top_oi else None

    vols = sorted([v25_3_num(x.get("volume")) for x in all_rows if v25_3_num(x.get("volume")) > 0])
    median_vol = vols[len(vols)//2] if vols else 1.0
    unusual = []
    for row in all_rows:
        vol = v25_3_num(row.get("volume"))
        oi = v25_3_num(row.get("open_interest"))
        if vol <= 0:
            continue
        # Conservative free-data unusual proxy:
        # 1) current volume vs chain median volume
        # 2) current volume vs 10% of OI, avoiding false positives on tiny OI
        ratio_vs_median = vol / max(median_vol, 1.0)
        ratio_vs_oi = vol / max(oi * 0.10, 1.0)
        unusual_ratio = round(max(ratio_vs_median, ratio_vs_oi), 2)
        if unusual_ratio >= 3.0:
            unusual.append({**row, "unusual_ratio": unusual_ratio})

    unusual = sorted(unusual, key=lambda x: v25_3_num(x.get("unusual_ratio")), reverse=True)[:25]
    max_unusual = v25_3_num(unusual[0].get("unusual_ratio")) if unusual else 0.0
    top_call_oi = max([v25_3_num(x.get("open_interest")) for x in calls] or [0])
    top_put_oi = max([v25_3_num(x.get("open_interest")) for x in puts] or [0])
    oi_total = sum(v25_3_num(x.get("open_interest")) for x in all_rows)
    oi_concentration = (v25_3_num(top_oi[0].get("open_interest")) / oi_total * 100.0) if top_oi and oi_total else 0.0

    bullish_score = 50.0
    bearish_score = 50.0
    notes = []

    # Put/Call Ratio interpretation
    if pcr < 0.70:
        bullish_score += 18
        bearish_score -= 10
        notes.append("PCR < 0.70: call demand leads / bullish flow")
    elif pcr > 1.20:
        bearish_score += 18
        bullish_score -= 10
        notes.append("PCR > 1.20: put demand leads / bearish flow")
    else:
        notes.append("PCR neutral")

    # OI concentration / magnet
    if oi_concentration >= 12:
        bullish_score += 5
        bearish_score += 5
        notes.append("High OI concentration: magnet level detected")

    if top_call_oi > top_put_oi * 1.2:
        bullish_score += 8
        notes.append("Call OI leads put OI")
    elif top_put_oi > top_call_oi * 1.2:
        bearish_score += 8
        notes.append("Put OI leads call OI")

    # Unusual option volume
    call_unusual = sum(1 for x in unusual if x.get("contract_type") == "CALL")
    put_unusual = sum(1 for x in unusual if x.get("contract_type") == "PUT")
    if max_unusual >= 5:
        if call_unusual > put_unusual:
            bullish_score += 14
            notes.append(f"Unusual call volume detected ({max_unusual}x proxy)")
        elif put_unusual > call_unusual:
            bearish_score += 14
            notes.append(f"Unusual put volume detected ({max_unusual}x proxy)")
        else:
            bullish_score += 5
            bearish_score += 5
            notes.append(f"Unusual mixed option volume detected ({max_unusual}x proxy)")

    flow_bias = "BULLISH" if bullish_score > bearish_score + 5 else "BEARISH" if bearish_score > bullish_score + 5 else "MIXED"
    if side.startswith("PUT"):
        option_flow_score = bearish_score
    elif side.startswith("CALL"):
        option_flow_score = bullish_score
    else:
        option_flow_score = max(bullish_score, bearish_score)

    option_flow_score = int(max(0, min(100, round(option_flow_score))))
    final_score = int(round((technical_score * 0.65) + (option_flow_score * 0.35))) if technical_score else option_flow_score

    created_at = v25_3_now_iso()

    # Persist snapshots
    try:
        v24_conn_execute("""
            INSERT INTO option_flow
            (created_at, symbol, expiration, call_volume, put_volume, put_call_ratio, bullish_score, bearish_score,
             option_flow_score, flow_bias, technical_score, final_score, source, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (created_at, symbol, expiration, call_volume, put_volume, pcr, bullish_score, bearish_score,
              option_flow_score, flow_bias, technical_score, final_score, "yfinance", "; ".join(notes)[:1000]))

        for rank, row in enumerate(top_oi[:20], start=1):
            v24_conn_execute("""
                INSERT INTO option_oi
                (created_at, symbol, expiration, contract_type, strike, open_interest, volume, last_price,
                 implied_volatility, oi_rank, magnet_level, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (created_at, symbol, expiration, row.get("contract_type"), row.get("strike"), row.get("open_interest"),
                  row.get("volume"), row.get("last_price"), row.get("implied_volatility"), rank, magnet, "yfinance"))

        for row in unusual[:25]:
            v24_conn_execute("""
                INSERT INTO option_unusual_volume
                (created_at, symbol, expiration, contract_type, strike, volume, open_interest, unusual_ratio, direction, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (created_at, symbol, expiration, row.get("contract_type"), row.get("strike"), row.get("volume"),
                  row.get("open_interest"), row.get("unusual_ratio"), row.get("contract_type"), "yfinance"))
    except Exception as e:
        print("v25.3 option flow persist warning:", e)

    return {
        "ok": True,
        "version": V25_3_VERSION,
        "symbol": symbol,
        "expiration": expiration,
        "call_volume": int(call_volume),
        "put_volume": int(put_volume),
        "put_call_ratio": round(pcr, 3),
        "pcr_interpretation": "BULLISH" if pcr < 0.70 else "BEARISH" if pcr > 1.20 else "NEUTRAL",
        "top_oi": top_oi[:10],
        "magnet_level": magnet,
        "oi_concentration_pct": round(oi_concentration, 2),
        "unusual_volume": unusual[:10],
        "max_unusual_ratio": max_unusual,
        "bullish_score": round(bullish_score, 2),
        "bearish_score": round(bearish_score, 2),
        "option_flow_score": option_flow_score,
        "flow_bias": flow_bias,
        "technical_score": technical_score,
        "final_score": final_score,
        "notes": notes,
        "source": "yfinance",
        "free_data_warning": "Unusual volume uses current-chain proxy because free APIs may not provide historical option-volume averages.",
    }


def v25_3_alert_filter(symbol, technical_score, side="CALL", risk_grade="B", market_context_pass=True):
    """Return send/block decision using Technical Score + Option Flow Score."""
    symbol = str(symbol or "NVDA").upper().strip()
    side = str(side or "CALL").upper()
    risk_grade = str(risk_grade or "B").upper()
    technical_score = v25_3_num(technical_score, 0)

    reasons = []
    passed = True
    flow = None

    if technical_score < V25_3_MIN_TECHNICAL_SCORE:
        passed = False
        reasons.append(f"Technical Score ต่ำกว่า {V25_3_MIN_TECHNICAL_SCORE}")

    if risk_grade not in {"A", "B", "B+"}:
        passed = False
        reasons.append("Risk Grade ไม่ผ่าน")

    if not market_context_pass:
        passed = False
        reasons.append("Market Context ไม่ผ่าน")

    try:
        flow = v25_3_calculate_flow(symbol, technical_score, side)
        if v25_3_num(flow.get("option_flow_score")) < V25_3_MIN_FLOW_SCORE:
            passed = False
            reasons.append(f"Flow Score ต่ำกว่า {V25_3_MIN_FLOW_SCORE}")
    except Exception as e:
        passed = False
        reasons.append(f"Option Flow unavailable: {e}")

    final_score = flow.get("final_score") if isinstance(flow, dict) else technical_score
    if passed:
        reasons.append("PASS: Technical + Flow + Risk + Context ผ่าน")

    try:
        v24_conn_execute("""
            INSERT INTO option_flow_alert_filter
            (created_at, symbol, technical_score, flow_score, final_score, passed, reason, side, risk_grade)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (v25_3_now_iso(), symbol, technical_score,
              flow.get("option_flow_score") if isinstance(flow, dict) else None,
              final_score, 1 if passed else 0, "; ".join(reasons)[:1000], side, risk_grade))
    except Exception as e:
        print("v25.3 alert filter persist warning:", e)

    return {
        "ok": True,
        "version": V25_3_VERSION,
        "symbol": symbol,
        "side": side,
        "risk_grade": risk_grade,
        "technical_score": technical_score,
        "flow_score": flow.get("option_flow_score") if isinstance(flow, dict) else None,
        "final_score": final_score,
        "passed": passed,
        "reasons": reasons,
        "flow": flow,
    }


def v25_3_recent(table, limit=50):
    allowed = {"option_flow", "option_oi", "option_unusual_volume", "option_flow_alert_filter"}
    if table not in allowed:
        return []
    try:
        return v24_conn_execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (int(limit),), fetch="all") or []
    except Exception:
        return []


def v25_3_dashboard_html():
    flows = v25_3_recent("option_flow", 30)
    unusual = v25_3_recent("option_unusual_volume", 30)
    oi = v25_3_recent("option_oi", 30)
    filters = v25_3_recent("option_flow_alert_filter", 30)

    def html_table(rows):
        if not rows:
            return "<p>No records yet.</p>"
        keys = list(rows[0].keys())
        return "<table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse;font-size:13px;'><tr>" + "".join(f"<th>{k}</th>" for k in keys) + "</tr>" + "".join("<tr>" + "".join(f"<td>{r.get(k)}</td>" for k in keys) + "</tr>" for r in rows) + "</table>"

    return f"""
    <html><head><meta charset='utf-8'><title>{V25_3_VERSION}</title></head>
    <body style='font-family:Arial; padding:24px;'>
      <h1>{V25_3_VERSION}</h1>
      <p>Put/Call Ratio · Open Interest Magnet · Unusual Volume Proxy · Flow Score</p>
      <h2>Quick Test</h2>
      <ul>
        <li><a href='/v25/flow/NVDA?score=88&side=CALL'>NVDA Flow</a></li>
        <li><a href='/v25/flow-alert?symbol=NVDA&technical_score=88&side=CALL&risk_grade=A'>Flow Alert Filter</a></li>
      </ul>
      <h2>Top Option Flow</h2>{html_table(flows)}
      <h2>Highest Unusual Volume</h2>{html_table(unusual)}
      <h2>Highest OI / Magnet Levels</h2>{html_table(oi)}
      <h2>Flow Alert Decisions</h2>{html_table(filters)}
    </body></html>
    """


@app.route('/v25/flow')
def v25_3_route_flow_list():
    raw = request.args.get("symbols") or "NVDA,AAPL,TSLA,AMD,QQQ,SPY"
    symbols = [x.strip().upper() for x in raw.split(",") if x.strip()]
    out = []
    for sym in symbols[:20]:
        try:
            out.append(v25_3_calculate_flow(sym, request.args.get("score") or 0, request.args.get("side") or "CALL"))
        except Exception as e:
            out.append({"ok": False, "symbol": sym, "error": str(e)})
    return jsonify({"ok": True, "version": V25_3_VERSION, "results": out})


@app.route('/v25/flow/<symbol>')
def v25_3_route_flow_symbol(symbol):
    return jsonify(v25_3_calculate_flow(symbol, request.args.get("score") or 0, request.args.get("side") or "CALL"))


@app.route('/v25/oi')
def v25_3_route_oi():
    return jsonify({"ok": True, "version": V25_3_VERSION, "rows": v25_3_recent("option_oi", request.args.get("limit") or 50)})


@app.route('/v25/unusual-volume')
def v25_3_route_unusual():
    return jsonify({"ok": True, "version": V25_3_VERSION, "rows": v25_3_recent("option_unusual_volume", request.args.get("limit") or 50)})


@app.route('/v25/flow-score')
def v25_3_route_flow_score():
    symbol = request.args.get("symbol") or "NVDA"
    return jsonify(v25_3_calculate_flow(symbol, request.args.get("score") or 0, request.args.get("side") or "CALL"))


@app.route('/v25/flow-alert')
def v25_3_route_flow_alert():
    return jsonify(v25_3_alert_filter(
        request.args.get("symbol") or "NVDA",
        request.args.get("technical_score") or request.args.get("score") or 88,
        request.args.get("side") or "CALL",
        request.args.get("risk_grade") or "A",
        str(request.args.get("market_context_pass", "true")).lower() not in {"0", "false", "no"}
    ))


@app.route('/v25/flow-dashboard')
def v25_3_route_dashboard():
    return Response(v25_3_dashboard_html(), mimetype='text/html')


try:
    v25_3_init_db()
except Exception as e:
    print('v25.3 init warning:', e)

# ============================================================
# END V25.3 OPTION FLOW INTELLIGENCE ENGINE
# ============================================================

# ============================================================
# V25.4 CORRELATION MATRIX + THEME SELECTION ENGINE
# ============================================================
V25_4_VERSION = "V25.4 Correlation Matrix + Theme Selection"

V25_4_THEME_MAP = {
    # Mega cap / AI / semis
    "NVDA": "Semiconductor", "AMD": "Semiconductor", "AVGO": "Semiconductor", "TSM": "Semiconductor",
    "MRVL": "Semiconductor", "AMKR": "Semiconductor", "INTC": "Semiconductor", "MU": "Semiconductor",
    "SMCI": "AI Infrastructure", "PLTR": "AI Software", "CRWV": "AI Infrastructure", "NBIS": "AI Infrastructure",
    "MSFT": "Mega Cap Tech", "AAPL": "Mega Cap Tech", "AMZN": "Mega Cap Tech", "META": "Mega Cap Tech",
    "GOOG": "Mega Cap Tech", "GOOGL": "Mega Cap Tech", "NFLX": "Mega Cap Tech",
    # Growth / momentum
    "TSLA": "EV Growth", "RBLX": "Growth", "SHOP": "Growth", "HOOD": "Fintech",
    # Space / defense
    "RKLB": "Space Defense", "ASTS": "Space Defense", "AVAV": "Defense Drone", "KTOS": "Defense Drone",
    # Energy / nuclear / uranium
    "OKLO": "Nuclear Energy", "CEG": "Power Energy", "VST": "Power Energy", "LEU": "Uranium", "UUUU": "Uranium",
    # Crypto / quantum
    "COIN": "Crypto", "MSTR": "Crypto", "IREN": "Crypto", "CIFR": "Crypto",
    "IONQ": "Quantum", "RGTI": "Quantum", "QBTS": "Quantum", "QUBT": "Quantum",
    # ETFs
    "QQQ": "ETF Tech", "SPY": "ETF Broad", "IWM": "ETF Small Cap", "TQQQ": "ETF Leveraged", "SOXL": "ETF Leveraged Semi",
    # Gold
    "GOLD": "Gold", "XAUUSD": "Gold", "XAU/USD": "Gold",
}

V25_4_DEFAULT_UNIVERSE = [
    "NVDA","AMD","AVGO","TSM","MRVL","AMKR","INTC","MU","SMCI","PLTR","CRWV","NBIS",
    "AAPL","MSFT","AMZN","META","GOOGL","GOOG","TSLA","NFLX","QQQ","SPY","IWM",
    "RKLB","ASTS","OKLO","CEG","VST","LEU","UUUU","IONQ","RGTI","QBTS","COIN","MSTR","HOOD","GOLD"
]


def v25_4_now_iso():
    return datetime.now(timezone.utc).isoformat()


def v25_4_sector(symbol):
    sym = str(symbol or "").upper().replace(".BK", "")
    return V25_4_THEME_MAP.get(sym, "Other")


def v25_4_float(x, default=0.0):
    try:
        if x is None or x == "":
            return default
        return float(str(x).replace(",", "").strip())
    except Exception:
        return default


def v25_4_init_db():
    v24_conn_execute("""
        CREATE TABLE IF NOT EXISTS correlation_matrix (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            symbol_a TEXT NOT NULL,
            symbol_b TEXT NOT NULL,
            theme_a TEXT,
            theme_b TEXT,
            correlation REAL,
            lookback_days INTEGER,
            source TEXT DEFAULT 'yfinance'
        )
    """)
    v24_conn_execute("""
        CREATE TABLE IF NOT EXISTS correlation_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            group_name TEXT,
            selected_symbol TEXT,
            rejected_symbols TEXT,
            reason TEXT,
            selected_score REAL,
            selected_flow_score REAL,
            avg_correlation REAL,
            portfolio_quality_score REAL
        )
    """)
    v24_conn_execute("""
        CREATE TABLE IF NOT EXISTS v25_4_signal_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            theme TEXT,
            technical_score REAL,
            flow_score REAL,
            news_score REAL,
            risk_grade TEXT,
            side TEXT,
            final_score REAL,
            quality_score REAL,
            rank_in_theme INTEGER,
            selected INTEGER DEFAULT 0,
            reject_reason TEXT
        )
    """)


def v25_4_price_series(symbol, period="3mo", interval="1d"):
    sym = str(symbol or "").upper().strip()
    if sym in {"GOLD", "XAUUSD", "XAU/USD"}:
        yf_symbol = "GC=F"
    else:
        yf_symbol = sym
    try:
        data = yf.Ticker(yf_symbol).history(period=period, interval=interval, auto_adjust=False)
        if data is None or data.empty or "Close" not in data.columns:
            return []
        vals = [float(x) for x in data["Close"].dropna().tolist()]
        return vals[-80:]
    except Exception:
        return []


def v25_4_returns(values):
    out = []
    for i in range(1, len(values)):
        prev = values[i-1]
        cur = values[i]
        if prev:
            out.append((cur - prev) / prev)
    return out


def v25_4_corr(xs, ys):
    n = min(len(xs), len(ys))
    if n < 10:
        return None
    xs = xs[-n:]
    ys = ys[-n:]
    mx = sum(xs) / n
    my = sum(ys) / n
    vx = sum((x-mx)**2 for x in xs)
    vy = sum((y-my)**2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    cov = sum((xs[i]-mx)*(ys[i]-my) for i in range(n))
    return round(cov / ((vx * vy) ** 0.5), 4)


def v25_4_build_matrix(symbols=None, lookback_days=60):
    symbols = [str(s).upper().strip() for s in (symbols or V25_4_DEFAULT_UNIVERSE) if str(s).strip()]
    symbols = list(dict.fromkeys(symbols))[:80]
    series = {s: v25_4_returns(v25_4_price_series(s)) for s in symbols}
    rows = []
    now = v25_4_now_iso()
    for i, a in enumerate(symbols):
        for b in symbols[i+1:]:
            c = v25_4_corr(series.get(a, []), series.get(b, []))
            if c is None:
                continue
            row = {"symbol_a": a, "symbol_b": b, "theme_a": v25_4_sector(a), "theme_b": v25_4_sector(b), "correlation": c}
            rows.append(row)
            try:
                v24_conn_execute("""
                    INSERT INTO correlation_matrix
                    (created_at, symbol_a, symbol_b, theme_a, theme_b, correlation, lookback_days, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (now, a, b, row["theme_a"], row["theme_b"], c, int(lookback_days), "yfinance"))
            except Exception as e:
                print("v25.4 correlation insert warning:", e)
    rows.sort(key=lambda x: abs(v25_4_float(x.get("correlation"))), reverse=True)
    return {"ok": True, "version": V25_4_VERSION, "count": len(rows), "rows": rows[:500]}


def v25_4_recent_correlations(limit=100):
    try:
        return v24_conn_execute("SELECT * FROM correlation_matrix ORDER BY id DESC LIMIT ?", (int(limit),), fetch="all") or []
    except Exception:
        return []


def v25_4_pair_correlation(symbol_a, symbol_b):
    a = str(symbol_a or "").upper().strip()
    b = str(symbol_b or "").upper().strip()
    ar = v25_4_returns(v25_4_price_series(a))
    br = v25_4_returns(v25_4_price_series(b))
    c = v25_4_corr(ar, br)
    return {"ok": c is not None, "symbol_a": a, "symbol_b": b, "correlation": c, "theme_a": v25_4_sector(a), "theme_b": v25_4_sector(b)}


def v25_4_quality_score(candidate):
    technical = v25_4_float(candidate.get("technical_score") or candidate.get("score"), 0)
    flow = v25_4_float(candidate.get("flow_score"), 50)
    news = v25_4_float(candidate.get("news_score"), 50)
    risk = str(candidate.get("risk_grade") or "C").upper()
    side = str(candidate.get("side") or "CALL").upper()
    grade_bonus = {"A": 10, "A+": 12, "B+": 6, "B": 4, "C+": 0, "C": -5, "D": -12}.get(risk, -4)
    side_bonus = 2 if side in {"CALL", "PUT"} else 0
    q = technical * 0.48 + flow * 0.32 + news * 0.12 + 50 * 0.08 + grade_bonus + side_bonus
    return round(max(0, min(100, q)), 2)


def v25_4_parse_candidates_from_query():
    raw = request.args.get("candidates") or ""
    out = []
    if raw:
        # Format: NVDA:91:88:A:CALL,AMD:87:82:B:CALL
        for item in raw.split(","):
            parts = [p.strip() for p in item.split(":")]
            if not parts or not parts[0]:
                continue
            out.append({
                "symbol": parts[0].upper(),
                "technical_score": v25_4_float(parts[1], 85) if len(parts) > 1 else 85,
                "flow_score": v25_4_float(parts[2], 75) if len(parts) > 2 else 75,
                "risk_grade": parts[3].upper() if len(parts) > 3 else "B",
                "side": parts[4].upper() if len(parts) > 4 else "CALL",
                "news_score": v25_4_float(parts[5], 50) if len(parts) > 5 else 50,
            })
    if not out:
        symbols = [x.strip().upper() for x in (request.args.get("symbols") or "NVDA,AMD,AVGO,TSM").split(",") if x.strip()]
        for s in symbols:
            out.append({"symbol": s, "technical_score": 88, "flow_score": 80, "risk_grade": "B", "side": "CALL", "news_score": 55})
    return out


def v25_4_select_best_candidate(candidates, correlation_threshold=0.75, max_per_theme=1):
    prepared = []
    for c in candidates:
        item = dict(c)
        item["symbol"] = str(item.get("symbol") or "").upper().strip()
        item["theme"] = v25_4_sector(item["symbol"])
        item["quality_score"] = v25_4_quality_score(item)
        prepared.append(item)

    prepared.sort(key=lambda x: x.get("quality_score", 0), reverse=True)
    selected = []
    rejected = []
    theme_counts = {}
    pair_cache = {}

    for cand in prepared:
        sym = cand["symbol"]
        theme = cand["theme"]
        reason = None
        if theme_counts.get(theme, 0) >= int(max_per_theme):
            reason = f"Theme cap: already selected best candidate in {theme}"
        else:
            for s in selected:
                key = tuple(sorted([sym, s["symbol"]]))
                if key not in pair_cache:
                    pair_cache[key] = v25_4_pair_correlation(key[0], key[1]).get("correlation")
                corr = pair_cache.get(key)
                if corr is not None and corr >= float(correlation_threshold):
                    reason = f"High correlation with selected {s['symbol']} ({corr})"
                    break
        if reason:
            cand["selected"] = 0
            cand["reject_reason"] = reason
            rejected.append(cand)
        else:
            cand["selected"] = 1
            cand["reject_reason"] = ""
            selected.append(cand)
            theme_counts[theme] = theme_counts.get(theme, 0) + 1

    # Store candidates and high-level decision.
    now = v25_4_now_iso()
    try:
        for rank, c in enumerate(selected + rejected, start=1):
            v24_conn_execute("""
                INSERT INTO v25_4_signal_candidates
                (created_at, symbol, theme, technical_score, flow_score, news_score, risk_grade, side, final_score, quality_score, rank_in_theme, selected, reject_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (now, c.get("symbol"), c.get("theme"), v25_4_float(c.get("technical_score")), v25_4_float(c.get("flow_score")),
                  v25_4_float(c.get("news_score")), c.get("risk_grade"), c.get("side"), v25_4_float(c.get("final_score") or c.get("technical_score")),
                  v25_4_float(c.get("quality_score")), rank, int(c.get("selected") or 0), c.get("reject_reason") or ""))
        avg_corr = 0.0
        corr_vals = []
        for i, a in enumerate(selected):
            for b in selected[i+1:]:
                val = v25_4_pair_correlation(a["symbol"], b["symbol"]).get("correlation")
                if val is not None:
                    corr_vals.append(val)
        if corr_vals:
            avg_corr = round(sum(corr_vals) / len(corr_vals), 4)
        portfolio_quality = round(sum(v25_4_float(x.get("quality_score")) for x in selected) / max(1, len(selected)), 2)
        v24_conn_execute("""
            INSERT INTO correlation_decisions
            (created_at, group_name, selected_symbol, rejected_symbols, reason, selected_score, selected_flow_score, avg_correlation, portfolio_quality_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (now, "theme_selection", ",".join(x.get("symbol") for x in selected), ",".join(x.get("symbol") for x in rejected),
              "Best-of-theme + correlation suppression", v25_4_float(selected[0].get("technical_score")) if selected else 0,
              v25_4_float(selected[0].get("flow_score")) if selected else 0, avg_corr, portfolio_quality))
    except Exception as e:
        print("v25.4 decision persist warning:", e)

    return {
        "ok": True,
        "version": V25_4_VERSION,
        "correlation_threshold": float(correlation_threshold),
        "max_per_theme": int(max_per_theme),
        "selected": selected,
        "rejected": rejected,
        "summary": {
            "selected_count": len(selected),
            "rejected_count": len(rejected),
            "themes_selected": sorted(set(x.get("theme") for x in selected)),
            "portfolio_quality_score": round(sum(v25_4_float(x.get("quality_score")) for x in selected) / max(1, len(selected)), 2),
        }
    }


def v25_4_should_send_alert(candidate, current_candidates=None):
    result = v25_4_select_best_candidate(current_candidates or [candidate])
    selected_symbols = {x.get("symbol") for x in result.get("selected", [])}
    sym = str(candidate.get("symbol") or "").upper()
    return {"ok": True, "symbol": sym, "send": sym in selected_symbols, "decision": result}


def v25_4_recent(table, limit=50):
    allowed = {"correlation_matrix", "correlation_decisions", "v25_4_signal_candidates"}
    if table not in allowed:
        return []
    try:
        return v24_conn_execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (int(limit),), fetch="all") or []
    except Exception:
        return []


def v25_4_dashboard_html():
    corr = v25_4_recent("correlation_matrix", 60)
    decisions = v25_4_recent("correlation_decisions", 30)
    candidates = v25_4_recent("v25_4_signal_candidates", 60)
    def html_table(rows):
        if not rows:
            return "<p>No records yet.</p>"
        keys = list(rows[0].keys())
        return "<table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse;font-size:13px;'><tr>" + "".join(f"<th>{k}</th>" for k in keys) + "</tr>" + "".join("<tr>" + "".join(f"<td>{r.get(k)}</td>" for k in keys) + "</tr>" for r in rows) + "</table>"
    return f"""
    <html><head><meta charset='utf-8'><title>{V25_4_VERSION}</title></head>
    <body style='font-family:Arial; padding:24px;'>
      <h1>{V25_4_VERSION}</h1>
      <p>Correlation Matrix · Best-of-Theme Selection · Sector Exposure Control · Redundant Alert Suppression</p>
      <h2>Quick Test</h2>
      <ul>
        <li><a href='/v25/correlation/build?symbols=NVDA,AMD,AVGO,TSM'>Build NVDA/AMD/AVGO/TSM Matrix</a></li>
        <li><a href='/v25/theme-select?candidates=NVDA:91:88:A:CALL,AMD:88:82:B:CALL,AVGO:86:80:B:CALL,TSM:84:78:B:CALL'>Theme Select Test</a></li>
        <li><a href='/v25/correlation/NVDA/AMD'>NVDA vs AMD Correlation</a></li>
      </ul>
      <h2>Correlation Decisions</h2>{html_table(decisions)}
      <h2>Signal Candidates</h2>{html_table(candidates)}
      <h2>Recent Correlation Matrix</h2>{html_table(corr)}
    </body></html>
    """


@app.route('/v25/correlation/build')
def v25_4_route_build_corr():
    raw = request.args.get("symbols") or ",".join(V25_4_DEFAULT_UNIVERSE[:20])
    symbols = [x.strip().upper() for x in raw.split(",") if x.strip()]
    return jsonify(v25_4_build_matrix(symbols, request.args.get("lookback_days") or 60))


@app.route('/v25/correlation/<symbol_a>/<symbol_b>')
def v25_4_route_pair_corr(symbol_a, symbol_b):
    return jsonify(v25_4_pair_correlation(symbol_a, symbol_b))


@app.route('/v25/theme-select')
def v25_4_route_theme_select():
    candidates = v25_4_parse_candidates_from_query()
    return jsonify(v25_4_select_best_candidate(
        candidates,
        request.args.get("correlation_threshold") or 0.75,
        request.args.get("max_per_theme") or 1,
    ))


@app.route('/v25/alert-portfolio-gate')
def v25_4_route_alert_portfolio_gate():
    candidates = v25_4_parse_candidates_from_query()
    candidate = candidates[0] if candidates else {"symbol": "NVDA"}
    return jsonify(v25_4_should_send_alert(candidate, candidates))


@app.route('/v25/correlation-matrix')
def v25_4_route_recent_matrix():
    return jsonify({"ok": True, "version": V25_4_VERSION, "rows": v25_4_recent("correlation_matrix", request.args.get("limit") or 100)})


@app.route('/v25/correlation-dashboard')
def v25_4_route_dashboard():
    return Response(v25_4_dashboard_html(), mimetype='text/html')


try:
    v25_4_init_db()
except Exception as e:
    print('v25.4 init warning:', e)

# ============================================================
# END V25.4 CORRELATION MATRIX + THEME SELECTION ENGINE
# ============================================================


# ============================================================
# V25.5 TRADE QUALITY PREDICTION ENGINE
# Predictive quality gate before sending alerts:
# - Predicted Win Rate
# - Expected Return (R)
# - Expected Drawdown (R)
# - Historical Similarity
# This module is additive and does not remove legacy engines.
# ============================================================
V25_5_VERSION = "V25.5 Trade Quality Prediction Engine"
V25_5_MIN_WIN_RATE = float(os.getenv("V25_5_MIN_WIN_RATE", "58"))
V25_5_MIN_EXPECTED_R = float(os.getenv("V25_5_MIN_EXPECTED_R", "0.15"))
V25_5_MIN_SIMILARITY = float(os.getenv("V25_5_MIN_SIMILARITY", "45"))
V25_5_MIN_QUALITY_SCORE = float(os.getenv("V25_5_MIN_QUALITY_SCORE", "70"))


def v25_5_float(x, default=0.0):
    try:
        if x is None or x == "":
            return default
        return float(str(x).replace(",", "").strip())
    except Exception:
        return default


def v25_5_text(x, default=""):
    try:
        if x is None:
            return default
        return str(x).strip()
    except Exception:
        return default


def v25_5_init_db():
    v24_conn_execute("""
        CREATE TABLE IF NOT EXISTS trade_quality_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT,
            strategy TEXT,
            technical_score REAL,
            flow_score REAL,
            context_score REAL,
            risk_grade TEXT,
            predicted_win_rate REAL,
            expected_return_r REAL,
            expected_drawdown_r REAL,
            historical_similarity REAL,
            quality_score REAL,
            quality_grade TEXT,
            decision TEXT,
            reasons TEXT,
            sample_size INTEGER DEFAULT 0
        )
    """)
    v24_conn_execute("""
        CREATE TABLE IF NOT EXISTS trade_quality_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            prediction_id INTEGER,
            symbol TEXT NOT NULL,
            side TEXT,
            entry REAL,
            tp1 REAL,
            tp2 REAL,
            sl REAL,
            outcome TEXT,
            realized_r REAL,
            notes TEXT
        )
    """)


def v25_5_grade_to_num(grade):
    g = v25_5_text(grade, "C").upper()
    if g == "A+": return 95
    if g == "A": return 90
    if g == "B+": return 82
    if g == "B": return 75
    if g == "C+": return 65
    if g == "C": return 55
    if g == "D": return 40
    return 50


def v25_5_quality_grade(score):
    s = v25_5_float(score)
    if s >= 88: return "A"
    if s >= 80: return "B+"
    if s >= 72: return "B"
    if s >= 62: return "C+"
    if s >= 52: return "C"
    return "D"


def v25_5_load_historical(symbol=None, side=None, strategy=None, limit=400):
    """Best-effort historical sample loader.
    Works even if older tables do not exist. It tries known V23/V24/V25 tables first.
    """
    candidates = []
    queries = [
        ("trade_quality_outcomes", "SELECT symbol, side, outcome, realized_r, notes FROM trade_quality_outcomes ORDER BY id DESC LIMIT ?"),
        ("performance_signals", "SELECT symbol, side, outcome, realized_r, strategy FROM performance_signals ORDER BY id DESC LIMIT ?"),
        ("alert_journal", "SELECT symbol, side, outcome, realized_r, strategy FROM alert_journal ORDER BY id DESC LIMIT ?"),
        ("signals", "SELECT symbol, signal_type as side, score, probability, report FROM signals ORDER BY id DESC LIMIT ?"),
    ]
    for table, sql in queries:
        try:
            rows = v24_conn_execute(sql, (int(limit),), fetch="all") or []
            for r in rows:
                d = dict(r)
                d["_source_table"] = table
                candidates.append(d)
        except Exception:
            pass
    if symbol:
        sym = symbol.upper()
        candidates = [r for r in candidates if v25_5_text(r.get("symbol")).upper() == sym or not r.get("symbol")]
    if side:
        sd = side.upper()
        candidates = [r for r in candidates if sd in v25_5_text(r.get("side")).upper() or not r.get("side")]
    if strategy:
        st = strategy.upper()
        candidates = [r for r in candidates if st in v25_5_text(r.get("strategy")).upper() or not r.get("strategy")]
    return candidates[:limit]


def v25_5_historical_stats(symbol=None, side=None, strategy=None):
    rows = v25_5_load_historical(symbol, side, strategy)
    wins = losses = breakeven = 0
    r_values = []
    usable = 0
    for r in rows:
        outcome = v25_5_text(r.get("outcome") or r.get("result") or "").upper()
        rr = r.get("realized_r") if r.get("realized_r") is not None else r.get("r_multiple")
        rr = v25_5_float(rr, None)
        if rr is not None:
            usable += 1
            r_values.append(rr)
            if rr > 0: wins += 1
            elif rr < 0: losses += 1
            else: breakeven += 1
        elif outcome:
            usable += 1
            if any(x in outcome for x in ["TP", "WIN", "PROFIT"]):
                wins += 1; r_values.append(1.0)
            elif any(x in outcome for x in ["SL", "LOSS", "LOSE"]):
                losses += 1; r_values.append(-1.0)
            else:
                breakeven += 1; r_values.append(0.0)
    sample = usable
    if sample <= 0:
        return {"sample_size": 0, "win_rate": None, "avg_win_r": 1.30, "avg_loss_r": -1.00, "expectancy_r": None, "profit_factor": None}
    win_rate = wins / sample * 100.0
    win_rs = [x for x in r_values if x > 0]
    loss_rs = [x for x in r_values if x < 0]
    avg_win = sum(win_rs)/len(win_rs) if win_rs else 1.30
    avg_loss = sum(loss_rs)/len(loss_rs) if loss_rs else -1.00
    gross_win = sum(win_rs)
    gross_loss = abs(sum(loss_rs))
    pf = gross_win / gross_loss if gross_loss else (gross_win if gross_win else None)
    exp = sum(r_values)/sample if sample else None
    return {"sample_size": sample, "win_rate": round(win_rate,2), "avg_win_r": round(avg_win,3), "avg_loss_r": round(avg_loss,3), "expectancy_r": round(exp,3) if exp is not None else None, "profit_factor": round(pf,3) if pf is not None else None}


def v25_5_predict_trade_quality(symbol, side="CALL", strategy="UNKNOWN", technical_score=50, flow_score=50, context_score=50, risk_grade="C", market_regime="UNKNOWN", rvol=None, rsi=None):
    symbol = v25_5_text(symbol, "UNKNOWN").upper()
    side = v25_5_text(side, "CALL").upper()
    strategy = v25_5_text(strategy, "UNKNOWN").upper()
    technical_score = v25_5_float(technical_score, 50)
    flow_score = v25_5_float(flow_score, 50)
    context_score = v25_5_float(context_score, 50)
    risk_num = v25_5_grade_to_num(risk_grade)
    rvol = v25_5_float(rvol, None)
    rsi = v25_5_float(rsi, None)
    hist = v25_5_historical_stats(symbol, side, strategy)

    # Historical similarity blends available sample size with quality of matching dimensions.
    sample = int(hist.get("sample_size") or 0)
    sample_factor = min(35, sample * 2.5)
    symbol_factor = 18 if sample >= 5 else 8 if sample > 0 else 0
    strategy_factor = 14 if strategy not in {"", "UNKNOWN", "MANUAL"} and sample >= 5 else 5 if strategy not in {"", "UNKNOWN"} else 0
    score_factor = max(0, 20 - abs(technical_score - 80) * 0.4) if technical_score >= 70 else max(0, technical_score - 50) * 0.25
    historical_similarity = max(0, min(100, sample_factor + symbol_factor + strategy_factor + score_factor))

    # Predicted win rate: conservative blend of model components + actual history if available.
    model_wr = 50
    model_wr += (technical_score - 50) * 0.28
    model_wr += (flow_score - 50) * 0.18
    model_wr += (context_score - 50) * 0.12
    model_wr += (risk_num - 50) * 0.08
    if rvol is not None and rvol >= 1.5: model_wr += 3
    if rvol is not None and rvol < 1.0: model_wr -= 4
    if rsi is not None and rsi >= 72: model_wr -= 6
    if "RANGE" in v25_5_text(market_regime).upper(): model_wr -= 3
    if "DOWNTREND" in v25_5_text(market_regime).upper() and side.startswith("CALL"): model_wr -= 6
    if "UPTREND" in v25_5_text(market_regime).upper() and side.startswith("PUT"): model_wr -= 6

    hist_wr = hist.get("win_rate")
    if hist_wr is not None and sample >= 10:
        hist_weight = min(0.55, sample / 100.0)
        predicted_wr = model_wr * (1 - hist_weight) + hist_wr * hist_weight
    elif hist_wr is not None and sample > 0:
        predicted_wr = model_wr * 0.82 + hist_wr * 0.18
    else:
        predicted_wr = model_wr
    predicted_wr = max(35, min(78, predicted_wr))

    avg_win = v25_5_float(hist.get("avg_win_r"), 1.30)
    avg_loss = abs(v25_5_float(hist.get("avg_loss_r"), -1.00))
    p = predicted_wr / 100.0
    expected_return_r = p * avg_win - (1-p) * avg_loss
    # Expected drawdown proxy for a 5-signal cluster, intentionally conservative.
    expected_drawdown_r = -abs((1-p) * avg_loss * 2.2)

    quality_score = 0.0
    quality_score += predicted_wr * 0.42
    quality_score += max(0, min(100, (expected_return_r + 1.0) * 50)) * 0.24
    quality_score += historical_similarity * 0.18
    quality_score += risk_num * 0.10
    quality_score += max(0, min(100, flow_score)) * 0.06
    quality_score = max(0, min(100, quality_score))
    grade = v25_5_quality_grade(quality_score)

    reasons = []
    decision = "PASS"
    if predicted_wr < V25_5_MIN_WIN_RATE:
        decision = "REJECT"
        reasons.append(f"Predicted Win Rate ต่ำกว่า {V25_5_MIN_WIN_RATE}%")
    if expected_return_r < V25_5_MIN_EXPECTED_R:
        decision = "REJECT"
        reasons.append(f"Expected Return ต่ำกว่า {V25_5_MIN_EXPECTED_R}R")
    if historical_similarity < V25_5_MIN_SIMILARITY:
        # Not always a hard reject when model is very strong, but warn.
        reasons.append("Historical Similarity ยังต่ำ/ข้อมูลย้อนหลังไม่พอ")
        if quality_score < 82:
            decision = "REJECT"
    if quality_score < V25_5_MIN_QUALITY_SCORE:
        decision = "REJECT"
        reasons.append(f"Quality Score ต่ำกว่า {V25_5_MIN_QUALITY_SCORE}")
    if not reasons:
        reasons.append("Trade Quality ผ่านเกณฑ์: Win Rate/Expected Return/Similarity เหมาะสม")

    result = {
        "ok": True,
        "version": V25_5_VERSION,
        "symbol": symbol,
        "side": side,
        "strategy": strategy,
        "technical_score": round(technical_score, 2),
        "flow_score": round(flow_score, 2),
        "context_score": round(context_score, 2),
        "risk_grade": v25_5_text(risk_grade, "C"),
        "predicted_win_rate": round(predicted_wr, 2),
        "expected_return_r": round(expected_return_r, 3),
        "expected_drawdown_r": round(expected_drawdown_r, 3),
        "historical_similarity": round(historical_similarity, 2),
        "quality_score": round(quality_score, 2),
        "quality_grade": grade,
        "decision": decision,
        "reasons": reasons,
        "historical_stats": hist,
    }
    try:
        v24_conn_execute("""
            INSERT INTO trade_quality_predictions
            (created_at, symbol, side, strategy, technical_score, flow_score, context_score, risk_grade,
             predicted_win_rate, expected_return_r, expected_drawdown_r, historical_similarity,
             quality_score, quality_grade, decision, reasons, sample_size)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (now_text(), symbol, side, strategy, technical_score, flow_score, context_score, v25_5_text(risk_grade, "C"),
              result["predicted_win_rate"], result["expected_return_r"], result["expected_drawdown_r"], result["historical_similarity"],
              result["quality_score"], result["quality_grade"], result["decision"], json.dumps(reasons, ensure_ascii=False), sample))
    except Exception as e:
        print("v25.5 persist warning:", e)
    return result


def v25_5_recent_predictions(limit=50):
    try:
        return v24_conn_execute("SELECT * FROM trade_quality_predictions ORDER BY id DESC LIMIT ?", (int(limit),), fetch="all") or []
    except Exception:
        return []


def v25_5_dashboard_html():
    rows = v25_5_recent_predictions(80)
    passed = [r for r in rows if v25_5_text(r.get("decision")).upper() == "PASS"]
    rejected = [r for r in rows if v25_5_text(r.get("decision")).upper() != "PASS"]
    def table(rs):
        if not rs:
            return "<p>No records yet.</p>"
        keys = ["created_at","symbol","side","strategy","technical_score","flow_score","context_score","predicted_win_rate","expected_return_r","expected_drawdown_r","historical_similarity","quality_score","quality_grade","decision","sample_size"]
        return "<table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse;font-size:13px;'><tr>" + "".join(f"<th>{k}</th>" for k in keys) + "</tr>" + "".join("<tr>" + "".join(f"<td>{r.get(k)}</td>" for k in keys) + "</tr>" for r in rs) + "</table>"
    return f"""
    <html><head><meta charset='utf-8'><title>{V25_5_VERSION}</title></head>
    <body style='font-family:Arial; padding:24px;'>
      <h1>{V25_5_VERSION}</h1>
      <p>เปลี่ยนจาก "มีสัญญาณ" เป็น "สัญญาณนี้มีโอกาสทำเงินจริงแค่ไหน"</p>
      <h2>Quick Test</h2>
      <ul>
        <li><a href='/v25/trade-quality/NVDA?score=91&flow_score=88&context_score=82&risk_grade=A&side=CALL&strategy=BREAKOUT&rvol=2.1&rsi=64&regime=UPTREND'>NVDA Quality Test</a></li>
        <li><a href='/v25/trade-quality/AAPL?score=84&flow_score=52&context_score=70&risk_grade=B&side=CALL&strategy=PULLBACK&rvol=1.2&rsi=70&regime=RANGE'>AAPL Quality Test</a></li>
      </ul>
      <h2>Passed Predictions</h2>{table(passed)}
      <h2>Rejected Predictions</h2>{table(rejected)}
    </body></html>
    """


@app.route('/v25/trade-quality/<symbol>')
def v25_5_route_trade_quality(symbol):
    return jsonify(v25_5_predict_trade_quality(
        symbol=symbol,
        side=request.args.get("side") or "CALL",
        strategy=request.args.get("strategy") or "UNKNOWN",
        technical_score=request.args.get("score") or request.args.get("technical_score") or 50,
        flow_score=request.args.get("flow_score") or 50,
        context_score=request.args.get("context_score") or 50,
        risk_grade=request.args.get("risk_grade") or "C",
        market_regime=request.args.get("regime") or "UNKNOWN",
        rvol=request.args.get("rvol"),
        rsi=request.args.get("rsi"),
    ))


@app.route('/v25/trade-quality-gate')
def v25_5_route_trade_quality_gate():
    symbol = request.args.get("symbol") or "NVDA"
    return jsonify(v25_5_predict_trade_quality(
        symbol=symbol,
        side=request.args.get("side") or "CALL",
        strategy=request.args.get("strategy") or "UNKNOWN",
        technical_score=request.args.get("score") or request.args.get("technical_score") or 50,
        flow_score=request.args.get("flow_score") or 50,
        context_score=request.args.get("context_score") or 50,
        risk_grade=request.args.get("risk_grade") or "C",
        market_regime=request.args.get("regime") or "UNKNOWN",
        rvol=request.args.get("rvol"),
        rsi=request.args.get("rsi"),
    ))


@app.route('/v25/trade-quality/recent')
def v25_5_route_recent():
    return jsonify({"ok": True, "version": V25_5_VERSION, "rows": v25_5_recent_predictions(request.args.get("limit") or 100)})


@app.route('/v25/trade-quality-dashboard')
def v25_5_route_dashboard():
    return Response(v25_5_dashboard_html(), mimetype='text/html')


try:
    v25_5_init_db()
except Exception as e:
    print('v25.5 init warning:', e)

# ============================================================
# END V25.5 TRADE QUALITY PREDICTION ENGINE
# ============================================================

# ============================================================
# V26.0 PROFESSIONAL EXECUTION INTELLIGENCE SUITE
# V26.1 Real Options Chain Intelligence
# V26.2 Liquidity Engine
# V26.3 Regime Switching AI
# V26.4 Position Management AI
# V26.5 Portfolio Simulation
# Appended without removing previous V25.x engines.
# ============================================================
V26_VERSION = "V26.0 Professional Execution Intelligence Suite"


def v26_float(x, default=0.0):
    try:
        if x is None or x == "":
            return default
        return float(str(x).replace(",", "").strip())
    except Exception:
        return default


def v26_int(x, default=0):
    try:
        if x is None or x == "":
            return default
        return int(float(str(x).replace(",", "").strip()))
    except Exception:
        return default


def v26_text(x, default=""):
    try:
        s = str(x if x is not None else default).strip()
        return s if s else default
    except Exception:
        return default


def v26_now():
    try:
        return now_text()
    except Exception:
        return (datetime.now(timezone.utc) + timedelta(hours=7)).strftime("%d/%m/%Y %H:%M")


def v26_init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS v26_options_chain_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            expiration TEXT,
            underlying_price REAL,
            call_volume REAL,
            put_volume REAL,
            put_call_ratio REAL,
            call_oi REAL,
            put_oi REAL,
            max_call_oi_strike REAL,
            max_call_oi REAL,
            max_put_oi_strike REAL,
            max_put_oi REAL,
            call_wall REAL,
            put_wall REAL,
            zero_gamma_proxy REAL,
            flow_score REAL,
            bias TEXT,
            notes TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS v26_liquidity_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            vix REAL,
            dxy REAL,
            us10y REAL,
            spy_price REAL,
            qqq_price REAL,
            liquidity_score REAL,
            risk_mode TEXT,
            notes TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS v26_regime_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            symbol TEXT,
            base_regime TEXT,
            volatility_state TEXT,
            liquidity_state TEXT,
            final_regime TEXT,
            score_adjustment REAL,
            model_profile TEXT,
            notes TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS v26_position_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            symbol TEXT,
            side TEXT,
            entry REAL,
            stop_loss REAL,
            tp1 REAL,
            tp2 REAL,
            tp3 REAL,
            trailing_stop REAL,
            scale_out_plan TEXT,
            risk_per_unit REAL,
            reward_r REAL,
            position_size REAL,
            notes TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS v26_portfolio_simulations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            candidates TEXT,
            selected TEXT,
            rejected TEXT,
            total_risk_pct REAL,
            sector_exposure TEXT,
            correlation_warning TEXT,
            portfolio_score REAL,
            notes TEXT
        )
    """)
    conn.commit()
    conn.close()


def v26_recent(table, limit=50):
    allowed = {
        "v26_options_chain_snapshots", "v26_liquidity_snapshots", "v26_regime_snapshots",
        "v26_position_plans", "v26_portfolio_simulations"
    }
    if table not in allowed:
        return []
    try:
        conn = db()
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (v26_int(limit, 50),)).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        return [{"error": str(e)}]


def v26_get_last_close(symbol, period="1y"):
    try:
        t = yf.Ticker(symbol)
        data = t.history(period=period, interval="1d", auto_adjust=False)
        if data is None or data.empty:
            return None, []
        closes = [float(x) for x in data["Close"].dropna().tolist()]
        return closes[-1] if closes else None, closes
    except Exception:
        return None, []


def v26_ema(values, period):
    try:
        return ema(values, period)
    except Exception:
        if len(values) < period:
            return None
        k = 2 / (period + 1)
        out = values[0]
        for p in values[1:]:
            out = p * k + out * (1-k)
        return out


def v26_real_options_chain(symbol, expiration=None):
    """Use real option chain fields available from yfinance: volume and openInterest.
    Greeks/GEX are not reliably free; GEX/zero-gamma are represented as transparent proxies.
    """
    symbol = v26_text(symbol, "NVDA").upper()
    result = {"ok": False, "version": V26_VERSION, "symbol": symbol}
    try:
        ticker = yf.Ticker(symbol)
        expirations = list(getattr(ticker, "options", []) or [])
        if not expirations:
            raise RuntimeError("No options expirations available from yfinance")
        exp = expiration or expirations[0]
        chain = ticker.option_chain(exp)
        calls = chain.calls.copy()
        puts = chain.puts.copy()
        underlying, _ = v26_get_last_close(symbol, "1mo")
        if underlying is None:
            try:
                underlying = v26_float(ticker.fast_info.get("last_price"), None)
            except Exception:
                underlying = None

        def colsum(df, col):
            try:
                return float(df[col].fillna(0).sum())
            except Exception:
                return 0.0

        call_vol = colsum(calls, "volume")
        put_vol = colsum(puts, "volume")
        call_oi = colsum(calls, "openInterest")
        put_oi = colsum(puts, "openInterest")
        pcr = round(put_vol / call_vol, 4) if call_vol else None

        max_call_strike = max_call_oi = max_put_strike = max_put_oi = None
        if "openInterest" in calls.columns and not calls.empty:
            row = calls.sort_values("openInterest", ascending=False).iloc[0]
            max_call_strike = v26_float(row.get("strike"), None)
            max_call_oi = v26_float(row.get("openInterest"), None)
        if "openInterest" in puts.columns and not puts.empty:
            row = puts.sort_values("openInterest", ascending=False).iloc[0]
            max_put_strike = v26_float(row.get("strike"), None)
            max_put_oi = v26_float(row.get("openInterest"), None)

        # Transparent proxy: weighted OI magnet; not true dealer gamma.
        call_wall = max_call_strike
        put_wall = max_put_strike
        if max_call_strike and max_put_strike:
            zero_gamma_proxy = round((max_call_strike + max_put_strike) / 2.0, 2)
        else:
            zero_gamma_proxy = None

        score = 50
        notes = []
        bias = "NEUTRAL"
        if pcr is not None:
            if pcr < 0.70:
                score += 16; bias = "BULLISH"; notes.append("PCR < 0.70: call demand stronger")
            elif pcr > 1.20:
                score -= 16; bias = "BEARISH"; notes.append("PCR > 1.20: put demand stronger")
            else:
                notes.append("PCR neutral")
        total_vol = call_vol + put_vol
        total_oi = call_oi + put_oi
        if total_vol >= 50000:
            score += 8; notes.append("High option volume")
        elif total_vol >= 15000:
            score += 4; notes.append("Moderate option volume")
        if total_oi >= 100000:
            score += 8; notes.append("High OI liquidity")
        elif total_oi >= 30000:
            score += 4; notes.append("Moderate OI liquidity")
        if underlying and call_wall and put_wall:
            if underlying > call_wall:
                score += 5; notes.append("Underlying above call wall proxy")
            elif underlying < put_wall:
                score -= 5; notes.append("Underlying below put wall proxy")
        flow_score = int(max(0, min(100, score)))

        result.update({
            "ok": True,
            "expiration": exp,
            "available_expirations": expirations[:8],
            "underlying_price": underlying,
            "call_volume": call_vol,
            "put_volume": put_vol,
            "put_call_ratio": pcr,
            "call_open_interest": call_oi,
            "put_open_interest": put_oi,
            "max_call_oi_strike": max_call_strike,
            "max_call_oi": max_call_oi,
            "max_put_oi_strike": max_put_strike,
            "max_put_oi": max_put_oi,
            "call_wall": call_wall,
            "put_wall": put_wall,
            "zero_gamma_proxy": zero_gamma_proxy,
            "flow_score": flow_score,
            "bias": bias,
            "notes": notes,
            "warning": "Uses real yfinance option volume/OI. Greeks/GEX are proxy estimates, not dealer-grade paid gamma data."
        })
        try:
            conn = db()
            conn.execute("""
                INSERT INTO v26_options_chain_snapshots
                (created_at, symbol, expiration, underlying_price, call_volume, put_volume, put_call_ratio,
                 call_oi, put_oi, max_call_oi_strike, max_call_oi, max_put_oi_strike, max_put_oi,
                 call_wall, put_wall, zero_gamma_proxy, flow_score, bias, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (v26_now(), symbol, exp, underlying, call_vol, put_vol, pcr, call_oi, put_oi,
                  max_call_strike, max_call_oi, max_put_strike, max_put_oi, call_wall, put_wall,
                  zero_gamma_proxy, flow_score, bias, json.dumps(notes, ensure_ascii=False)))
            conn.commit(); conn.close()
        except Exception as e:
            result["db_warning"] = str(e)
        return result
    except Exception as e:
        result["error"] = str(e)
        return result


def v26_liquidity_engine():
    def close(sym):
        p, _ = v26_get_last_close(sym, "6mo")
        return p
    vix = close("^VIX")
    dxy = close("DX-Y.NYB") or close("UUP")
    us10y = close("^TNX")
    spy = close("SPY")
    qqq = close("QQQ")
    score = 50
    notes = []
    if vix is not None:
        if vix > 30:
            score -= 22; notes.append("VIX > 30: panic/high volatility")
        elif vix > 25:
            score -= 14; notes.append("VIX > 25: reduce CALL risk")
        elif vix < 16:
            score += 8; notes.append("VIX calm")
    if dxy is not None:
        # DXY around >105 often tightens conditions for gold/risk assets.
        if dxy > 105:
            score -= 8; notes.append("DXY strong: pressure on gold/risk assets")
        elif dxy < 102:
            score += 4; notes.append("DXY soft")
    if us10y is not None:
        if us10y > 4.7:
            score -= 12; notes.append("US10Y elevated: pressure on growth/tech")
        elif us10y < 4.1:
            score += 5; notes.append("US10Y supportive")
    risk_mode = "RISK_ON" if score >= 60 else "RISK_OFF" if score <= 40 else "NEUTRAL"
    out = {"ok": True, "version": V26_VERSION, "vix": vix, "dxy": dxy, "us10y": us10y, "spy_price": spy, "qqq_price": qqq,
           "liquidity_score": int(max(0, min(100, score))), "risk_mode": risk_mode, "notes": notes}
    try:
        conn = db()
        conn.execute("""
            INSERT INTO v26_liquidity_snapshots
            (created_at, vix, dxy, us10y, spy_price, qqq_price, liquidity_score, risk_mode, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (v26_now(), vix, dxy, us10y, spy, qqq, out["liquidity_score"], risk_mode, json.dumps(notes, ensure_ascii=False)))
        conn.commit(); conn.close()
    except Exception as e:
        out["db_warning"] = str(e)
    return out


def v26_spy_ema200_context():
    price, closes = v26_get_last_close("SPY", "2y")
    e200 = v26_ema(closes, 200) if closes else None
    state = "UNKNOWN"
    if price and e200:
        state = "ABOVE_EMA200" if price > e200 else "BELOW_EMA200"
    return {"spy_price": price, "spy_ema200": e200, "state": state}


def v26_regime_switching_ai(symbol="SPY", base_score=50, side="CALL"):
    symbol = v26_text(symbol, "SPY").upper()
    base_score = v26_float(base_score, 50)
    side = v26_text(side, "CALL").upper()
    price, closes = v26_get_last_close(symbol, "1y")
    e50 = v26_ema(closes, 50) if closes else None
    e200 = v26_ema(closes, 200) if closes else None
    vix_data = v26_liquidity_engine()
    vix = v26_float(vix_data.get("vix"), None)
    liq_score = v26_float(vix_data.get("liquidity_score"), 50)
    volatility_state = "NORMAL"
    if vix is not None:
        if vix >= 30: volatility_state = "PANIC"
        elif vix >= 25: volatility_state = "VOL_EXPANSION"
        elif vix <= 15: volatility_state = "VOL_COMPRESSION"
    trend_state = "UNKNOWN"
    if price and e50 and e200:
        if price > e50 > e200: trend_state = "TREND_UP"
        elif price < e50 < e200: trend_state = "TREND_DOWN"
        else: trend_state = "RANGE_TRANSITION"
    final_regime = trend_state
    if volatility_state == "PANIC":
        final_regime = "PANIC"
    elif volatility_state == "VOL_EXPANSION" and "TREND" not in trend_state:
        final_regime = "VOLATILITY_EXPANSION"
    elif volatility_state == "VOL_COMPRESSION":
        final_regime = "VOLATILITY_COMPRESSION"

    adj = 0
    model_profile = "BALANCED"
    if final_regime == "TREND_UP":
        model_profile = "MOMENTUM_BREAKOUT"; adj += 8 if side.startswith("CALL") else -8
    elif final_regime == "TREND_DOWN":
        model_profile = "DEFENSIVE_PUT_OR_AVOID"; adj += 8 if side.startswith("PUT") else -10
    elif final_regime == "PANIC":
        model_profile = "RISK_OFF_CAPITAL_PRESERVATION"; adj -= 18
    elif final_regime == "VOLATILITY_EXPANSION":
        model_profile = "WIDER_STOPS_SMALLER_SIZE"; adj -= 8
    elif final_regime == "VOLATILITY_COMPRESSION":
        model_profile = "RANGE_OR_BREAKOUT_WAIT"; adj -= 4
    if liq_score < 40:
        adj -= 8
    elif liq_score > 60:
        adj += 4
    adjusted = int(max(0, min(100, base_score + adj)))
    notes = [f"trend={trend_state}", f"volatility={volatility_state}", f"liquidity={vix_data.get('risk_mode')}", f"profile={model_profile}"]
    out = {"ok": True, "version": V26_VERSION, "symbol": symbol, "base_score": base_score, "adjusted_score": adjusted,
           "score_adjustment": adj, "base_regime": trend_state, "volatility_state": volatility_state,
           "liquidity_state": vix_data.get("risk_mode"), "final_regime": final_regime,
           "model_profile": model_profile, "notes": notes}
    try:
        conn = db()
        conn.execute("""
            INSERT INTO v26_regime_snapshots
            (created_at, symbol, base_regime, volatility_state, liquidity_state, final_regime, score_adjustment, model_profile, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (v26_now(), symbol, trend_state, volatility_state, vix_data.get("risk_mode"), final_regime, adj, model_profile, json.dumps(notes, ensure_ascii=False)))
        conn.commit(); conn.close()
    except Exception as e:
        out["db_warning"] = str(e)
    return out


def v26_position_management_ai(symbol, side="CALL", entry=None, atr=None, score=50, quality_score=50, account_equity=10000, risk_pct=1.0):
    symbol = v26_text(symbol, "UNKNOWN").upper()
    side = v26_text(side, "CALL").upper()
    entry = v26_float(entry, None)
    if entry is None or entry <= 0:
        entry, _ = v26_get_last_close(symbol, "1mo")
    if not entry:
        return {"ok": False, "error": "entry or market price required", "symbol": symbol}
    atr = v26_float(atr, None)
    if not atr or atr <= 0:
        _, closes = v26_get_last_close(symbol, "3mo")
        if closes and len(closes) > 15:
            # lightweight ATR proxy from close-to-close range
            diffs = [abs(closes[i]-closes[i-1]) for i in range(1, len(closes))]
            atr = sum(diffs[-14:]) / 14
        else:
            atr = max(entry * 0.015, 0.01)
    score = v26_float(score, 50); quality_score = v26_float(quality_score, 50)
    if side.startswith("PUT"):
        sl = entry + atr * (1.1 if quality_score >= 80 else 0.9)
        tp1 = entry - atr * 0.9
        tp2 = entry - atr * 1.6
        tp3 = entry - atr * 2.4
        trailing = entry + atr * 0.75
    else:
        sl = entry - atr * (1.1 if quality_score >= 80 else 0.9)
        tp1 = entry + atr * 0.9
        tp2 = entry + atr * 1.6
        tp3 = entry + atr * 2.4
        trailing = entry - atr * 0.75
    risk_per_unit = abs(entry - sl)
    risk_cash = v26_float(account_equity, 10000) * v26_float(risk_pct, 1.0) / 100.0
    if quality_score < 70:
        risk_cash *= 0.5
    if score < 80:
        risk_cash *= 0.5
    size = int(risk_cash / risk_per_unit) if risk_per_unit > 0 else 0
    reward_r = abs(tp2 - entry) / risk_per_unit if risk_per_unit else 0
    scale_plan = "TP1 sell 30%, TP2 sell 40%, TP3/trailing keep 30%"
    notes = []
    if quality_score >= 85: notes.append("High quality: normal size")
    elif quality_score >= 70: notes.append("Medium quality: reduced size")
    else: notes.append("Low quality: half size or avoid")
    out = {"ok": True, "version": V26_VERSION, "symbol": symbol, "side": side, "entry": round(entry, 4),
           "stop_loss": round(sl, 4), "tp1": round(tp1, 4), "tp2": round(tp2, 4), "tp3": round(tp3, 4),
           "trailing_stop": round(trailing, 4), "scale_out_plan": scale_plan,
           "risk_per_unit": round(risk_per_unit, 4), "reward_r_to_tp2": round(reward_r, 2),
           "position_size": size, "risk_cash": round(risk_cash, 2), "notes": notes}
    try:
        conn = db()
        conn.execute("""
            INSERT INTO v26_position_plans
            (created_at, symbol, side, entry, stop_loss, tp1, tp2, tp3, trailing_stop, scale_out_plan, risk_per_unit, reward_r, position_size, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (v26_now(), symbol, side, entry, sl, tp1, tp2, tp3, trailing, scale_plan, risk_per_unit, reward_r, size, json.dumps(notes, ensure_ascii=False)))
        conn.commit(); conn.close()
    except Exception as e:
        out["db_warning"] = str(e)
    return out


V26_SECTOR_MAP = {
    "NVDA":"SEMICONDUCTOR", "AMD":"SEMICONDUCTOR", "AVGO":"SEMICONDUCTOR", "TSM":"SEMICONDUCTOR", "MRVL":"SEMICONDUCTOR", "AMKR":"SEMICONDUCTOR", "INTC":"SEMICONDUCTOR",
    "AAPL":"MEGA_CAP_TECH", "MSFT":"MEGA_CAP_TECH", "GOOGL":"MEGA_CAP_TECH", "GOOG":"MEGA_CAP_TECH", "META":"MEGA_CAP_TECH", "AMZN":"MEGA_CAP_TECH",
    "TSLA":"EV_HIGH_BETA", "PLTR":"AI_SOFTWARE", "CRWV":"AI_INFRA", "AVAV":"AEROSPACE", "RKLB":"SPACE", "ASTS":"SPACE", "OKLO":"NUCLEAR", "CEG":"ENERGY", "VST":"ENERGY", "LEU":"URANIUM", "UUUU":"URANIUM",
    "QQQ":"ETF", "SPY":"ETF", "IWM":"ETF", "GOLD":"GOLD", "XAUUSD":"GOLD"
}


def v26_parse_candidates(raw):
    # Format: NVDA:92:A:CALL:SEMICONDUCTOR,AMD:88:B:CALL:SEMICONDUCTOR
    candidates = []
    for part in v26_text(raw).split(","):
        p = [x.strip() for x in part.split(":")]
        if not p or not p[0]:
            continue
        sym = p[0].upper()
        score = v26_float(p[1], 50) if len(p) > 1 else 50
        grade = p[2].upper() if len(p) > 2 else "C"
        side = p[3].upper() if len(p) > 3 else "CALL"
        sector = p[4].upper() if len(p) > 4 else V26_SECTOR_MAP.get(sym, "OTHER")
        candidates.append({"symbol": sym, "score": score, "grade": grade, "side": side, "sector": sector})
    return candidates


def v26_portfolio_simulation(candidates_raw=None, max_per_sector=1, max_total=3):
    candidates = v26_parse_candidates(candidates_raw or "NVDA:92:A:CALL:SEMICONDUCTOR,AMD:88:B:CALL:SEMICONDUCTOR,TSM:86:B:CALL:SEMICONDUCTOR,AAPL:84:B:CALL:MEGA_CAP_TECH,GOLD:82:B:CALL:GOLD")
    # Add quality proxies from V25.5 if available.
    enriched = []
    for c in candidates:
        quality = c["score"]
        try:
            pred = v25_5_predict_trade_quality(c["symbol"], c["side"], "V26_PORTFOLIO", c["score"], 70, 70, c["grade"])
            quality = v26_float(pred.get("quality_score"), c["score"])
            c["predicted_win_rate"] = pred.get("predicted_win_rate")
            c["quality_score"] = quality
        except Exception:
            c["quality_score"] = quality
        enriched.append(c)
    enriched.sort(key=lambda x: (v26_float(x.get("quality_score")), v26_float(x.get("score"))), reverse=True)
    selected = []
    rejected = []
    sector_count = {}
    for c in enriched:
        sector = c.get("sector") or "OTHER"
        if len(selected) >= v26_int(max_total, 3):
            c["reject_reason"] = "max_total_reached"; rejected.append(c); continue
        if sector_count.get(sector, 0) >= v26_int(max_per_sector, 1):
            c["reject_reason"] = f"sector_cap_{sector}"; rejected.append(c); continue
        selected.append(c)
        sector_count[sector] = sector_count.get(sector, 0) + 1
    portfolio_score = round(sum(v26_float(x.get("quality_score"), x.get("score")) for x in selected) / len(selected), 2) if selected else 0
    warnings = []
    if any(x.get("sector") == "SEMICONDUCTOR" for x in rejected):
        warnings.append("Semiconductor cluster detected; best-of-theme selected")
    total_risk_pct = round(len(selected) * 1.0, 2)
    out = {"ok": True, "version": V26_VERSION, "selected": selected, "rejected": rejected,
           "sector_exposure": sector_count, "total_risk_pct": total_risk_pct,
           "portfolio_score": portfolio_score, "correlation_warning": warnings,
           "rule": "Max one alert per sector/theme by default; scan many, send few."}
    try:
        conn = db()
        conn.execute("""
            INSERT INTO v26_portfolio_simulations
            (created_at, candidates, selected, rejected, total_risk_pct, sector_exposure, correlation_warning, portfolio_score, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (v26_now(), json.dumps(candidates, ensure_ascii=False), json.dumps(selected, ensure_ascii=False), json.dumps(rejected, ensure_ascii=False), total_risk_pct,
              json.dumps(sector_count, ensure_ascii=False), json.dumps(warnings, ensure_ascii=False), portfolio_score, "V26 portfolio simulation"))
        conn.commit(); conn.close()
    except Exception as e:
        out["db_warning"] = str(e)
    return out


def v26_dashboard_html():
    liquidity = v26_recent("v26_liquidity_snapshots", 5)
    option_flow = v26_recent("v26_options_chain_snapshots", 10)
    regimes = v26_recent("v26_regime_snapshots", 10)
    positions = v26_recent("v26_position_plans", 10)
    sims = v26_recent("v26_portfolio_simulations", 10)
    def table(rows):
        if not rows: return "<p>No records yet.</p>"
        keys = list(rows[0].keys())[:12]
        return "<table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse;font-size:12px;'><tr>" + ''.join(f"<th>{k}</th>" for k in keys) + "</tr>" + ''.join("<tr>" + ''.join(f"<td>{r.get(k)}</td>" for k in keys) + "</tr>" for r in rows) + "</table>"
    return f"""
    <html><head><meta charset='utf-8'><title>{V26_VERSION}</title></head>
    <body style='font-family:Arial;padding:24px;'>
      <h1>{V26_VERSION}</h1>
      <p>Execution Intelligence: Options Chain, Liquidity, Regime Switching, Position Management, Portfolio Simulation.</p>
      <h2>Quick Tests</h2>
      <ul>
        <li><a href='/v26/options-chain/NVDA'>Options Chain NVDA</a></li>
        <li><a href='/v26/liquidity'>Liquidity Engine</a></li>
        <li><a href='/v26/regime/NVDA?score=91&side=CALL'>Regime Switching NVDA</a></li>
        <li><a href='/v26/position-plan/NVDA?entry=214&side=CALL&score=90&quality_score=86'>Position Plan NVDA</a></li>
        <li><a href='/v26/portfolio-sim?candidates=NVDA:92:A:CALL:SEMICONDUCTOR,AMD:89:B:CALL:SEMICONDUCTOR,TSM:86:B:CALL:SEMICONDUCTOR,AAPL:84:B:CALL:MEGA_CAP_TECH,GOLD:82:B:CALL:GOLD'>Portfolio Simulation</a></li>
      </ul>
      <h2>Liquidity</h2>{table(liquidity)}
      <h2>Options Chain Snapshots</h2>{table(option_flow)}
      <h2>Regime Snapshots</h2>{table(regimes)}
      <h2>Position Plans</h2>{table(positions)}
      <h2>Portfolio Simulations</h2>{table(sims)}
    </body></html>
    """


@app.route('/v26')
@app.route('/v26/dashboard')
def v26_route_dashboard():
    return Response(v26_dashboard_html(), mimetype='text/html')


@app.route('/v26/options-chain/<symbol>')
def v26_route_options_chain(symbol):
    return jsonify(v26_real_options_chain(symbol, request.args.get("expiration")))


@app.route('/v26/liquidity')
def v26_route_liquidity():
    return jsonify(v26_liquidity_engine())


@app.route('/v26/spy-ema200')
def v26_route_spy_ema200():
    return jsonify({"ok": True, "version": V26_VERSION, **v26_spy_ema200_context()})


@app.route('/v26/regime/<symbol>')
def v26_route_regime(symbol):
    return jsonify(v26_regime_switching_ai(symbol, request.args.get("score") or 50, request.args.get("side") or "CALL"))


@app.route('/v26/position-plan/<symbol>')
def v26_route_position_plan(symbol):
    return jsonify(v26_position_management_ai(
        symbol=symbol,
        side=request.args.get("side") or "CALL",
        entry=request.args.get("entry"),
        atr=request.args.get("atr"),
        score=request.args.get("score") or 50,
        quality_score=request.args.get("quality_score") or 50,
        account_equity=request.args.get("equity") or 10000,
        risk_pct=request.args.get("risk_pct") or 1.0,
    ))


@app.route('/v26/portfolio-sim')
def v26_route_portfolio_sim():
    return jsonify(v26_portfolio_simulation(request.args.get("candidates"), request.args.get("max_per_sector") or 1, request.args.get("max_total") or 3))


@app.route('/v26/json')
def v26_route_json():
    return jsonify({
        "ok": True,
        "version": V26_VERSION,
        "liquidity_recent": v26_recent("v26_liquidity_snapshots", 5),
        "options_chain_recent": v26_recent("v26_options_chain_snapshots", 5),
        "regime_recent": v26_recent("v26_regime_snapshots", 5),
        "position_recent": v26_recent("v26_position_plans", 5),
        "portfolio_recent": v26_recent("v26_portfolio_simulations", 5),
    })


try:
    v26_init_db()
except Exception as e:
    print('v26 init warning:', e)

# ============================================================
# END V26.0 PROFESSIONAL EXECUTION INTELLIGENCE SUITE
# ============================================================



# ============================================================
# V26.6 TRADE DNA + CONVICTION ENGINE
# ============================================================
V26_6_VERSION = "V26.6 Trade DNA + Conviction Engine"

def v26_6_float(x, default=0.0):
    try:
        if x is None or x == "":
            return default
        return float(str(x).replace(",", "").strip())
    except Exception:
        return default

def v26_6_int(x, default=0):
    try:
        if x is None or x == "":
            return default
        return int(float(str(x).replace(",", "").strip()))
    except Exception:
        return default

def v26_6_text(x, default=""):
    try:
        if x is None:
            return default
        return str(x).strip()
    except Exception:
        return default

def v26_6_safe_json(obj):
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return "{}"

def v26_6_init_db():
    """Create V26.6 tables without disturbing legacy tables."""
    v24_conn_execute("""
        CREATE TABLE IF NOT EXISTS trade_dna_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            dna_key TEXT UNIQUE NOT NULL,
            symbol TEXT,
            sector TEXT,
            side TEXT,
            strategy TEXT,
            ema_state TEXT,
            rsi_zone TEXT,
            rvol_zone TEXT,
            market_regime TEXT,
            vix_state TEXT,
            news_state TEXT,
            flow_state TEXT,
            risk_grade TEXT,
            feature_json TEXT
        )
    """)
    v24_conn_execute("""
        CREATE TABLE IF NOT EXISTS dna_statistics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            updated_at TEXT NOT NULL,
            dna_key TEXT UNIQUE NOT NULL,
            occurrences INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            breakeven INTEGER DEFAULT 0,
            win_rate REAL DEFAULT 0,
            avg_return_r REAL DEFAULT 0,
            expected_return_r REAL DEFAULT 0,
            expected_drawdown_r REAL DEFAULT 0,
            profit_factor REAL DEFAULT 0,
            sample_quality TEXT,
            source TEXT
        )
    """)
    v24_conn_execute("""
        CREATE TABLE IF NOT EXISTS conviction_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT,
            sector TEXT,
            dna_key TEXT,
            technical_score REAL,
            flow_score REAL,
            context_score REAL,
            quality_score REAL,
            dna_win_rate REAL,
            expected_return_r REAL,
            expected_drawdown_r REAL,
            historical_similarity REAL,
            conviction_score REAL,
            conviction_grade TEXT,
            decision TEXT,
            reasons TEXT
        )
    """)

def v26_6_zone_rsi(rsi):
    rsi = v26_6_float(rsi, None)
    if rsi is None:
        return "RSI_UNKNOWN"
    if rsi >= 75:
        return "RSI_OVERHEATED"
    if rsi >= 68:
        return "RSI_HOT"
    if rsi >= 55:
        return "RSI_BULL_MOMENTUM"
    if rsi >= 45:
        return "RSI_NEUTRAL"
    if rsi >= 35:
        return "RSI_WEAK"
    return "RSI_OVERSOLD"

def v26_6_zone_rvol(rvol):
    rvol = v26_6_float(rvol, None)
    if rvol is None:
        return "RVOL_UNKNOWN"
    if rvol >= 3:
        return "RVOL_EXPLOSIVE"
    if rvol >= 1.8:
        return "RVOL_STRONG"
    if rvol >= 1.2:
        return "RVOL_OK"
    if rvol >= 0.8:
        return "RVOL_LIGHT"
    return "RVOL_WEAK"

def v26_6_zone_score(score):
    score = v26_6_float(score, 50)
    if score >= 90:
        return "SCORE_ELITE"
    if score >= 85:
        return "SCORE_STRONG"
    if score >= 75:
        return "SCORE_GOOD"
    if score >= 60:
        return "SCORE_MEDIUM"
    return "SCORE_LOW"

def v26_6_flow_state(flow_score):
    flow_score = v26_6_float(flow_score, None)
    if flow_score is None:
        return "FLOW_UNKNOWN"
    if flow_score >= 85:
        return "FLOW_ELITE"
    if flow_score >= 75:
        return "FLOW_STRONG"
    if flow_score >= 60:
        return "FLOW_OK"
    return "FLOW_WEAK"

def v26_6_context_state(context_score):
    context_score = v26_6_float(context_score, None)
    if context_score is None:
        return "CONTEXT_UNKNOWN"
    if context_score >= 85:
        return "CONTEXT_TAILWIND"
    if context_score >= 70:
        return "CONTEXT_OK"
    if context_score >= 50:
        return "CONTEXT_MIXED"
    return "CONTEXT_HEADWIND"

def v26_6_normalize_regime(regime):
    r = v26_6_text(regime, "UNKNOWN").upper()
    if "STRONG" in r and "UP" in r:
        return "REGIME_STRONG_UPTREND"
    if "UP" in r:
        return "REGIME_UPTREND"
    if "STRONG" in r and "DOWN" in r:
        return "REGIME_STRONG_DOWNTREND"
    if "DOWN" in r:
        return "REGIME_DOWNTREND"
    if "RANGE" in r:
        return "REGIME_RANGE"
    if "PANIC" in r:
        return "REGIME_PANIC"
    return "REGIME_MIXED"

def v26_6_sector_for_symbol(symbol):
    symbol = v26_6_text(symbol).upper()
    sector_map = {
        "NVDA":"SEMICONDUCTOR", "AMD":"SEMICONDUCTOR", "AVGO":"SEMICONDUCTOR", "TSM":"SEMICONDUCTOR",
        "MRVL":"SEMICONDUCTOR", "MU":"SEMICONDUCTOR", "AMKR":"SEMICONDUCTOR", "INTC":"SEMICONDUCTOR",
        "AAPL":"MEGA_TECH", "MSFT":"MEGA_TECH", "GOOGL":"MEGA_TECH", "GOOG":"MEGA_TECH", "META":"MEGA_TECH",
        "AMZN":"MEGA_TECH", "TSLA":"EV_HIGH_BETA", "PLTR":"AI_SOFTWARE", "CRWD":"CYBERSECURITY",
        "NET":"CYBERSECURITY", "SNOW":"CLOUD_DATA", "DDOG":"CLOUD_DATA", "QQQ":"ETF_INDEX", "SPY":"ETF_INDEX",
        "IWM":"ETF_INDEX", "SOXL":"LEVERAGED_SEMI", "TQQQ":"LEVERAGED_TECH", "OKLO":"NUCLEAR_ENERGY",
        "CEG":"POWER_ENERGY", "VST":"POWER_ENERGY", "LEU":"URANIUM", "UUUU":"URANIUM",
        "RKLB":"SPACE_AEROSPACE", "ASTS":"SPACE_AEROSPACE", "AVAV":"DEFENSE_DRONE",
        "HOOD":"FINTECH_CRYPTO", "COIN":"FINTECH_CRYPTO", "MSTR":"CRYPTO_PROXY",
        "GOLD":"GOLD", "XAUUSD":"GOLD", "XAU/USD":"GOLD"
    }
    return sector_map.get(symbol, "OTHER")

def v26_6_build_dna_key(symbol, side="CALL", strategy="UNKNOWN", technical_score=50, rsi=None,
                         rvol=None, market_regime="UNKNOWN", vix_state="UNKNOWN",
                         news_state="UNKNOWN", flow_score=None, risk_grade="NA", sector=None):
    symbol = v26_6_text(symbol).upper()
    side = v26_6_text(side, "CALL").upper()
    sector = sector or v26_6_sector_for_symbol(symbol)
    features = {
        "sector": sector,
        "side": side,
        "strategy": v26_6_text(strategy, "UNKNOWN").upper(),
        "score_zone": v26_6_zone_score(technical_score),
        "rsi_zone": v26_6_zone_rsi(rsi),
        "rvol_zone": v26_6_zone_rvol(rvol),
        "regime": v26_6_normalize_regime(market_regime),
        "vix_state": v26_6_text(vix_state, "VIX_UNKNOWN").upper(),
        "news_state": v26_6_text(news_state, "NEWS_UNKNOWN").upper(),
        "flow_state": v26_6_flow_state(flow_score),
        "risk_grade": v26_6_text(risk_grade, "NA").upper(),
    }
    dna_key = "|".join([
        features["sector"], features["side"], features["strategy"], features["score_zone"],
        features["rsi_zone"], features["rvol_zone"], features["regime"], features["vix_state"],
        features["news_state"], features["flow_state"], features["risk_grade"]
    ])
    return dna_key, features

def v26_6_upsert_dna_pattern(symbol, dna_key, features):
    try:
        v24_conn_execute("""
            INSERT INTO trade_dna_patterns
            (created_at, dna_key, symbol, sector, side, strategy, ema_state, rsi_zone, rvol_zone,
             market_regime, vix_state, news_state, flow_state, risk_grade, feature_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(dna_key) DO UPDATE SET
                symbol=excluded.symbol,
                sector=excluded.sector,
                side=excluded.side,
                strategy=excluded.strategy,
                rsi_zone=excluded.rsi_zone,
                rvol_zone=excluded.rvol_zone,
                market_regime=excluded.market_regime,
                vix_state=excluded.vix_state,
                news_state=excluded.news_state,
                flow_state=excluded.flow_state,
                risk_grade=excluded.risk_grade,
                feature_json=excluded.feature_json
        """, (
            now_text(), dna_key, symbol, features.get("sector"), features.get("side"), features.get("strategy"),
            features.get("score_zone"), features.get("rsi_zone"), features.get("rvol_zone"),
            features.get("regime"), features.get("vix_state"), features.get("news_state"),
            features.get("flow_state"), features.get("risk_grade"), v26_6_safe_json(features)
        ))
    except Exception as e:
        print("v26_6_upsert_dna_pattern warning:", e)

def v26_6_query_outcome_rows(symbol=None, sector=None, strategy=None, limit=500):
    """Use available historical outcome tables. Works even if some tables do not exist."""
    rows = []
    queries = []
    # V24 quant outcomes usually store realized_r / outcome.
    queries.append(("quant_signal_outcomes", "symbol, sector, strategy, realized_r, outcome"))
    queries.append(("trade_quality_outcomes", "symbol, NULL as sector, NULL as strategy, realized_r, outcome"))
    for table, cols in queries:
        try:
            sql = f"SELECT {cols} FROM {table}"
            params = []
            cond = []
            if symbol:
                cond.append("UPPER(symbol)=?")
                params.append(v26_6_text(symbol).upper())
            if sector and table == "quant_signal_outcomes":
                cond.append("UPPER(sector)=?")
                params.append(v26_6_text(sector).upper())
            if strategy and table == "quant_signal_outcomes":
                cond.append("UPPER(strategy)=?")
                params.append(v26_6_text(strategy).upper())
            if cond:
                sql += " WHERE " + " AND ".join(cond)
            sql += " ORDER BY id DESC LIMIT ?"
            params.append(int(limit))
            part = v24_conn_execute(sql, tuple(params), fetch="all") or []
            rows.extend(part)
        except Exception:
            pass
    return rows

def v26_6_stats_from_rows(rows):
    rs = []
    wins = losses = breakeven = 0
    for r in rows or []:
        rr = v26_6_float(r.get("realized_r"), None)
        outcome = v26_6_text(r.get("outcome")).upper()
        if rr is None:
            if outcome in ("TP1", "TP2", "WIN", "PROFIT"):
                rr = 1.0
            elif outcome in ("SL", "LOSS"):
                rr = -1.0
            else:
                rr = 0.0
        rs.append(rr)
        if rr > 0:
            wins += 1
        elif rr < 0:
            losses += 1
        else:
            breakeven += 1
    n = len(rs)
    if n == 0:
        return {
            "occurrences": 0, "wins": 0, "losses": 0, "breakeven": 0, "win_rate": 0,
            "avg_return_r": 0, "expected_return_r": 0, "expected_drawdown_r": 0,
            "profit_factor": 0, "sample_quality": "NO_SAMPLE"
        }
    gross_win = sum(x for x in rs if x > 0)
    gross_loss = abs(sum(x for x in rs if x < 0))
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for x in list(reversed(rs)):
        equity += x
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    win_rate = wins / n * 100
    return {
        "occurrences": n,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "win_rate": round(win_rate, 2),
        "avg_return_r": round(sum(rs) / n, 3),
        "expected_return_r": round(sum(rs) / n, 3),
        "expected_drawdown_r": round(max_dd, 3),
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss else round(gross_win, 3),
        "sample_quality": "GOOD" if n >= 50 else "MEDIUM" if n >= 20 else "LOW_SAMPLE"
    }

def v26_6_blended_dna_stats(symbol, sector, strategy, dna_key):
    symbol_rows = v26_6_query_outcome_rows(symbol=symbol, limit=300)
    sector_rows = v26_6_query_outcome_rows(sector=sector, limit=500)
    strategy_rows = v26_6_query_outcome_rows(strategy=strategy, limit=500)
    all_rows = v26_6_query_outcome_rows(limit=1000)

    s1 = v26_6_stats_from_rows(symbol_rows)
    s2 = v26_6_stats_from_rows(sector_rows)
    s3 = v26_6_stats_from_rows(strategy_rows)
    s4 = v26_6_stats_from_rows(all_rows)

    weights = []
    values = []
    for stat, weight in [(s1, 0.40), (s2, 0.25), (s3, 0.20), (s4, 0.15)]:
        if stat["occurrences"] > 0:
            weights.append(weight)
            values.append((stat, weight))
    if not values:
        # Conservative prior until enough real journal data exists.
        blended = {
            "occurrences": 0, "wins": 0, "losses": 0, "breakeven": 0,
            "win_rate": 52.0, "avg_return_r": 0.10, "expected_return_r": 0.10,
            "expected_drawdown_r": -1.0, "profit_factor": 1.05, "sample_quality": "PRIOR_ONLY"
        }
    else:
        total_w = sum(w for _, w in values)
        blended = {
            "occurrences": sum(st["occurrences"] for st, _ in values),
            "wins": sum(st["wins"] for st, _ in values),
            "losses": sum(st["losses"] for st, _ in values),
            "breakeven": sum(st["breakeven"] for st, _ in values),
            "win_rate": round(sum(st["win_rate"] * w for st, w in values) / total_w, 2),
            "avg_return_r": round(sum(st["avg_return_r"] * w for st, w in values) / total_w, 3),
            "expected_return_r": round(sum(st["expected_return_r"] * w for st, w in values) / total_w, 3),
            "expected_drawdown_r": round(sum(st["expected_drawdown_r"] * w for st, w in values) / total_w, 3),
            "profit_factor": round(sum(st["profit_factor"] * w for st, w in values) / total_w, 3),
            "sample_quality": "BLENDED_GOOD" if sum(st["occurrences"] for st, _ in values) >= 50 else "BLENDED_LOW_SAMPLE"
        }
    try:
        v24_conn_execute("""
            INSERT INTO dna_statistics
            (updated_at, dna_key, occurrences, wins, losses, breakeven, win_rate, avg_return_r,
             expected_return_r, expected_drawdown_r, profit_factor, sample_quality, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(dna_key) DO UPDATE SET
                updated_at=excluded.updated_at,
                occurrences=excluded.occurrences,
                wins=excluded.wins,
                losses=excluded.losses,
                breakeven=excluded.breakeven,
                win_rate=excluded.win_rate,
                avg_return_r=excluded.avg_return_r,
                expected_return_r=excluded.expected_return_r,
                expected_drawdown_r=excluded.expected_drawdown_r,
                profit_factor=excluded.profit_factor,
                sample_quality=excluded.sample_quality,
                source=excluded.source
        """, (
            now_text(), dna_key, blended["occurrences"], blended["wins"], blended["losses"],
            blended["breakeven"], blended["win_rate"], blended["avg_return_r"],
            blended["expected_return_r"], blended["expected_drawdown_r"], blended["profit_factor"],
            blended["sample_quality"], "symbol/sector/strategy/all blended"
        ))
    except Exception as e:
        print("v26_6 stats upsert warning:", e)
    return blended, {"symbol": s1, "sector": s2, "strategy": s3, "all": s4}

def v26_6_historical_similarity(features, stats):
    # Similarity is conservative when sample size is low.
    score = 50.0
    sample = v26_6_int(stats.get("occurrences"), 0)
    score += min(20, sample / 3.0)
    if features.get("rvol_zone") in ("RVOL_STRONG", "RVOL_EXPLOSIVE"):
        score += 6
    if features.get("flow_state") in ("FLOW_STRONG", "FLOW_ELITE"):
        score += 8
    if features.get("regime") in ("REGIME_UPTREND", "REGIME_STRONG_UPTREND") and features.get("side") == "CALL":
        score += 6
    if features.get("regime") in ("REGIME_DOWNTREND", "REGIME_STRONG_DOWNTREND") and features.get("side") == "PUT":
        score += 6
    if features.get("rsi_zone") in ("RSI_HOT", "RSI_OVERHEATED"):
        score -= 8
    return round(max(0, min(100, score)), 2)

def v26_6_conviction_engine(symbol, side="CALL", strategy="UNKNOWN", technical_score=50, flow_score=50,
                            context_score=50, quality_score=50, rsi=None, rvol=None, market_regime="UNKNOWN",
                            vix_state="UNKNOWN", news_state="UNKNOWN", risk_grade="NA", sector=None):
    symbol = v26_6_text(symbol).upper()
    side = v26_6_text(side, "CALL").upper()
    strategy = v26_6_text(strategy, "UNKNOWN").upper()
    sector = sector or v26_6_sector_for_symbol(symbol)

    dna_key, features = v26_6_build_dna_key(
        symbol=symbol, side=side, strategy=strategy, technical_score=technical_score,
        rsi=rsi, rvol=rvol, market_regime=market_regime, vix_state=vix_state,
        news_state=news_state, flow_score=flow_score, risk_grade=risk_grade, sector=sector
    )
    v26_6_upsert_dna_pattern(symbol, dna_key, features)
    stats, component_stats = v26_6_blended_dna_stats(symbol, sector, strategy, dna_key)
    similarity = v26_6_historical_similarity(features, stats)

    tech = v26_6_float(technical_score, 50)
    flow = v26_6_float(flow_score, 50)
    context = v26_6_float(context_score, 50)
    quality = v26_6_float(quality_score, 50)
    dna_win = v26_6_float(stats.get("win_rate"), 52)
    exp_ret = v26_6_float(stats.get("expected_return_r"), 0.10)
    exp_dd = v26_6_float(stats.get("expected_drawdown_r"), -1.0)

    conviction = (
        tech * 0.24 +
        flow * 0.20 +
        context * 0.16 +
        quality * 0.16 +
        dna_win * 0.14 +
        similarity * 0.10
    )
    # Reward good expectancy; penalize bad drawdown.
    conviction += max(-8, min(8, exp_ret * 4.0))
    if exp_dd < -2.0:
        conviction -= 5
    if stats.get("sample_quality") in ("PRIOR_ONLY", "LOW_SAMPLE", "BLENDED_LOW_SAMPLE"):
        conviction -= 4

    conviction = round(max(0, min(100, conviction)), 2)
    if conviction >= 90 and exp_ret >= 1.2 and similarity >= 75:
        grade = "INSTITUTIONAL"
    elif conviction >= 82:
        grade = "HIGH"
    elif conviction >= 70:
        grade = "MEDIUM"
    else:
        grade = "LOW"

    decision = "SEND" if grade in ("HIGH", "INSTITUTIONAL") and tech >= 85 and flow >= 75 and context >= 60 and exp_ret >= 0 else "BLOCK"
    reasons = []
    reasons.append(f"DNA sample={stats.get('occurrences')} quality={stats.get('sample_quality')}")
    reasons.append(f"Predicted win rate={dna_win:.2f}%")
    reasons.append(f"Expected return={exp_ret:.2f}R")
    reasons.append(f"Expected drawdown={exp_dd:.2f}R")
    reasons.append(f"Historical similarity={similarity:.2f}%")
    if decision == "BLOCK":
        if tech < 85:
            reasons.append("BLOCK: technical score below strict threshold")
        if flow < 75:
            reasons.append("BLOCK: option flow score too weak")
        if context < 60:
            reasons.append("BLOCK: market context not supportive")
        if exp_ret < 0:
            reasons.append("BLOCK: negative expected return")

    try:
        v24_conn_execute("""
            INSERT INTO conviction_history
            (created_at, symbol, side, sector, dna_key, technical_score, flow_score, context_score,
             quality_score, dna_win_rate, expected_return_r, expected_drawdown_r, historical_similarity,
             conviction_score, conviction_grade, decision, reasons)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now_text(), symbol, side, sector, dna_key, tech, flow, context, quality,
            dna_win, exp_ret, exp_dd, similarity, conviction, grade, decision,
            " | ".join(reasons)
        ))
    except Exception as e:
        print("v26_6 conviction insert warning:", e)

    return {
        "ok": True,
        "version": V26_6_VERSION,
        "symbol": symbol,
        "side": side,
        "sector": sector,
        "strategy": strategy,
        "dna_key": dna_key,
        "features": features,
        "predicted_win_rate": round(dna_win, 2),
        "expected_return_r": round(exp_ret, 3),
        "expected_drawdown_r": round(exp_dd, 3),
        "historical_similarity": similarity,
        "conviction_score": conviction,
        "conviction_grade": grade,
        "decision": decision,
        "reasons": reasons,
        "dna_stats": stats,
        "component_stats": component_stats,
    }

def v26_6_recent(table, limit=50):
    allowed = {"trade_dna_patterns", "dna_statistics", "conviction_history"}
    if table not in allowed:
        return []
    try:
        return v24_conn_execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (v26_6_int(limit, 50),), fetch="all") or []
    except Exception as e:
        return [{"error": str(e)}]

@app.route('/v26/dna/<symbol>')
def v26_6_route_dna(symbol):
    result = v26_6_conviction_engine(
        symbol=symbol,
        side=request.args.get("side") or "CALL",
        strategy=request.args.get("strategy") or "UNKNOWN",
        technical_score=request.args.get("technical_score") or request.args.get("score") or 50,
        flow_score=request.args.get("flow_score") or 50,
        context_score=request.args.get("context_score") or 50,
        quality_score=request.args.get("quality_score") or 50,
        rsi=request.args.get("rsi"),
        rvol=request.args.get("rvol"),
        market_regime=request.args.get("regime") or "UNKNOWN",
        vix_state=request.args.get("vix_state") or "UNKNOWN",
        news_state=request.args.get("news_state") or "UNKNOWN",
        risk_grade=request.args.get("risk_grade") or "NA",
        sector=request.args.get("sector"),
    )
    return jsonify(result)

@app.route('/v26/conviction')
def v26_6_route_conviction():
    symbol = request.args.get("symbol") or "NVDA"
    return v26_6_route_dna(symbol)

@app.route('/v26/conviction-gate')
def v26_6_route_conviction_gate():
    symbol = request.args.get("symbol") or "NVDA"
    result = v26_6_conviction_engine(
        symbol=symbol,
        side=request.args.get("side") or "CALL",
        strategy=request.args.get("strategy") or "UNKNOWN",
        technical_score=request.args.get("technical_score") or request.args.get("score") or 50,
        flow_score=request.args.get("flow_score") or 50,
        context_score=request.args.get("context_score") or 50,
        quality_score=request.args.get("quality_score") or 50,
        rsi=request.args.get("rsi"),
        rvol=request.args.get("rvol"),
        market_regime=request.args.get("regime") or "UNKNOWN",
        vix_state=request.args.get("vix_state") or "UNKNOWN",
        news_state=request.args.get("news_state") or "UNKNOWN",
        risk_grade=request.args.get("risk_grade") or "NA",
        sector=request.args.get("sector"),
    )
    return jsonify({
        "ok": True,
        "symbol": result["symbol"],
        "decision": result["decision"],
        "conviction_grade": result["conviction_grade"],
        "conviction_score": result["conviction_score"],
        "predicted_win_rate": result["predicted_win_rate"],
        "expected_return_r": result["expected_return_r"],
        "expected_drawdown_r": result["expected_drawdown_r"],
        "historical_similarity": result["historical_similarity"],
        "reasons": result["reasons"],
    })

@app.route('/v26/dna-stats')
def v26_6_route_dna_stats():
    return jsonify({
        "ok": True,
        "version": V26_6_VERSION,
        "top_dna": v26_6_recent("dna_statistics", request.args.get("limit") or 50),
        "patterns": v26_6_recent("trade_dna_patterns", request.args.get("limit") or 50),
    })

@app.route('/v26/conviction-history')
def v26_6_route_conviction_history():
    return jsonify({
        "ok": True,
        "version": V26_6_VERSION,
        "history": v26_6_recent("conviction_history", request.args.get("limit") or 100),
    })

@app.route('/v26/conviction-dashboard')
def v26_6_route_dashboard():
    rows = v26_6_recent("conviction_history", 30)
    stats = v26_6_recent("dna_statistics", 30)
    html = "<h1>V26.6 Trade DNA + Conviction Engine</h1>"
    html += "<p>ระบบนี้ตอบก่อนส่ง Alert ว่า: Win Rate คาดการณ์, Expected Return, Expected Drawdown และ Historical Similarity เป็นอย่างไร</p>"
    html += "<h2>Recent Conviction Decisions</h2><table border='1' cellpadding='6'><tr><th>Time</th><th>Symbol</th><th>Side</th><th>Conviction</th><th>Grade</th><th>Decision</th><th>Win%</th><th>Exp R</th><th>Similarity</th></tr>"
    for r in rows:
        html += f"<tr><td>{r.get('created_at','')}</td><td>{r.get('symbol','')}</td><td>{r.get('side','')}</td><td>{r.get('conviction_score','')}</td><td>{r.get('conviction_grade','')}</td><td>{r.get('decision','')}</td><td>{r.get('dna_win_rate','')}</td><td>{r.get('expected_return_r','')}</td><td>{r.get('historical_similarity','')}</td></tr>"
    html += "</table><h2>DNA Statistics</h2><table border='1' cellpadding='6'><tr><th>DNA</th><th>Sample</th><th>Win%</th><th>Exp R</th><th>PF</th><th>Quality</th></tr>"
    for r in stats:
        html += f"<tr><td>{str(r.get('dna_key',''))[:80]}</td><td>{r.get('occurrences','')}</td><td>{r.get('win_rate','')}</td><td>{r.get('expected_return_r','')}</td><td>{r.get('profit_factor','')}</td><td>{r.get('sample_quality','')}</td></tr>"
    html += "</table>"
    return Response(html, mimetype="text/html")

try:
    v26_6_init_db()
except Exception as e:
    print("v26.6 init warning:", e)

# ============================================================
# END V26.6 TRADE DNA + CONVICTION ENGINE
# ============================================================



# ============================================================
# V26.7 MARKET BREADTH + SECTOR ROTATION + RELATIVE STRENGTH
# ============================================================
V26_7_VERSION = "V26.7 Market Breadth + Sector Rotation Intelligence"

V26_7_SECTOR_ETFS = {
    "Technology": "XLK",
    "Semiconductor": "SMH",
    "AI": "BOTZ",
    "Energy": "XLE",
    "Financial": "XLF",
    "Healthcare": "XLV",
    "Industrial": "XLI",
    "Consumer_Discretionary": "XLY",
    "Consumer_Staples": "XLP",
    "Utilities": "XLU",
    "Real_Estate": "XLRE",
    "Materials": "XLB",
    "Communications": "XLC",
    "Aerospace_Defense": "ITA",
    "Crypto_Proxy": "BITQ",
    "Quantum_Proxy": "QTUM",
}

V26_7_SYMBOL_SECTOR = {
    # Mega cap / AI / Tech
    "NVDA": "Semiconductor", "AMD": "Semiconductor", "AVGO": "Semiconductor", "TSM": "Semiconductor",
    "MRVL": "Semiconductor", "AMKR": "Semiconductor", "INTC": "Semiconductor", "MU": "Semiconductor",
    "SMCI": "Semiconductor", "ARM": "Semiconductor", "WDC": "Semiconductor", "AAOI": "Semiconductor",
    "AEHR": "Semiconductor", "AXTI": "Semiconductor",
    "AAPL": "Technology", "MSFT": "Technology", "META": "Technology", "GOOGL": "Technology",
    "GOOG": "Technology", "AMZN": "Consumer_Discretionary", "NFLX": "Communications",
    "PLTR": "AI", "CRWD": "Technology", "SNOW": "Technology", "NET": "Technology", "DDOG": "Technology",
    "CRDO": "Semiconductor", "CRWV": "AI", "NBIS": "AI", "LAES": "Technology",
    # High beta / themes
    "TSLA": "Consumer_Discretionary", "HOOD": "Financial", "COIN": "Crypto_Proxy", "MSTR": "Crypto_Proxy",
    "RKLB": "Aerospace_Defense", "ASTS": "Aerospace_Defense", "KTOS": "Aerospace_Defense",
    "AVAV": "Aerospace_Defense", "BKSY": "Aerospace_Defense", "PL": "Aerospace_Defense",
    "OKLO": "Energy", "CEG": "Energy", "VST": "Energy", "LEU": "Energy", "UUUU": "Energy",
    "QBTS": "Quantum_Proxy", "IONQ": "Quantum_Proxy", "RGTI": "Quantum_Proxy", "QUBT": "Quantum_Proxy",
    # ETFs
    "SPY": "Index", "QQQ": "Index", "IWM": "Index", "TQQQ": "Index", "SQQQ": "Index", "SOXL": "Semiconductor",
}

V26_7_THEME_GROUPS = {
    "Semiconductor": ["NVDA", "AMD", "AVGO", "TSM", "MRVL", "AMKR", "INTC", "MU", "SMCI", "ARM", "WDC", "AAOI", "AEHR", "AXTI", "CRDO"],
    "AI": ["NVDA", "PLTR", "MSFT", "GOOGL", "META", "CRWV", "NBIS", "SMCI"],
    "MegaCap_Tech": ["AAPL", "MSFT", "AMZN", "META", "GOOGL", "GOOG", "NVDA", "AVGO"],
    "Aerospace_Defense": ["RKLB", "ASTS", "KTOS", "AVAV", "BKSY", "PL"],
    "Energy_Nuclear": ["OKLO", "CEG", "VST", "LEU", "UUUU"],
    "Quantum": ["QBTS", "IONQ", "RGTI", "QUBT"],
    "Crypto": ["COIN", "MSTR", "HOOD", "BITQ"],
}

def v26_7_now_iso():
    return datetime.now(timezone.utc).isoformat()

def v26_7_float(x, default=0.0):
    try:
        if x is None or x == "":
            return default
        return float(str(x).replace(",", "").strip())
    except Exception:
        return default

def v26_7_int(x, default=0):
    try:
        if x is None or x == "":
            return default
        return int(float(str(x).replace(",", "").strip()))
    except Exception:
        return default

def v26_7_json(obj):
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return "{}"

def v26_7_init_db():
    """Create V26.7 tables without disturbing legacy tables."""
    v24_conn_execute("""
        CREATE TABLE IF NOT EXISTS market_breadth (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            universe TEXT,
            advancers INTEGER DEFAULT 0,
            decliners INTEGER DEFAULT 0,
            unchanged INTEGER DEFAULT 0,
            advance_decline_ratio REAL DEFAULT 0,
            new_highs INTEGER DEFAULT 0,
            new_lows INTEGER DEFAULT 0,
            up_volume REAL DEFAULT 0,
            down_volume REAL DEFAULT 0,
            up_down_volume_ratio REAL DEFAULT 0,
            breadth_score REAL DEFAULT 50,
            status TEXT,
            raw_json TEXT
        )
    """)
    v24_conn_execute("""
        CREATE TABLE IF NOT EXISTS sector_rotation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            sector TEXT,
            etf_symbol TEXT,
            return_1d REAL DEFAULT 0,
            return_5d REAL DEFAULT 0,
            return_20d REAL DEFAULT 0,
            volume_ratio REAL DEFAULT 1,
            relative_strength REAL DEFAULT 50,
            money_flow_score REAL DEFAULT 50,
            rank_no INTEGER DEFAULT 0,
            status TEXT,
            raw_json TEXT
        )
    """)
    v24_conn_execute("""
        CREATE TABLE IF NOT EXISTS money_flow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            theme TEXT,
            theme_score REAL DEFAULT 50,
            leaders TEXT,
            laggards TEXT,
            status TEXT,
            raw_json TEXT
        )
    """)
    v24_conn_execute("""
        CREATE TABLE IF NOT EXISTS relative_strength (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            symbol TEXT,
            sector TEXT,
            return_1d REAL DEFAULT 0,
            return_5d REAL DEFAULT 0,
            return_20d REAL DEFAULT 0,
            relative_strength_score REAL DEFAULT 50,
            rank_no INTEGER DEFAULT 0,
            raw_json TEXT
        )
    """)
    v24_conn_execute("""
        CREATE TABLE IF NOT EXISTS suppressed_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            symbol TEXT,
            side TEXT,
            original_score REAL DEFAULT 0,
            adjusted_score REAL DEFAULT 0,
            breadth_score REAL DEFAULT 50,
            sector_score REAL DEFAULT 50,
            relative_strength_score REAL DEFAULT 50,
            action TEXT,
            reason TEXT,
            raw_json TEXT
        )
    """)

def v26_7_recent(table, limit=50):
    limit = max(1, min(500, v26_7_int(limit, 50)))
    try:
        return v24_conn_execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT {limit}", fetch="all") or []
    except Exception:
        return []

def v26_7_price_series(symbol, period="3mo", interval="1d"):
    """Free Yahoo series helper. Returns closes, highs, lows, volumes."""
    try:
        data = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
        if data is None or data.empty:
            return [], [], [], []
        data = data.dropna()
        closes = [float(x) for x in data["Close"].tolist()]
        highs = [float(x) for x in data["High"].tolist()]
        lows = [float(x) for x in data["Low"].tolist()]
        volumes = [float(x) for x in data["Volume"].fillna(0).tolist()]
        return closes, highs, lows, volumes
    except Exception as e:
        print("v26.7 price series error:", symbol, e)
        return [], [], [], []

def v26_7_returns(symbol):
    closes, highs, lows, volumes = v26_7_price_series(symbol)
    if len(closes) < 22:
        return {"symbol": symbol, "ok": False, "return_1d": 0, "return_5d": 0, "return_20d": 0, "volume_ratio": 1}
    def ret(n):
        try:
            return (closes[-1] - closes[-n-1]) / closes[-n-1] * 100 if closes[-n-1] else 0
        except Exception:
            return 0
    avg_vol = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 and sum(volumes[-21:-1]) > 0 else 0
    volume_ratio = volumes[-1] / avg_vol if avg_vol else 1
    return {
        "symbol": symbol, "ok": True,
        "price": closes[-1],
        "high_20": max(highs[-20:]) if highs else None,
        "low_20": min(lows[-20:]) if lows else None,
        "volume": volumes[-1] if volumes else 0,
        "return_1d": round(ret(1), 3),
        "return_5d": round(ret(5), 3),
        "return_20d": round(ret(20), 3),
        "volume_ratio": round(volume_ratio, 3),
    }

def v26_7_score_from_returns(r1, r5, r20, volume_ratio=1.0):
    score = 50 + (r1 * 2.0) + (r5 * 2.5) + (r20 * 1.2)
    if volume_ratio >= 1.5:
        score += 6
    elif volume_ratio < 0.7:
        score -= 5
    return round(max(0, min(100, score)), 2)

def v26_7_breadth_universe():
    raw = os.getenv("V26_7_BREADTH_UNIVERSE", "")
    if raw.strip():
        return [x.strip().upper() for x in raw.split(",") if x.strip()]
    base = []
    try:
        base += list(US_WATCHLIST or [])
        base += list(TIER_A_WATCHLIST or [])
        base += list(TIER_B_WATCHLIST or [])
    except Exception:
        pass
    base += ["NVDA","AAPL","MSFT","AMZN","META","GOOGL","TSLA","AMD","AVGO","PLTR","TSM","MRVL","QQQ","SPY","IWM","SMH","XLK","XLE","XLF","XLV","XLI","XLY"]
    # de-dup, no Thai, cap for free API stability.
    seen, out = set(), []
    for s in base:
        s = str(s).upper().replace(".BK", "")
        if s and s not in seen and s not in {"GOLD","XAUUSD"}:
            seen.add(s); out.append(s)
    return out[:80]

def v26_7_market_breadth(universe=None, save=True):
    symbols = universe or v26_7_breadth_universe()
    adv = dec = unch = new_highs = new_lows = 0
    up_vol = down_vol = 0.0
    rows = []
    for sym in symbols:
        data = v26_7_returns(sym)
        if not data.get("ok"):
            continue
        r1 = data["return_1d"]
        if r1 > 0.05:
            adv += 1; up_vol += data.get("volume", 0)
        elif r1 < -0.05:
            dec += 1; down_vol += data.get("volume", 0)
        else:
            unch += 1
        price = data.get("price")
        if price and data.get("high_20") and price >= data["high_20"] * 0.995:
            new_highs += 1
        if price and data.get("low_20") and price <= data["low_20"] * 1.005:
            new_lows += 1
        rows.append(data)
    total = max(1, adv + dec + unch)
    ad_ratio = adv / max(1, dec)
    ud_vol_ratio = up_vol / max(1.0, down_vol)
    adv_pct = adv / total * 100
    nhnl = (new_highs - new_lows) / max(1, total) * 100
    breadth_score = 50 + (adv_pct - 50) * 0.7 + min(20, max(-20, (ad_ratio - 1) * 10)) + min(15, max(-15, nhnl))
    breadth_score = round(max(0, min(100, breadth_score)), 2)
    if breadth_score >= 70:
        status = "HEALTHY / RISK-ON"
    elif breadth_score >= 55:
        status = "NEUTRAL POSITIVE"
    elif breadth_score >= 40:
        status = "WEAK / CAUTION"
    else:
        status = "RISK-OFF / SUPPRESS ALERTS"
    result = {
        "ok": True, "version": V26_7_VERSION, "universe_size": len(rows),
        "advancers": adv, "decliners": dec, "unchanged": unch,
        "advance_decline_ratio": round(ad_ratio, 3),
        "new_highs": new_highs, "new_lows": new_lows,
        "up_volume": round(up_vol, 2), "down_volume": round(down_vol, 2),
        "up_down_volume_ratio": round(ud_vol_ratio, 3),
        "breadth_score": breadth_score, "status": status, "rows": rows[:120],
    }
    if save:
        try:
            v24_conn_execute("""
                INSERT INTO market_breadth
                (created_at, universe, advancers, decliners, unchanged, advance_decline_ratio, new_highs, new_lows, up_volume, down_volume, up_down_volume_ratio, breadth_score, status, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (v26_7_now_iso(), ",".join(symbols), adv, dec, unch, round(ad_ratio,3), new_highs, new_lows, round(up_vol,2), round(down_vol,2), round(ud_vol_ratio,3), breadth_score, status, v26_7_json(result)))
        except Exception as e:
            print("v26.7 save breadth error:", e)
    return result

def v26_7_sector_rotation(save=True):
    items = []
    spy = v26_7_returns("SPY")
    spy_20 = spy.get("return_20d", 0) if spy.get("ok") else 0
    for sector, etf in V26_7_SECTOR_ETFS.items():
        data = v26_7_returns(etf)
        if not data.get("ok"):
            continue
        rs = v26_7_score_from_returns(data["return_1d"], data["return_5d"], data["return_20d"] - spy_20, data["volume_ratio"])
        money_flow = round(max(0, min(100, rs + (data["volume_ratio"] - 1) * 8)), 2)
        status = "LEADER" if money_flow >= 70 else "IMPROVING" if money_flow >= 58 else "LAGGARD" if money_flow < 42 else "NEUTRAL"
        item = {
            "sector": sector, "etf_symbol": etf,
            "return_1d": data["return_1d"], "return_5d": data["return_5d"], "return_20d": data["return_20d"],
            "volume_ratio": data["volume_ratio"], "relative_strength": rs, "money_flow_score": money_flow, "status": status,
        }
        items.append(item)
    items.sort(key=lambda x: x["money_flow_score"], reverse=True)
    for i, it in enumerate(items, 1):
        it["rank_no"] = i
        if save:
            try:
                v24_conn_execute("""
                    INSERT INTO sector_rotation
                    (created_at, sector, etf_symbol, return_1d, return_5d, return_20d, volume_ratio, relative_strength, money_flow_score, rank_no, status, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (v26_7_now_iso(), it["sector"], it["etf_symbol"], it["return_1d"], it["return_5d"], it["return_20d"], it["volume_ratio"], it["relative_strength"], it["money_flow_score"], it["rank_no"], it["status"], v26_7_json(it)))
            except Exception as e:
                print("v26.7 save sector error:", e)
    return {"ok": True, "version": V26_7_VERSION, "sectors": items, "leaders": items[:5], "laggards": items[-5:]}

def v26_7_symbol_sector(symbol):
    sym = str(symbol or "").upper().replace(".BK","")
    return V26_7_SYMBOL_SECTOR.get(sym, "Other")

def v26_7_relative_strength(symbols=None, save=True):
    if symbols is None:
        symbols = v26_7_breadth_universe()
    rows = []
    spy = v26_7_returns("SPY")
    spy20 = spy.get("return_20d", 0) if spy.get("ok") else 0
    for sym in symbols:
        sym = str(sym).upper().replace(".BK","")
        if not sym or sym in {"GOLD","XAUUSD"}:
            continue
        data = v26_7_returns(sym)
        if not data.get("ok"):
            continue
        rs = v26_7_score_from_returns(data["return_1d"], data["return_5d"], data["return_20d"] - spy20, data["volume_ratio"])
        row = {
            "symbol": sym, "sector": v26_7_symbol_sector(sym),
            "return_1d": data["return_1d"], "return_5d": data["return_5d"], "return_20d": data["return_20d"],
            "relative_strength_score": rs, "volume_ratio": data["volume_ratio"],
        }
        rows.append(row)
    rows.sort(key=lambda x: x["relative_strength_score"], reverse=True)
    for i, row in enumerate(rows, 1):
        row["rank_no"] = i
        if save:
            try:
                v24_conn_execute("""
                    INSERT INTO relative_strength
                    (created_at, symbol, sector, return_1d, return_5d, return_20d, relative_strength_score, rank_no, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (v26_7_now_iso(), row["symbol"], row["sector"], row["return_1d"], row["return_5d"], row["return_20d"], row["relative_strength_score"], i, v26_7_json(row)))
            except Exception as e:
                print("v26.7 save relative strength error:", e)
    return {"ok": True, "version": V26_7_VERSION, "ranking": rows, "top": rows[:20]}

def v26_7_money_flow(save=True):
    sector_result = v26_7_sector_rotation(save=False)
    sector_scores = {x["sector"]: x["money_flow_score"] for x in sector_result.get("sectors", [])}
    results = []
    for theme, symbols in V26_7_THEME_GROUPS.items():
        rs = v26_7_relative_strength(symbols, save=False).get("ranking", [])
        leaders = rs[:3]
        laggards = rs[-3:] if len(rs) >= 3 else rs
        sector = v26_7_symbol_sector(symbols[0]) if symbols else "Other"
        sector_score = sector_scores.get(sector, 50)
        avg_rs = sum(x["relative_strength_score"] for x in leaders) / max(1, len(leaders)) if leaders else 50
        theme_score = round(max(0, min(100, avg_rs * 0.6 + sector_score * 0.4)), 2)
        status = "STRONG INFLOW" if theme_score >= 75 else "INFLOW" if theme_score >= 60 else "OUTFLOW" if theme_score < 40 else "NEUTRAL"
        item = {
            "theme": theme, "theme_score": theme_score, "sector_score": sector_score,
            "leaders": leaders, "laggards": laggards, "status": status,
        }
        results.append(item)
        if save:
            try:
                v24_conn_execute("""
                    INSERT INTO money_flow
                    (created_at, theme, theme_score, leaders, laggards, status, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (v26_7_now_iso(), theme, theme_score, v26_7_json(leaders), v26_7_json(laggards), status, v26_7_json(item)))
            except Exception as e:
                print("v26.7 save money flow error:", e)
    results.sort(key=lambda x: x["theme_score"], reverse=True)
    return {"ok": True, "version": V26_7_VERSION, "themes": results, "leaders": results[:5], "laggards": results[-5:]}

def v26_7_theme_for_symbol(symbol):
    sym = str(symbol or "").upper().replace(".BK","")
    for theme, symbols in V26_7_THEME_GROUPS.items():
        if sym in symbols:
            return theme
    return v26_7_symbol_sector(sym)

def v26_7_score_context(symbol, original_score=50, side="CALL", breadth=None, sector_rotation=None, relative_strength=None, save=True):
    sym = str(symbol or "").upper().replace(".BK","")
    original = v26_7_float(original_score, 50)
    side = str(side or "CALL").upper()
    breadth = breadth or v26_7_market_breadth(save=False)
    sector_rotation = sector_rotation or v26_7_sector_rotation(save=False)
    rs_result = relative_strength or v26_7_relative_strength([sym], save=False)
    breadth_score = v26_7_float(breadth.get("breadth_score"), 50)
    sector = v26_7_symbol_sector(sym)
    sector_scores = {x.get("sector"): v26_7_float(x.get("money_flow_score"), 50) for x in sector_rotation.get("sectors", [])}
    sector_score = sector_scores.get(sector, 50)
    rs_rows = rs_result.get("ranking", [])
    rs_score = v26_7_float(rs_rows[0].get("relative_strength_score"), 50) if rs_rows else 50
    adjusted = original
    reasons = []
    action = "ALLOW"

    # Weak market suppression: protect capital first.
    if breadth_score < 40:
        if side.startswith("CALL"):
            adjusted -= 18
            action = "BLOCK" if adjusted < 85 else "REDUCE_SIZE"
            reasons.append("Breadth < 40: ตลาดอ่อนแอ กด/บล็อก CALL แม้หุ้นรายตัวสวย")
        else:
            adjusted += 5
            reasons.append("Breadth < 40: สภาพตลาดสนับสนุนฝั่ง PUT มากกว่า")
    elif breadth_score < 55:
        adjusted -= 8 if side.startswith("CALL") else 0
        action = "REDUCE_SIZE" if side.startswith("CALL") else action
        reasons.append("Breadth อ่อน: ลดขนาดไม้/ลดความมั่นใจ")
    elif breadth_score >= 70 and side.startswith("CALL"):
        adjusted += 5
        reasons.append("Breadth แข็งแรง: สนับสนุนสัญญาณฝั่งซื้อ")

    # Sector rotation boost/penalty.
    if sector_score >= 70:
        adjusted += 6
        reasons.append(f"Sector/Money Flow แข็งแรง ({sector}: {sector_score})")
    elif sector_score < 45:
        adjusted -= 8
        action = "REDUCE_SIZE" if action == "ALLOW" else action
        reasons.append(f"Sector/Money Flow อ่อน ({sector}: {sector_score})")

    # Relative strength ranking.
    if rs_score >= 75:
        adjusted += 5
        reasons.append(f"Relative Strength แข็งแรง ({rs_score})")
    elif rs_score < 45:
        adjusted -= 7
        action = "REDUCE_SIZE" if action == "ALLOW" else action
        reasons.append(f"Relative Strength ต่ำ ({rs_score})")

    adjusted = round(max(0, min(100, adjusted)), 2)
    if adjusted < 85 and original >= 85:
        action = "BLOCK" if breadth_score < 40 else "REDUCE_SIZE"
    if not reasons:
        reasons.append("Breadth/Sector/RS เป็นกลาง ไม่ปรับคะแนนมาก")

    result = {
        "ok": True, "version": V26_7_VERSION, "symbol": sym, "side": side,
        "original_score": original, "adjusted_score": adjusted,
        "breadth_score": breadth_score, "breadth_status": breadth.get("status"),
        "sector": sector, "sector_score": sector_score,
        "relative_strength_score": rs_score,
        "action": action,
        "pass_gate": action != "BLOCK" and adjusted >= 85,
        "reasons": reasons,
    }
    if save and action in {"BLOCK", "REDUCE_SIZE"}:
        try:
            v24_conn_execute("""
                INSERT INTO suppressed_signals
                (created_at, symbol, side, original_score, adjusted_score, breadth_score, sector_score, relative_strength_score, action, reason, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (v26_7_now_iso(), sym, side, original, adjusted, breadth_score, sector_score, rs_score, action, " | ".join(reasons), v26_7_json(result)))
        except Exception as e:
            print("v26.7 save suppression error:", e)
    return result

def v26_7_best_of_theme(symbols, scores=None):
    if isinstance(symbols, str):
        symbols = [x.strip().upper() for x in symbols.split(",") if x.strip()]
    scores = scores or {}
    # Build shared context once for speed.
    breadth = v26_7_market_breadth(save=False)
    sector_rot = v26_7_sector_rotation(save=False)
    rs = v26_7_relative_strength(symbols, save=False)
    rs_map = {x["symbol"]: x for x in rs.get("ranking", [])}
    candidates = []
    for sym in symbols:
        sym = str(sym).upper().replace(".BK","")
        base_score = v26_7_float(scores.get(sym), 85)
        ctx = v26_7_score_context(sym, base_score, "CALL", breadth, sector_rot, {"ranking":[rs_map.get(sym, {})] if sym in rs_map else []}, save=False)
        candidates.append({
            "symbol": sym,
            "theme": v26_7_theme_for_symbol(sym),
            "sector": v26_7_symbol_sector(sym),
            "base_score": base_score,
            "adjusted_score": ctx["adjusted_score"],
            "breadth_score": ctx["breadth_score"],
            "sector_score": ctx["sector_score"],
            "relative_strength_score": ctx["relative_strength_score"],
            "action": ctx["action"],
            "pass_gate": ctx["pass_gate"],
            "reasons": ctx["reasons"],
        })
    # Select one best per theme, especially Semiconductor cluster like NVDA/AMD/AVGO/TSM.
    grouped = {}
    for c in candidates:
        grouped.setdefault(c["theme"], []).append(c)
    selected = []
    rejected = []
    for theme, rows in grouped.items():
        rows.sort(key=lambda x: (x["pass_gate"], x["adjusted_score"], x["relative_strength_score"]), reverse=True)
        if rows:
            selected.append(rows[0])
            rejected.extend([{**r, "reject_reason": f"Theme duplicate: selected {rows[0]['symbol']}"} for r in rows[1:]])
    selected.sort(key=lambda x: x["adjusted_score"], reverse=True)
    return {"ok": True, "version": V26_7_VERSION, "selected": selected, "rejected": rejected, "all_candidates": candidates}

def v26_7_alert_gate(symbol, asset=None, analysis=None, sig="CALL"):
    """Gate to be called before LINE alert. Returns (ok, reason)."""
    analysis = analysis or {}
    score = v26_7_float(analysis.get("score"), 50)
    side = str(sig or "CALL").upper()
    result = v26_7_score_context(symbol, score, side)
    if not result["pass_gate"]:
        return False, f"V26.7 {result['action']}: " + " | ".join(result["reasons"])
    return True, f"V26.7 PASS adjusted_score={result['adjusted_score']} breadth={result['breadth_score']} sector={result['sector_score']} rs={result['relative_strength_score']}"

# Integrate V26.7 into legacy alert gate without rewriting the old alert system.
try:
    _v26_7_original_should_send_alert_final = should_send_alert_final
    def should_send_alert_final(symbol, sig, analysis, asset):
        ok, reason = _v26_7_original_should_send_alert_final(symbol, sig, analysis, asset)
        if not ok:
            return ok, reason
        try:
            gate_ok, gate_reason = v26_7_alert_gate(symbol, asset, analysis, sig)
            if not gate_ok:
                return False, gate_reason
        except Exception as e:
            print("v26.7 gate warning:", e)
        return True, "PASS"
except Exception as e:
    print("v26.7 alert gate integration warning:", e)

@app.route('/v26/breadth')
@app.route('/v26/market-breadth')
def v26_7_route_breadth():
    symbols = request.args.get("symbols")
    universe = [x.strip().upper() for x in symbols.split(",") if x.strip()] if symbols else None
    return jsonify(v26_7_market_breadth(universe=universe, save=True))

@app.route('/v26/sector-rotation')
def v26_7_route_sector_rotation():
    return jsonify(v26_7_sector_rotation(save=True))

@app.route('/v26/money-flow')
def v26_7_route_money_flow():
    return jsonify(v26_7_money_flow(save=True))

@app.route('/v26/relative-strength')
def v26_7_route_relative_strength():
    symbols = request.args.get("symbols")
    universe = [x.strip().upper() for x in symbols.split(",") if x.strip()] if symbols else None
    return jsonify(v26_7_relative_strength(symbols=universe, save=True))

@app.route('/v26/suppression/<symbol>')
def v26_7_route_suppression(symbol):
    return jsonify(v26_7_score_context(
        symbol=symbol,
        original_score=request.args.get("score") or 85,
        side=request.args.get("side") or "CALL",
        save=True,
    ))

@app.route('/v26/best-of-theme')
def v26_7_route_best_of_theme():
    symbols = request.args.get("symbols") or "NVDA,AMD,AVGO,TSM"
    return jsonify(v26_7_best_of_theme(symbols))

@app.route('/v26/suppressed-signals')
def v26_7_route_suppressed_signals():
    return jsonify({"ok": True, "version": V26_7_VERSION, "rows": v26_7_recent("suppressed_signals", request.args.get("limit") or 100)})

@app.route('/v26/market-intelligence-dashboard')
@app.route('/v26/v26-7-dashboard')
def v26_7_route_dashboard():
    breadth_rows = v26_7_recent("market_breadth", 10)
    sector_rows = v26_7_recent("sector_rotation", 20)
    money_rows = v26_7_recent("money_flow", 20)
    rs_rows = v26_7_recent("relative_strength", 30)
    suppressed_rows = v26_7_recent("suppressed_signals", 30)

    html = "<h1>V26.7 Market Breadth + Sector Rotation Intelligence</h1>"
    html += "<p>ระบบนี้ช่วยตอบว่า เงินกำลังไหลเข้า Sector/Theme ไหน และตลาดโดยรวมแข็งพอให้ส่ง Alert หรือไม่</p>"
    html += "<p><a href='/v26/breadth'>Market Breadth</a> | <a href='/v26/sector-rotation'>Sector Rotation</a> | <a href='/v26/money-flow'>Money Flow</a> | <a href='/v26/relative-strength'>Relative Strength</a> | <a href='/v26/best-of-theme?symbols=NVDA,AMD,AVGO,TSM'>Best of Theme</a></p>"

    html += "<h2>Latest Breadth</h2><table border='1' cellpadding='6'><tr><th>Time</th><th>Score</th><th>Status</th><th>Adv</th><th>Dec</th><th>A/D</th><th>NH</th><th>NL</th></tr>"
    for r in breadth_rows:
        html += f"<tr><td>{r.get('created_at','')}</td><td>{r.get('breadth_score','')}</td><td>{r.get('status','')}</td><td>{r.get('advancers','')}</td><td>{r.get('decliners','')}</td><td>{r.get('advance_decline_ratio','')}</td><td>{r.get('new_highs','')}</td><td>{r.get('new_lows','')}</td></tr>"
    html += "</table>"

    html += "<h2>Sector Leaders / Laggards</h2><table border='1' cellpadding='6'><tr><th>Rank</th><th>Sector</th><th>ETF</th><th>1D</th><th>5D</th><th>20D</th><th>Flow</th><th>Status</th></tr>"
    for r in sector_rows:
        html += f"<tr><td>{r.get('rank_no','')}</td><td>{r.get('sector','')}</td><td>{r.get('etf_symbol','')}</td><td>{r.get('return_1d','')}</td><td>{r.get('return_5d','')}</td><td>{r.get('return_20d','')}</td><td>{r.get('money_flow_score','')}</td><td>{r.get('status','')}</td></tr>"
    html += "</table>"

    html += "<h2>Theme Money Flow</h2><table border='1' cellpadding='6'><tr><th>Theme</th><th>Score</th><th>Status</th><th>Leaders</th></tr>"
    for r in money_rows:
        html += f"<tr><td>{r.get('theme','')}</td><td>{r.get('theme_score','')}</td><td>{r.get('status','')}</td><td>{str(r.get('leaders',''))[:160]}</td></tr>"
    html += "</table>"

    html += "<h2>Relative Strength Ranking</h2><table border='1' cellpadding='6'><tr><th>Rank</th><th>Symbol</th><th>Sector</th><th>RS</th><th>1D</th><th>5D</th><th>20D</th></tr>"
    for r in rs_rows:
        html += f"<tr><td>{r.get('rank_no','')}</td><td>{r.get('symbol','')}</td><td>{r.get('sector','')}</td><td>{r.get('relative_strength_score','')}</td><td>{r.get('return_1d','')}</td><td>{r.get('return_5d','')}</td><td>{r.get('return_20d','')}</td></tr>"
    html += "</table>"

    html += "<h2>Suppressed / Reduced Signals</h2><table border='1' cellpadding='6'><tr><th>Time</th><th>Symbol</th><th>Side</th><th>Original</th><th>Adjusted</th><th>Breadth</th><th>Sector</th><th>RS</th><th>Action</th><th>Reason</th></tr>"
    for r in suppressed_rows:
        html += f"<tr><td>{r.get('created_at','')}</td><td>{r.get('symbol','')}</td><td>{r.get('side','')}</td><td>{r.get('original_score','')}</td><td>{r.get('adjusted_score','')}</td><td>{r.get('breadth_score','')}</td><td>{r.get('sector_score','')}</td><td>{r.get('relative_strength_score','')}</td><td>{r.get('action','')}</td><td>{r.get('reason','')}</td></tr>"
    html += "</table>"
    return Response(html, mimetype="text/html")

try:
    v26_7_init_db()
except Exception as e:
    print("v26.7 init warning:", e)

# ============================================================
# END V26.7 MARKET BREADTH + SECTOR ROTATION INTELLIGENCE
# ============================================================


# ============================================================
# V28 FUND VALIDATION CORE INTEGRATION
# ============================================================
try:
    from modules.v28_fund_validation_core import init_v28_db, portfolio_gate as v28_portfolio_gate
    init_v28_db()
    _v28_original_should_send_alert_final = should_send_alert_final
    def should_send_alert_final(symbol, sig, analysis, asset):
        ok, reason = _v28_original_should_send_alert_final(symbol, sig, analysis, asset)
        if not ok:
            return ok, reason
        try:
            gate_ok, gate_detail = v28_portfolio_gate(symbol, analysis, sig)
            if isinstance(analysis, dict):
                analysis["v28_portfolio_gate"] = gate_detail
            if not gate_ok:
                return False, "V28 Portfolio Risk Gate: " + " | ".join(gate_detail.get("reasons") or ["BLOCK"])
        except Exception as e:
            print("V28 portfolio gate warning:", e)
        return True, "PASS"
except Exception as e:
    print("V28 fund validation integration warning:", e)
# ============================================================
# END V28 FUND VALIDATION CORE INTEGRATION
# ============================================================


# ============================================================
# V29 PRODUCTION HARDENING & GOVERNANCE INTEGRATION
# ============================================================
try:
    from modules.v29_governance_core import init_v29_db, governance_gate as v29_governance_gate, start_scheduler_once as v29_start_scheduler_once, V29_ENABLE_CRON
    init_v29_db()
    _v29_original_should_send_alert_final = should_send_alert_final
    def should_send_alert_final(symbol, sig, analysis, asset):
        ok, reason = _v29_original_should_send_alert_final(symbol, sig, analysis, asset)
        if not ok:
            return ok, reason
        try:
            gate_ok, gate_detail = v29_governance_gate(symbol, sig, analysis if isinstance(analysis, dict) else {})
            if isinstance(analysis, dict):
                analysis["v29_governance_gate"] = gate_detail
            if not gate_ok:
                return False, "V29 Governance Gate: " + " | ".join(gate_detail.get("reasons") or ["BLOCK"])
        except Exception as e:
            print("V29 governance gate warning:", e)
        return True, "PASS"
    if V29_ENABLE_CRON:
        v29_start_scheduler_once()
except Exception as e:
    print("V29 governance integration warning:", e)
# ============================================================
# END V29 PRODUCTION HARDENING & GOVERNANCE INTEGRATION
# ============================================================


# ============================================================
# V30 INSTITUTIONAL MODEL VALIDATION & PAPER TRADING INTEGRATION
# ============================================================
try:
    from modules.v30_model_validation_core import init_v30_db, validation_gate as v30_validation_gate
    init_v30_db()
    _v30_original_should_send_alert_final = should_send_alert_final
    def should_send_alert_final(symbol, sig, analysis, asset):
        ok, reason = _v30_original_should_send_alert_final(symbol, sig, analysis, asset)
        if not ok:
            return ok, reason
        try:
            gate_ok, gate_detail = v30_validation_gate(symbol, sig, analysis if isinstance(analysis, dict) else {})
            if isinstance(analysis, dict):
                analysis["v30_validation_gate"] = gate_detail
            if not gate_ok:
                return False, "V30 Validation Gate: " + " | ".join(gate_detail.get("reasons") or ["BLOCK"])
        except Exception as e:
            print("V30 validation gate warning:", e)
        return True, "PASS"
except Exception as e:
    print("V30 model validation integration warning:", e)
# ============================================================
# END V30 INSTITUTIONAL MODEL VALIDATION & PAPER TRADING INTEGRATION
# ============================================================



# ============================================================
# V31 ALPHA RESEARCH & PERFORMANCE ATTRIBUTION INTEGRATION
# ============================================================
try:
    from modules.v31_alpha_attribution_core import init_v31_db, alpha_gate as v31_alpha_gate, V31_ALPHA_GATE_MODE
    init_v31_db()
    _v31_original_should_send_alert_final = should_send_alert_final
    def should_send_alert_final(symbol, sig, analysis, asset):
        ok, reason = _v31_original_should_send_alert_final(symbol, sig, analysis, asset)
        if not ok:
            return ok, reason
        try:
            payload = analysis if isinstance(analysis, dict) else {}
            payload.setdefault("symbol", symbol)
            payload.setdefault("side", sig)
            gate_ok, gate_detail = v31_alpha_gate(payload)
            if isinstance(analysis, dict):
                analysis["v31_alpha_gate"] = gate_detail
            if V31_ALPHA_GATE_MODE == "block" and not gate_ok:
                return False, "V31 Alpha Gate: alpha score below threshold"
        except Exception as e:
            print("V31 alpha gate warning:", e)
        return True, "PASS"
except Exception as e:
    print("V31 alpha attribution integration warning:", e)
# ============================================================
# END V31 ALPHA RESEARCH & PERFORMANCE ATTRIBUTION INTEGRATION
# ============================================================


# ============================================================
# V31 FINAL MAIN RUNNER
# Keep this at the end so every appended route/gate is loaded before Flask starts.
# ============================================================
# Start background workers when imported by Gunicorn/Railway.
start_production_workers_once()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
