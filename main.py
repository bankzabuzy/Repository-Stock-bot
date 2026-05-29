import os
import re
import hmac
import json
import time
import math
import hashlib
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, abort, Response

try:
    import yfinance as yf
except Exception:
    yf = None

try:
    import psycopg2
    import psycopg2.extras
except Exception:
    psycopg2 = None

app = Flask(__name__)

# ============================================================
# V22.10 STRICT SIGNAL ALERTS — US OPTIONS + GOLD ONLY
# - ปิดแจ้งเตือนหุ้นไทย
# - ส่ง LINE เฉพาะสัญญาณเข้มจริง
# - แบ่ง Universe เป็นกลุ่มอุตสาหกรรม
# - ลดการใช้โควต้า LINE ด้วย cooldown + state-change filter
# ============================================================
APP_VERSION = "V22.10 Strict US Options + Gold Alerts"
PORT = int(os.getenv("PORT", "8080"))
DB_PATH = os.getenv("DB_PATH", "/app/signals.db")

LINE_CHANNEL_ACCESS_TOKEN = (
    os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    or os.getenv("LINE_TOKEN")
    or os.getenv("LINE_ACCESS_TOKEN")
    or ""
).strip()
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "").strip()
ALERT_USER_IDS = [x.strip() for x in (os.getenv("ALERT_USER_IDS") or os.getenv("LINE_USER_ID") or os.getenv("LINE_USER_IDS") or "").replace(";", ",").split(",") if x.strip()]

TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "").strip()
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "").strip()
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()

# PostgreSQL auto-detect
DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("DATABASE_PUBLIC_URL")
    or os.getenv("POSTGRES_URL")
    or os.getenv("POSTGRESQL_URL")
    or ""
).strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]
USE_POSTGRES = bool(DATABASE_URL)

# Alert policy defaults: strict enough for LINE free quota
ENABLE_AUTO_ALERTS = os.getenv("ENABLE_AUTO_ALERTS", "true").lower() == "true"
ENABLE_THAI_ALERTS = False  # hard disabled per user request
ENABLE_US_ALERTS = os.getenv("ENABLE_US_ALERTS", "true").lower() == "true"
ENABLE_GOLD_ALERTS = os.getenv("ENABLE_GOLD_ALERTS", "true").lower() == "true"
ENABLE_US_SESSION_ONLY = os.getenv("ENABLE_US_SESSION_ONLY", "true").lower() == "true"
ALLOW_US_PREMARKET_ALERTS = os.getenv("ALLOW_US_PREMARKET_ALERTS", "true").lower() == "true"
ALLOW_GOLD_24H_ALERTS = os.getenv("ALLOW_GOLD_24H_ALERTS", "true").lower() == "true"

# Thailand time; adjust manually if needed
US_PREMARKET_START_TH = os.getenv("US_PREMARKET_START_TH", "15:00")
US_SESSION_START_TH = os.getenv("US_SESSION_START_TH", "20:30")
US_SESSION_END_TH = os.getenv("US_SESSION_END_TH", "04:00")
SIGNAL_SCAN_SECONDS = int(os.getenv("SIGNAL_SCAN_SECONDS", "900"))  # 15 min; lower only if paid LINE plan
SYMBOL_COOLDOWN_MINUTES = int(os.getenv("SYMBOL_COOLDOWN_MINUTES", "240"))
GROUP_COOLDOWN_MINUTES = int(os.getenv("GROUP_COOLDOWN_MINUTES", "60"))
MAX_ALERTS_PER_CYCLE = int(os.getenv("MAX_ALERTS_PER_CYCLE", "3"))
MAX_ALERTS_PER_DAY = int(os.getenv("MAX_ALERTS_PER_DAY", "20"))

# Strict criteria
STRICT_MIN_SCORE_US = int(os.getenv("STRICT_MIN_SCORE_US", "86"))
STRICT_MIN_CONFIDENCE_US = int(os.getenv("STRICT_MIN_CONFIDENCE_US", "64"))
STRICT_MIN_RVOL_US = float(os.getenv("STRICT_MIN_RVOL_US", "1.35"))
STRICT_MIN_ATR_PCT_US = float(os.getenv("STRICT_MIN_ATR_PCT_US", "0.006"))
STRICT_MAX_RSI_CALL = float(os.getenv("STRICT_MAX_RSI_CALL", "68.5"))
STRICT_MIN_RSI_CALL = float(os.getenv("STRICT_MIN_RSI_CALL", "52"))
STRICT_MIN_RSI_PUT = float(os.getenv("STRICT_MIN_RSI_PUT", "32"))
STRICT_MAX_RSI_PUT = float(os.getenv("STRICT_MAX_RSI_PUT", "48"))
STRICT_REQUIRE_TF_CONFIRM = os.getenv("STRICT_REQUIRE_TF_CONFIRM", "true").lower() == "true"
STRICT_REQUIRE_EMA_STACK = os.getenv("STRICT_REQUIRE_EMA_STACK", "true").lower() == "true"
STRICT_REQUIRE_SIGNAL_CHANGE = os.getenv("STRICT_REQUIRE_SIGNAL_CHANGE", "true").lower() == "true"

STRICT_MIN_SCORE_GOLD = int(os.getenv("STRICT_MIN_SCORE_GOLD", "78"))
STRICT_MIN_CONFIDENCE_GOLD = int(os.getenv("STRICT_MIN_CONFIDENCE_GOLD", "58"))
STRICT_MIN_ATR_PCT_GOLD = float(os.getenv("STRICT_MIN_ATR_PCT_GOLD", "0.0015"))

REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 StockBotV22.10"}
CACHE: Dict[str, Tuple[float, Any]] = {}
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "120"))

# ============================================================
# WATCHLIST GROUPS — US Options + Gold only
# ============================================================
WATCHLIST_GROUPS: Dict[str, List[str]] = {
    "mega_cap_options": ["NVDA", "AAPL", "MSFT", "AMZN", "TSLA", "META", "GOOGL", "GOOG", "AMD", "AVGO", "NFLX"],
    "etf_options": ["QQQ", "SPY", "IWM", "DIA", "TQQQ", "SQQQ", "SOXL", "SOXS"],
    "semiconductor": ["TSM", "MRVL", "AMKR", "INTC", "WDC", "AAOI", "AEHR", "AXTI", "MTRN", "LAES", "CRDO"],
    "ai_cloud_software": ["PLTR", "CRWV", "NOW", "SNOW", "CRWD", "DDOG", "NET", "ZETA", "HOOD"],
    "space_defense": ["RKLB", "ASTS", "AVAV", "BKSY", "PL", "KTOS", "UMAC", "ONDS"],
    "energy_nuclear": ["OKLO", "CEG", "VST", "LEU", "UUUU", "EOSE", "PLUG", "IREN", "CIFR", "NBIS"],
    "quantum_growth": ["QBTS", "IONQ", "RGTI", "QUBT"],
    "special_watch": ["DXYZ", "TJX", "IBM", "NVTS", "INFQ", "AAOI"],
    "gold": ["GOLD"],
}

def env_list(name: str, default: str = "") -> List[str]:
    return [x.strip().upper() for x in os.getenv(name, default).split(",") if x.strip()]

EXTRA_US_SYMBOLS = env_list("EXTRA_US_SYMBOLS", "")
for s in EXTRA_US_SYMBOLS:
    WATCHLIST_GROUPS.setdefault("extra", []).append(s)

# optional override for exact universe
_override = env_list("US_OPTIONS_WATCHLIST", "")
if _override:
    WATCHLIST_GROUPS = {"custom_us_options": _override, "gold": ["GOLD"]}

THAI_SUFFIXES = (".BK", ".SET")
THAI_BLOCKLIST = {"SCB", "AOT", "PTT", "CPALL", "KBANK", "BBL", "KTB", "ADVANC", "BDMS", "PTTEP", "DELTA"}
GOLD_WORDS = {"GOLD", "XAU", "XAUUSD", "XAU/USD", "ทอง", "ทองคำ", "ทองคํา"}

# ============================================================
# DB
# ============================================================
def db_conn():
    if USE_POSTGRES:
        if psycopg2 is None:
            raise RuntimeError("DATABASE_URL exists but psycopg2-binary is not installed")
        return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor, connect_timeout=15)
    conn = sqlite3.connect(DB_PATH, timeout=60, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def _q(sql: str) -> str:
    if USE_POSTGRES:
        sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        sql = sql.replace("?", "%s")
    return sql

def execute(sql: str, params: Tuple = ()) -> None:
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(_q(sql), params)
        conn.commit()
    finally:
        conn.close()

def fetch_one(sql: str, params: Tuple = ()) -> Optional[Dict[str, Any]]:
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(_q(sql), params)
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def fetch_all(sql: str, params: Tuple = ()) -> List[Dict[str, Any]]:
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(_q(sql), params)
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def init_db():
    execute("""
    CREATE TABLE IF NOT EXISTS alert_state (
        symbol TEXT PRIMARY KEY,
        last_sent_ts REAL NOT NULL,
        last_signal TEXT,
        last_score INTEGER DEFAULT 0
    )
    """)
    execute("""
    CREATE TABLE IF NOT EXISTS alert_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        symbol TEXT NOT NULL,
        group_name TEXT,
        signal TEXT,
        score INTEGER,
        confidence INTEGER,
        sent INTEGER DEFAULT 0,
        reason TEXT,
        report TEXT
    )
    """)
    execute("""
    CREATE TABLE IF NOT EXISTS cooldown_state (
        key TEXT PRIMARY KEY,
        last_ts REAL NOT NULL
    )
    """)

# ============================================================
# Utils
# ============================================================
def th_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=7)

def now_text() -> str:
    return th_now().strftime("%d/%m/%Y %H:%M")

def safe_float(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None or x == "":
            return default
        return float(str(x).replace(",", "").strip())
    except Exception:
        return default

def fmt(x: Any, d: int = 2) -> str:
    try:
        return f"{float(x):,.{d}f}"
    except Exception:
        return "N/A"

def cache_get(key: str):
    item = CACHE.get(key)
    if not item:
        return None
    ts, val = item
    if time.time() - ts > CACHE_TTL_SECONDS:
        CACHE.pop(key, None)
        return None
    return val

def cache_set(key: str, val: Any):
    CACHE[key] = (time.time(), val)

def parse_hhmm(s: str) -> Tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)

def time_in_window_th(start_hhmm: str, end_hhmm: str) -> bool:
    now = th_now()
    sh, sm = parse_hhmm(start_hhmm)
    eh, em = parse_hhmm(end_hhmm)
    start = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end = now.replace(hour=eh, minute=em, second=0, microsecond=0)
    if end <= start:
        return now >= start or now <= end
    return start <= now <= end

def in_us_alert_window() -> bool:
    if not ENABLE_US_SESSION_ONLY:
        return True
    if ALLOW_US_PREMARKET_ALERTS and time_in_window_th(US_PREMARKET_START_TH, US_SESSION_END_TH):
        return True
    return time_in_window_th(US_SESSION_START_TH, US_SESSION_END_TH)

def is_gold(sym: str) -> bool:
    return sym.upper().replace(" ", "") in GOLD_WORDS

def is_us_symbol_allowed(sym: str) -> bool:
    s = sym.upper().strip()
    if s.endswith(THAI_SUFFIXES):
        return False
    if s in THAI_BLOCKLIST:
        return False
    return bool(re.fullmatch(r"[A-Z0-9]{1,6}", s))

def get_last_state(symbol: str) -> Tuple[float, str, int]:
    row = fetch_one("SELECT last_sent_ts,last_signal,last_score FROM alert_state WHERE symbol=?", (symbol,))
    if not row:
        return 0.0, "", 0
    return float(row.get("last_sent_ts") or 0), str(row.get("last_signal") or ""), int(row.get("last_score") or 0)

def set_last_state(symbol: str, signal: str, score: int):
    now = time.time()
    if USE_POSTGRES:
        execute("""
        INSERT INTO alert_state(symbol,last_sent_ts,last_signal,last_score)
        VALUES(?,?,?,?)
        ON CONFLICT(symbol) DO UPDATE SET last_sent_ts=EXCLUDED.last_sent_ts,last_signal=EXCLUDED.last_signal,last_score=EXCLUDED.last_score
        """, (symbol, now, signal, score))
    else:
        execute("""
        INSERT INTO alert_state(symbol,last_sent_ts,last_signal,last_score)
        VALUES(?,?,?,?)
        ON CONFLICT(symbol) DO UPDATE SET last_sent_ts=excluded.last_sent_ts,last_signal=excluded.last_signal,last_score=excluded.last_score
        """, (symbol, now, signal, score))

def cooldown_ok(key: str, minutes: int) -> bool:
    row = fetch_one("SELECT last_ts FROM cooldown_state WHERE key=?", (key,))
    if not row:
        return True
    return (time.time() - float(row.get("last_ts") or 0)) >= minutes * 60

def set_cooldown(key: str):
    now = time.time()
    if USE_POSTGRES:
        execute("""
        INSERT INTO cooldown_state(key,last_ts) VALUES(?,?)
        ON CONFLICT(key) DO UPDATE SET last_ts=EXCLUDED.last_ts
        """, (key, now))
    else:
        execute("""
        INSERT INTO cooldown_state(key,last_ts) VALUES(?,?)
        ON CONFLICT(key) DO UPDATE SET last_ts=excluded.last_ts
        """, (key, now))

def alerts_sent_today() -> int:
    today = th_now().strftime("%d/%m/%Y")
    row = fetch_one("SELECT COUNT(*) AS c FROM alert_log WHERE created_at LIKE ? AND sent=1", (today + "%",))
    return int(row.get("c") or 0) if row else 0

# ============================================================
# Data sources
# ============================================================
def get_usd_thb_rate() -> float:
    cached = cache_get("USDTHB")
    if cached:
        return float(cached)
    rate = 36.5
    try:
        if yf is not None:
            data = yf.Ticker("USDTHB=X").history(period="5d", interval="1d")
            if data is not None and not data.empty:
                rate = float(data["Close"].dropna().iloc[-1])
    except Exception:
        pass
    cache_set("USDTHB", rate)
    return rate

def yf_series(symbol: str, period="5d", interval="15m") -> Dict[str, Any]:
    if yf is None:
        raise RuntimeError("yfinance is not installed")
    key = f"YF:{symbol}:{period}:{interval}"
    cached = cache_get(key)
    if cached:
        return cached
    ticker = "GC=F" if is_gold(symbol) else symbol
    data = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
    if data is None or data.empty or "Close" not in data:
        raise RuntimeError(f"no market data for {symbol}")
    closes = [float(x) for x in data["Close"].dropna().tolist()]
    highs = [float(x) for x in data["High"].dropna().tolist()]
    lows = [float(x) for x in data["Low"].dropna().tolist()]
    opens = [float(x) for x in data["Open"].dropna().tolist()]
    vols = [float(x) for x in data["Volume"].fillna(0).tolist()] if "Volume" in data else [0.0] * len(closes)
    price = closes[-1]
    prev = closes[-2] if len(closes) >= 2 else price
    out = {"symbol": symbol, "price": price, "previous_close": prev, "change": price - prev, "percent_change": ((price - prev) / prev * 100) if prev else 0, "closes": closes, "highs": highs, "lows": lows, "opens": opens, "volumes": vols, "source": "Yahoo Finance"}
    cache_set(key, out)
    return out

def get_goldtraders_price() -> Dict[str, Any]:
    cached = cache_get("GOLDTRADERS")
    if cached:
        return cached
    out = {"source": "สมาคมค้าทองคำแห่งประเทศไทย / Gold Traders Association"}
    try:
        html = requests.get("https://www.goldtraders.or.th/", headers=REQUEST_HEADERS, timeout=15).text
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)
        nums = []
        for m in re.findall(r"\d{2,3},\d{3}(?:\.\d+)?", text):
            v = safe_float(m)
            if v and 30000 <= v <= 120000:
                nums.append(v)
        # heuristic: buy/sell/ornament around first few values
        if len(nums) >= 2:
            out["bar_buy"] = nums[0]
            out["bar_sell"] = nums[1]
            if len(nums) >= 4:
                out["ornament_sell"] = max(nums[:6])
        date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{4}|\d{1,2}/\d{1,2}/\d{2,4}).{0,40}(\d{1,2}:\d{2})", text)
        if date_match:
            out["updated"] = " ".join(date_match.groups())
    except Exception as e:
        out["error"] = str(e)
    cache_set("GOLDTRADERS", out)
    return out

# ============================================================
# Indicators and scoring
# ============================================================
def ema(vals: List[float], n: int) -> Optional[float]:
    if not vals:
        return None
    k = 2 / (n + 1)
    e = vals[0]
    for v in vals[1:]:
        e = v * k + e * (1 - k)
    return e

def rsi(vals: List[float], n: int = 14) -> Optional[float]:
    if len(vals) < n + 1:
        return None
    gains, losses = [], []
    diffs = [vals[i] - vals[i-1] for i in range(1, len(vals))]
    for d in diffs[-n:]:
        gains.append(max(d, 0))
        losses.append(abs(min(d, 0)))
    avg_gain = sum(gains) / n
    avg_loss = sum(losses) / n
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)

def atr(highs: List[float], lows: List[float], closes: List[float], n: int = 14) -> Optional[float]:
    if len(closes) < n + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
    return sum(trs[-n:]) / min(n, len(trs)) if trs else None

def rvol(volumes: List[float], n: int = 20) -> float:
    if not volumes or len(volumes) < 2:
        return 1.0
    cur = volumes[-1]
    avg = sum(volumes[-(n+1):-1]) / max(1, len(volumes[-(n+1):-1]))
    if avg <= 0:
        return 1.0
    return cur / avg

def timeframe_bias(symbol: str, interval: str) -> str:
    try:
        data = yf_series(symbol, period="10d" if interval != "1d" else "6mo", interval=interval)
        c = data["closes"]
        e6, e12, e50 = ema(c, 6), ema(c, 12), ema(c, 50)
        price = c[-1]
        if e6 and e12 and e50 and price > e6 > e12 > e50:
            return "BULLISH"
        if e6 and e12 and e50 and price < e6 < e12 < e50:
            return "BEARISH"
        return "MIXED"
    except Exception:
        return "MIXED"

def option_strike(price: float, direction: str) -> Tuple[float, float]:
    if price >= 500:
        step = 5.0
    elif price >= 100:
        step = 2.5
    elif price >= 30:
        step = 1.0
    else:
        step = 0.5
    base = round(price / step) * step
    if direction == "CALL":
        buy = base + step if base <= price else base
        sell = buy + (2 * step if step < 5 else step)
    else:
        buy = base - step if base >= price else base
        sell = buy - (2 * step if step < 5 else step)
    return round(buy, 2), round(sell, 2)

def score_symbol(symbol: str) -> Dict[str, Any]:
    is_g = is_gold(symbol)
    data = yf_series("GOLD" if is_g else symbol)
    c, h, l, v = data["closes"], data["highs"], data["lows"], data["volumes"]
    price = float(data["price"])
    e6, e12, e50 = ema(c, 6), ema(c, 12), ema(c, 50)
    r = rsi(c) or 50.0
    a = atr(h, l, c) or 0.0
    rv = rvol(v)
    atr_pct = a / price if price else 0
    change_pct = data.get("percent_change") or 0
    tf_fast = timeframe_bias("GOLD" if is_g else symbol, "15m")
    tf_mid = timeframe_bias("GOLD" if is_g else symbol, "60m")
    tf_confirm_bull = tf_fast == "BULLISH" and tf_mid == "BULLISH"
    tf_confirm_bear = tf_fast == "BEARISH" and tf_mid == "BEARISH"

    bull_stack = bool(e6 and e12 and e50 and price > e6 > e12 > e50)
    bear_stack = bool(e6 and e12 and e50 and price < e6 < e12 < e50)
    range_regime = atr_pct < (0.006 if not is_g else 0.0018)
    regime = "RANGE / LOW VOL" if range_regime else ("UPTREND" if bull_stack else "DOWNTREND" if bear_stack else "MIXED")

    bull_score = 50
    bear_score = 50
    reasons = []
    if bull_stack:
        bull_score += 22; reasons.append("EMA6/12/50 เรียงตัวขาขึ้น")
    if bear_stack:
        bear_score += 22; reasons.append("EMA6/12/50 เรียงตัวขาลง")
    if tf_confirm_bull:
        bull_score += 16; reasons.append("15m และ 1h ยืนยัน Bullish")
    if tf_confirm_bear:
        bear_score += 16; reasons.append("15m และ 1h ยืนยัน Bearish")
    if rv >= STRICT_MIN_RVOL_US:
        bull_score += 8 if change_pct >= 0 else 0
        bear_score += 8 if change_pct < 0 else 0
        reasons.append(f"RVOL {rv:.2f} สูง")
    if change_pct > 0.5:
        bull_score += 5
    if change_pct < -0.5:
        bear_score += 5
    if STRICT_MIN_RSI_CALL <= r <= STRICT_MAX_RSI_CALL:
        bull_score += 8
    elif r > STRICT_MAX_RSI_CALL:
        bull_score -= 10; reasons.append("RSI สูงเกินไป ลดความมั่นใจฝั่ง CALL")
    if STRICT_MIN_RSI_PUT <= r <= STRICT_MAX_RSI_PUT:
        bear_score += 8
    elif r < STRICT_MIN_RSI_PUT:
        bear_score -= 8
    if range_regime:
        bull_score -= 8; bear_score -= 8; reasons.append("ตลาด Range/Low Vol ลดความน่าเชื่อถือ")
    if not is_g and atr_pct < STRICT_MIN_ATR_PCT_US:
        bull_score -= 7; bear_score -= 7; reasons.append("ATR% ต่ำเกินไป ระยะทำกำไรแคบ")
    if is_g and atr_pct < STRICT_MIN_ATR_PCT_GOLD:
        bull_score -= 7; bear_score -= 7

    direction = "NEUTRAL"
    score = max(bull_score, bear_score)
    if bull_score >= bear_score + 8:
        direction = "CALL"
    elif bear_score >= bull_score + 8:
        direction = "PUT"
    else:
        score = min(score, 64)
    score = max(0, min(100, int(round(score))))
    confidence = int(max(35, min(78, 40 + (score - 50) * 0.65)))
    risk_grade = "A" if score >= 90 and confidence >= 68 else "B" if score >= 84 else "C" if score >= 72 else "D"
    buy_strike, sell_strike = option_strike(price, direction if direction in ("CALL", "PUT") else "CALL")

    return {
        "symbol": symbol,
        "asset_type": "GOLD" if is_g else "US_STOCK",
        "price": price,
        "change_pct": change_pct,
        "score": score,
        "confidence": confidence,
        "direction": direction,
        "risk_grade": risk_grade,
        "regime": regime,
        "tf_fast": tf_fast,
        "tf_mid": tf_mid,
        "tf_confirm": tf_confirm_bull or tf_confirm_bear,
        "ema6": e6, "ema12": e12, "ema50": e50,
        "rsi": r, "atr": a, "atr_pct": atr_pct, "rvol": rv,
        "bull_stack": bull_stack,
        "bear_stack": bear_stack,
        "buy_strike": buy_strike,
        "sell_strike": sell_strike,
        "reasons": reasons[:6],
        "source": data.get("source", "Yahoo Finance"),
    }

def strict_alert_pass(x: Dict[str, Any]) -> Tuple[bool, str]:
    symbol = x["symbol"]
    if x["asset_type"] == "US_STOCK":
        if not ENABLE_US_ALERTS:
            return False, "US alerts disabled"
        if not in_us_alert_window():
            return False, "outside US session/premarket window"
        if x["score"] < STRICT_MIN_SCORE_US:
            return False, f"score {x['score']} < {STRICT_MIN_SCORE_US}"
        if x["confidence"] < STRICT_MIN_CONFIDENCE_US:
            return False, f"confidence {x['confidence']} < {STRICT_MIN_CONFIDENCE_US}"
        if x["risk_grade"] not in ("A", "B"):
            return False, f"risk grade {x['risk_grade']} not A/B"
        if x["direction"] not in ("CALL", "PUT"):
            return False, "no clear option direction"
        if STRICT_REQUIRE_TF_CONFIRM and not x["tf_confirm"]:
            return False, "15m/1h not confirmed"
        if STRICT_REQUIRE_EMA_STACK:
            if x["direction"] == "CALL" and not x["bull_stack"]:
                return False, "CALL but EMA bull stack not confirmed"
            if x["direction"] == "PUT" and not x["bear_stack"]:
                return False, "PUT but EMA bear stack not confirmed"
        if x["rvol"] < STRICT_MIN_RVOL_US:
            return False, f"RVOL {x['rvol']:.2f} < {STRICT_MIN_RVOL_US}"
        if x["atr_pct"] < STRICT_MIN_ATR_PCT_US:
            return False, f"ATR% {x['atr_pct']:.3%} too low"
        if x["direction"] == "CALL" and not (STRICT_MIN_RSI_CALL <= x["rsi"] <= STRICT_MAX_RSI_CALL):
            return False, f"CALL RSI {x['rsi']:.1f} outside strict zone"
        if x["direction"] == "PUT" and not (STRICT_MIN_RSI_PUT <= x["rsi"] <= STRICT_MAX_RSI_PUT):
            return False, f"PUT RSI {x['rsi']:.1f} outside strict zone"
    elif x["asset_type"] == "GOLD":
        if not ENABLE_GOLD_ALERTS:
            return False, "gold alerts disabled"
        if not ALLOW_GOLD_24H_ALERTS and not in_us_alert_window():
            return False, "gold outside allowed window"
        if x["score"] < STRICT_MIN_SCORE_GOLD:
            return False, f"gold score {x['score']} < {STRICT_MIN_SCORE_GOLD}"
        if x["confidence"] < STRICT_MIN_CONFIDENCE_GOLD:
            return False, f"gold confidence {x['confidence']} < {STRICT_MIN_CONFIDENCE_GOLD}"
        if x["direction"] not in ("CALL", "PUT"):
            return False, "gold no clear bias"
        if STRICT_REQUIRE_TF_CONFIRM and not x["tf_confirm"]:
            return False, "gold TF not confirmed"
        if x["atr_pct"] < STRICT_MIN_ATR_PCT_GOLD:
            return False, "gold ATR too low"
    else:
        return False, "unsupported asset"

    last_ts, last_sig, last_score = get_last_state(symbol)
    if time.time() - last_ts < SYMBOL_COOLDOWN_MINUTES * 60:
        return False, "symbol cooldown active"
    current_sig = f"{x['direction']}:{x['risk_grade']}"
    if STRICT_REQUIRE_SIGNAL_CHANGE and last_sig == current_sig and abs(x["score"] - last_score) < 4:
        return False, "same signal already sent"
    if alerts_sent_today() >= MAX_ALERTS_PER_DAY:
        return False, "daily LINE alert cap reached"
    return True, "PASS"

# ============================================================
# Report + LINE
# ============================================================
def build_report(x: Dict[str, Any], group_name: str = "") -> str:
    sym = x["symbol"]
    is_g = x["asset_type"] == "GOLD"
    if is_g:
        gt = get_goldtraders_price()
        thb = get_usd_thb_rate()
        thb_oz = x["price"] * thb
        thai_block = (
            f"\n🇹🇭 เทียบเงินบาท: {fmt(thb_oz,0)} บาท/ออนซ์"
            f"\n🏆 ราคาทองไทย"
            f"\nทองแท่งรับซื้อ: {fmt(gt.get('bar_buy'),0)} บาท"
            f"\nทองแท่งขายออก: {fmt(gt.get('bar_sell'),0)} บาท"
            f"\nทองรูปพรรณขายออก: {fmt(gt.get('ornament_sell'),0)} บาท"
            f"\nแหล่งราคา: {gt.get('source','สมาคมค้าทองคำแห่งประเทศไทย')}"
        )
    else:
        thai_block = ""
    opt = ""
    if not is_g and x["direction"] in ("CALL", "PUT"):
        if x["direction"] == "CALL":
            spread = f"Bull Call Spread\nBuy {fmt(x['buy_strike'],2)}C\nSell {fmt(x['sell_strike'],2)}C"
        else:
            spread = f"Bear Put Spread\nBuy {fmt(x['buy_strike'],2)}P\nSell {fmt(x['sell_strike'],2)}P"
        opt = f"""
\n🧠 Options Risk Engine V22.10
Setup: {x['direction']} / Strict Confirmed
Strike แนะนำ: {fmt(x['buy_strike'],2)}{'C' if x['direction']=='CALL' else 'P'}
Model Confidence: {x['confidence']}%

Spread Scanner:
{spread}
ข้อควรระวัง: ไม่มี Delta/IV/OI จริง ใช้ underlying/ATR/Trend/RVOL แบบเข้มงวด
"""
    reasons = "\n".join([f"- {r}" for r in x.get("reasons", [])]) or "- ผ่านเงื่อนไขเข้มงวดของระบบ"
    return f"""🚨 V22.10 STRICT ALERT

📊 {sym} {'ทองคำ' if is_g else 'US Options Watch'}
กลุ่ม: {group_name or '-'}
แหล่งข้อมูล: {x.get('source','Yahoo Finance')}
เวลาไทย: {now_text()}

ราคา: {fmt(x['price'],2)}
เปลี่ยนแปลง: {fmt(x.get('change_pct'),2)}%

V22 Market Score: {x['score']}/100
Model Confidence: {x['confidence']}%
Signal: {x['direction']}
Risk Grade: {x['risk_grade']}
Market Regime: {x['regime']}
Trend Alignment: 15m={x['tf_fast']} / 1h={x['tf_mid']}

📈 Technical
EMA6: {fmt(x['ema6'],2)}
EMA12: {fmt(x['ema12'],2)}
EMA50: {fmt(x['ema50'],2)}
RSI14: {fmt(x['rsi'],2)}
ATR14: {fmt(x['atr'],2)}
ATR%: {x['atr_pct']:.2%}
RVOL: {fmt(x['rvol'],2)}{thai_block}{opt}

เหตุผลหลัก:
{reasons}

หมายเหตุ: ไม่ใช่คำแนะนำการลงทุน ระบบส่งเฉพาะสัญญาณที่ผ่านตัวกรองเข้มงวดเพื่อลดสแปม LINE
""".strip()

def push_line(text: str) -> Tuple[bool, str]:
    if not LINE_CHANNEL_ACCESS_TOKEN:
        return False, "missing LINE token"
    if not ALERT_USER_IDS:
        return False, "missing ALERT_USER_IDS / LINE_USER_ID"
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}", "Content-Type": "application/json"}
    ok_all = True
    msg = []
    for uid in ALERT_USER_IDS:
        payload = {"to": uid, "messages": [{"type": "text", "text": text[:4900]}]}
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=15)
            if r.status_code >= 300:
                ok_all = False
                msg.append(f"{uid}:{r.status_code}:{r.text[:160]}")
            else:
                msg.append(f"{uid}:ok")
        except Exception as e:
            ok_all = False
            msg.append(f"{uid}:{e}")
    return ok_all, " | ".join(msg)

def log_alert(x: Dict[str, Any], group: str, sent: bool, reason: str, report: str = ""):
    try:
        execute("""
        INSERT INTO alert_log(created_at,symbol,group_name,signal,score,confidence,sent,reason,report)
        VALUES(?,?,?,?,?,?,?,?,?)
        """, (now_text(), x.get("symbol"), group, x.get("direction"), int(x.get("score") or 0), int(x.get("confidence") or 0), 1 if sent else 0, reason[:300], report[:4900]))
    except Exception as e:
        print("log_alert error", e)

# ============================================================
# Scanner
# ============================================================
def scan_group(group_name: str, symbols: List[str], send: bool = True) -> List[Dict[str, Any]]:
    results = []
    if not cooldown_ok(f"group:{group_name}", GROUP_COOLDOWN_MINUTES):
        return []
    for sym in symbols:
        sym = sym.upper().strip()
        if is_gold(sym):
            pass
        elif not is_us_symbol_allowed(sym):
            continue
        try:
            x = score_symbol(sym)
            passed, reason = strict_alert_pass(x)
            x["passed"] = passed
            x["reason"] = reason
            x["group"] = group_name
            results.append(x)
        except Exception as e:
            results.append({"symbol": sym, "group": group_name, "passed": False, "reason": f"error: {e}"})
    strong = [r for r in results if r.get("passed")]
    strong.sort(key=lambda r: (r.get("score", 0), r.get("confidence", 0)), reverse=True)
    sent_count = 0
    for x in strong[:MAX_ALERTS_PER_CYCLE]:
        report = build_report(x, group_name)
        ok, msg = (False, "dry-run")
        if send:
            ok, msg = push_line(report)
        if ok:
            set_last_state(x["symbol"], f"{x['direction']}:{x['risk_grade']}", int(x["score"]))
            sent_count += 1
        log_alert(x, group_name, ok, msg, report)
    if sent_count > 0:
        set_cooldown(f"group:{group_name}")
    return results

def scan_all(send: bool = True) -> Dict[str, Any]:
    if not ENABLE_AUTO_ALERTS and send:
        return {"ok": False, "reason": "ENABLE_AUTO_ALERTS=false"}
    out = {"ok": True, "version": APP_VERSION, "sent_candidates": 0, "groups": {}}
    for group, symbols in WATCHLIST_GROUPS.items():
        results = scan_group(group, symbols, send=send)
        out["groups"][group] = {
            "checked": len(results),
            "passed": len([x for x in results if x.get("passed")]),
            "top": [{"symbol": x.get("symbol"), "score": x.get("score"), "confidence": x.get("confidence"), "direction": x.get("direction"), "reason": x.get("reason")} for x in sorted(results, key=lambda r: r.get("score", 0) or 0, reverse=True)[:5]],
        }
        out["sent_candidates"] += out["groups"][group]["passed"]
    return out

def auto_loop():
    time.sleep(5)
    while True:
        try:
            scan_all(send=True)
        except Exception as e:
            print("auto_loop error", e)
        time.sleep(max(60, SIGNAL_SCAN_SECONDS))

# ============================================================
# LINE webhook commands
# ============================================================
def verify_line_signature(body: bytes, signature: str) -> bool:
    if not LINE_CHANNEL_SECRET:
        return True
    digest = hmac.new(LINE_CHANNEL_SECRET.encode(), body, hashlib.sha256).digest()
    import base64
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature or "")

def reply_line(reply_token: str, text: str):
    if not LINE_CHANNEL_ACCESS_TOKEN or not reply_token:
        return
    requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers={"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}", "Content-Type": "application/json"},
        json={"replyToken": reply_token, "messages": [{"type": "text", "text": text[:4900]}]},
        timeout=15,
    )

def handle_text(text: str) -> str:
    t = (text or "").strip().upper()
    if t in ("PING", "TEST"):
        return f"OK {APP_VERSION}\nDB={'PostgreSQL' if USE_POSTGRES else 'SQLite'}\nLINE quota-saving strict mode active"
    if t in ("SCAN", "สแกน"):
        res = scan_all(send=False)
        return json.dumps(res, ensure_ascii=False)[:4500]
    if t.startswith("SCAN SEND"):
        res = scan_all(send=True)
        return json.dumps(res, ensure_ascii=False)[:4500]
    m = re.search(r"(?:วิเคราะห์|ANALYZE)\s+([A-Z0-9./]+|ทอง|ทองคำ)", text, re.I)
    if not m:
        m = re.fullmatch(r"([A-Z0-9./]{1,10}|ทอง|ทองคำ)", text.strip(), re.I)
    if m:
        sym = m.group(1).upper()
        if sym in GOLD_WORDS or "ทอง" in sym:
            sym = "GOLD"
        if sym.endswith(THAI_SUFFIXES) or sym in THAI_BLOCKLIST:
            return "V22.10 ปิดการแจ้งเตือน/วิเคราะห์หุ้นไทยในโหมด Auto Alert แล้วครับ เน้นเฉพาะหุ้นสหรัฐฯ + ทอง"
        x = score_symbol(sym)
        passed, reason = strict_alert_pass(x)
        x["passed"] = passed; x["reason"] = reason
        report = build_report(x, "manual")
        return report + f"\n\nStrict Alert Check: {'ผ่าน' if passed else 'ไม่ผ่าน'} ({reason})"
    return "คำสั่ง: PING, SCAN, SCAN SEND, วิเคราะห์ NVDA, วิเคราะห์ GOLD"

# ============================================================
# Routes
# ============================================================
@app.route("/")
def home():
    return Response(f"OK\n{APP_VERSION}\nUse /health, /v22/debug-db, /scan/dry-run", mimetype="text/plain")

@app.route("/health")
def health():
    return jsonify({"ok": True, "version": APP_VERSION, "db": "PostgreSQL" if USE_POSTGRES else "SQLite", "auto_alerts": ENABLE_AUTO_ALERTS, "thai_alerts": ENABLE_THAI_ALERTS})

@app.route("/v22/debug-db")
def debug_db():
    try:
        init_db()
        row = fetch_one("SELECT 1 AS ok")
        conn_ok = bool(row)
    except Exception as e:
        conn_ok = False
        err = str(e)
    else:
        err = ""
    return jsonify({
        "ok": conn_ok,
        "error": err,
        "version": APP_VERSION,
        "database": "PostgreSQL" if USE_POSTGRES else "SQLite",
        "database_url_exists": bool(DATABASE_URL),
        "line_token": bool(LINE_CHANNEL_ACCESS_TOKEN),
        "line_secret": bool(LINE_CHANNEL_SECRET),
        "alert_user_ids": len(ALERT_USER_IDS),
        "watchlist_groups": {k: len(v) for k, v in WATCHLIST_GROUPS.items()},
        "strict": {
            "us_score": STRICT_MIN_SCORE_US,
            "us_confidence": STRICT_MIN_CONFIDENCE_US,
            "us_rvol": STRICT_MIN_RVOL_US,
            "cooldown_min": SYMBOL_COOLDOWN_MINUTES,
            "max_alerts_day": MAX_ALERTS_PER_DAY,
            "thai_alerts": ENABLE_THAI_ALERTS,
        }
    })

@app.route("/scan/dry-run")
def scan_dry_run():
    return jsonify(scan_all(send=False))

@app.route("/scan/send")
def scan_send():
    token = request.args.get("token", "")
    if ADMIN_TOKEN and token != ADMIN_TOKEN:
        abort(403)
    return jsonify(scan_all(send=True))

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        return "OK"
    body = request.get_data()
    sig = request.headers.get("X-Line-Signature", "")
    if not verify_line_signature(body, sig):
        abort(400)
    payload = request.get_json(silent=True) or {}
    for event in payload.get("events", []):
        try:
            reply_token = event.get("replyToken")
            msg = event.get("message", {})
            if msg.get("type") == "text":
                reply_line(reply_token, handle_text(msg.get("text", "")))
        except Exception as e:
            print("webhook event error", e)
    return "OK"

@app.route("/json")
def json_status():
    return jsonify({"ok": True, "version": APP_VERSION, "database": "PostgreSQL" if USE_POSTGRES else "SQLite", "groups": WATCHLIST_GROUPS})

# ============================================================
# Boot
# ============================================================
try:
    init_db()
except Exception as e:
    print("init_db error", e)

if ENABLE_AUTO_ALERTS:
    threading.Thread(target=auto_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
