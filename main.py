
import os
import json
import math
import random
from datetime import datetime, timedelta, timezone

import requests
import yfinance as yf
from flask import Flask, request, jsonify, Response

try:
    import psycopg2
    import psycopg2.extras
except Exception:
    psycopg2 = None


app = Flask(__name__)

# ============================================================
# V22 PROFESSIONAL EDITION CONFIG
# ============================================================
PORT = int(os.getenv("PORT", "3000"))
DATABASE_URL = os.getenv("DATABASE_URL", "")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

ACCOUNT_EQUITY = float(os.getenv("ACCOUNT_EQUITY", "100000"))
RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", "1.0"))
MAX_PORTFOLIO_HEAT_PCT = float(os.getenv("MAX_PORTFOLIO_HEAT_PCT", "6.0"))
MAX_DAILY_LOSS_R = float(os.getenv("MAX_DAILY_LOSS_R", "-3.0"))
MAX_CONSECUTIVE_LOSSES = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "5"))
AUTO_STOP_HOURS = int(os.getenv("AUTO_STOP_HOURS", "24"))
MONTE_CARLO_RUNS = int(os.getenv("MONTE_CARLO_RUNS", "10000"))
MONTE_CARLO_TRADES = int(os.getenv("MONTE_CARLO_TRADES", "100"))

PORTFOLIO_POSITIONS = os.getenv(
    "PORTFOLIO_POSITIONS",
    "QQQ:20,SPY:20,NVDA:10,AMD:8,MSFT:10,AAPL:8,TSLA:5,XLF:7,XLV:7,CASH:5"
)

ENABLE_AUTO_ALERTS = os.getenv("ENABLE_AUTO_ALERTS", "false").lower() == "true"
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_USER_ID = os.getenv("LINE_USER_ID", "")

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 V22 Professional Stock Bot"
}


# ============================================================
# DATABASE CORE - POSTGRESQL FIRST
# ============================================================
def now_utc():
    return datetime.now(timezone.utc)


def now_text():
    return now_utc().strftime("%Y-%m-%d %H:%M:%S")


def safe_float(x, default=None):
    try:
        if x is None or x == "":
            return default
        return float(str(x).replace(",", "").strip())
    except Exception:
        return default


def safe_int(x, default=0):
    try:
        if x is None or x == "":
            return default
        return int(float(x))
    except Exception:
        return default


def r4(x):
    try:
        if x is None:
            return 0.0
        return round(float(x), 4)
    except Exception:
        return 0.0


def pg_connect():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set. Add Railway PostgreSQL and connect DATABASE_URL.")
    if psycopg2 is None:
        raise RuntimeError("psycopg2-binary is not installed. Check requirements.txt.")
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def db_fetchall(sql, params=None):
    with pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()


def db_fetchone(sql, params=None):
    with pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchone()


def db_execute(sql, params=None, fetch=False):
    with pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            result = cur.fetchone() if fetch else None
            conn.commit()
            return result


def init_db():
    with pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id SERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    symbol TEXT NOT NULL,
                    asset_type TEXT,
                    price NUMERIC,
                    score NUMERIC,
                    bias TEXT,
                    signal_type TEXT,
                    regime TEXT,
                    probability NUMERIC,
                    report TEXT
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS trade_journal (
                    id SERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    symbol TEXT NOT NULL,
                    asset_type TEXT DEFAULT 'US_STOCK',
                    side TEXT NOT NULL,
                    strategy TEXT DEFAULT 'MANUAL',
                    setup TEXT DEFAULT 'MANUAL',
                    market_regime TEXT DEFAULT 'UNKNOWN',
                    entry_price NUMERIC NOT NULL,
                    stop_price NUMERIC,
                    target_price NUMERIC,
                    exit_price NUMERIC,
                    qty NUMERIC DEFAULT 1,
                    status TEXT DEFAULT 'OPEN',
                    result TEXT,
                    result_pct NUMERIC,
                    r_multiple NUMERIC,
                    pnl NUMERIC,
                    signal_score NUMERIC,
                    probability NUMERIC,
                    notes TEXT
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS closed_outcomes (
                    id SERIAL PRIMARY KEY,
                    trade_id INTEGER UNIQUE REFERENCES trade_journal(id) ON DELETE CASCADE,
                    closed_at TIMESTAMPTZ DEFAULT NOW(),
                    symbol TEXT NOT NULL,
                    asset_type TEXT,
                    side TEXT NOT NULL,
                    strategy TEXT,
                    setup TEXT,
                    market_regime TEXT,
                    entry_price NUMERIC NOT NULL,
                    exit_price NUMERIC NOT NULL,
                    stop_price NUMERIC,
                    target_price NUMERIC,
                    qty NUMERIC DEFAULT 1,
                    result TEXT NOT NULL,
                    result_pct NUMERIC,
                    r_multiple NUMERIC NOT NULL,
                    pnl NUMERIC,
                    holding_minutes NUMERIC,
                    notes TEXT
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS strategy_performance (
                    strategy TEXT PRIMARY KEY,
                    trades INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    losses INTEGER DEFAULT 0,
                    breakeven INTEGER DEFAULT 0,
                    win_rate NUMERIC DEFAULT 0,
                    avg_win_r NUMERIC DEFAULT 0,
                    avg_loss_r NUMERIC DEFAULT 0,
                    profit_factor NUMERIC DEFAULT 0,
                    expectancy_r NUMERIC DEFAULT 0,
                    total_r NUMERIC DEFAULT 0,
                    max_win_r NUMERIC DEFAULT 0,
                    max_loss_r NUMERIC DEFAULT 0,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS equity_curve (
                    id SERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    trade_id INTEGER UNIQUE REFERENCES trade_journal(id) ON DELETE CASCADE,
                    symbol TEXT,
                    strategy TEXT,
                    r_multiple NUMERIC NOT NULL,
                    equity_r NUMERIC NOT NULL,
                    drawdown_r NUMERIC NOT NULL
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_positions (
                    symbol TEXT PRIMARY KEY,
                    weight_pct NUMERIC DEFAULT 0,
                    sector TEXT,
                    asset_type TEXT DEFAULT 'US_STOCK',
                    side TEXT DEFAULT 'LONG',
                    risk_pct NUMERIC DEFAULT 0,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS risk_events (
                    id SERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    event_type TEXT NOT NULL,
                    message TEXT,
                    value NUMERIC,
                    meta JSONB
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS risk_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS monte_carlo_results (
                    id SERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    runs INTEGER,
                    trades_per_run INTEGER,
                    sample_size INTEGER,
                    p05 NUMERIC,
                    p50 NUMERIC,
                    p95 NUMERIC,
                    worst_final_r NUMERIC,
                    best_final_r NUMERIC,
                    avg_final_r NUMERIC,
                    avg_max_dd_r NUMERIC,
                    worst_max_dd_r NUMERIC,
                    risk_of_ruin_pct NUMERIC
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS system_logs (
                    id SERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    level TEXT DEFAULT 'INFO',
                    message TEXT,
                    meta JSONB
                );
            """)

        conn.commit()


def log_event(level, message, meta=None):
    try:
        db_execute(
            "INSERT INTO system_logs(level, message, meta) VALUES (%s, %s, %s)",
            (level, message, json.dumps(meta or {}))
        )
    except Exception:
        pass


# ============================================================
# FINANCE HELPERS
# ============================================================
def symbol_sector(symbol):
    s = str(symbol or "").upper()
    m = {
        "NVDA": "TECH", "AMD": "TECH", "AAPL": "TECH", "MSFT": "TECH",
        "QQQ": "TECH", "TSLA": "MEGA_CAP", "AMZN": "MEGA_CAP",
        "GOOGL": "MEGA_CAP", "META": "MEGA_CAP", "AVGO": "TECH",
        "SPY": "INDEX", "IWM": "INDEX", "DIA": "INDEX",
        "XLK": "TECH", "XLF": "FINANCIAL", "XLE": "ENERGY",
        "XLV": "HEALTHCARE", "XLY": "CONSUMER", "XLI": "INDUSTRIAL",
        "GLD": "GOLD", "GOLD": "GOLD", "XAUUSD": "GOLD", "CASH": "CASH",
        "AOT": "THAI_TRAVEL", "PTT": "THAI_ENERGY", "CPALL": "THAI_CONSUMER",
    }
    return m.get(s, "OTHER")


def parse_portfolio_positions(raw=None):
    raw = raw if raw is not None else PORTFOLIO_POSITIONS
    out = []
    for part in str(raw or "").replace(";", ",").split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        sym, weight = part.split(":", 1)
        w = safe_float(weight, 0)
        sym = sym.strip().upper()
        if sym:
            out.append({
                "symbol": sym,
                "weight_pct": w,
                "sector": symbol_sector(sym),
                "asset_type": "CASH" if sym == "CASH" else "US_STOCK",
                "side": "CASH" if sym == "CASH" else "LONG"
            })
    return out


def sync_portfolio_from_env():
    init_db()
    positions = parse_portfolio_positions()
    with pg_connect() as conn:
        with conn.cursor() as cur:
            for p in positions:
                cur.execute("""
                    INSERT INTO portfolio_positions(symbol, weight_pct, sector, asset_type, side, updated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT(symbol) DO UPDATE SET
                        weight_pct=EXCLUDED.weight_pct,
                        sector=EXCLUDED.sector,
                        asset_type=EXCLUDED.asset_type,
                        side=EXCLUDED.side,
                        updated_at=NOW()
                """, (p["symbol"], p["weight_pct"], p["sector"], p["asset_type"], p["side"]))
        conn.commit()


def calc_r(side, entry, stop, exit_price):
    side = str(side or "").upper()
    entry = float(entry)
    exit_price = float(exit_price)
    stop = safe_float(stop)
    if side in ("CALL", "BUY", "LONG"):
        risk = abs(entry - stop) if stop is not None and entry != stop else max(abs(entry) * 0.01, 0.01)
        return (exit_price - entry) / risk
    if side in ("PUT", "SELL", "SHORT"):
        risk = abs(stop - entry) if stop is not None and entry != stop else max(abs(entry) * 0.01, 0.01)
        return (entry - exit_price) / risk
    return 0.0


def result_from_r(r):
    if r > 0:
        return "WIN"
    if r < 0:
        return "LOSS"
    return "BE"


def result_pct(side, entry, exit_price):
    side = str(side or "").upper()
    entry = float(entry)
    exit_price = float(exit_price)
    if entry == 0:
        return 0.0
    if side in ("PUT", "SELL", "SHORT"):
        return ((entry - exit_price) / entry) * 100
    return ((exit_price - entry) / entry) * 100


# ============================================================
# JOURNAL / OUTCOME ENGINE
# ============================================================
def performance_from_rows(rows):
    trades = len(rows)
    r_values = [float(r["r_multiple"] or 0) for r in rows]
    wins = [x for x in r_values if x > 0]
    losses = [x for x in r_values if x < 0]
    bes = [x for x in r_values if x == 0]
    total_win = sum(wins)
    total_loss_abs = abs(sum(losses))
    total_r = sum(r_values)
    win_rate = len(wins) / trades * 100 if trades else 0
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    profit_factor = total_win / total_loss_abs if total_loss_abs > 0 else (total_win if total_win > 0 else 0)
    expectancy = total_r / trades if trades else 0
    return {
        "trades": trades,
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(bes),
        "win_rate": r4(win_rate),
        "avg_win_r": r4(avg_win),
        "avg_loss_r": r4(avg_loss),
        "profit_factor": r4(profit_factor),
        "expectancy_r": r4(expectancy),
        "total_r": r4(total_r),
        "max_win_r": r4(max(wins) if wins else 0),
        "max_loss_r": r4(min(losses) if losses else 0),
        "sample_warning": "Need 50-100 closed trades before trusting statistics." if trades < 50 else ""
    }


def rebuild_strategy_performance():
    init_db()
    with pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT strategy FROM closed_outcomes ORDER BY strategy")
            strategies = cur.fetchall()
            cur.execute("DELETE FROM strategy_performance")

            for s in strategies:
                strategy = s["strategy"] or "UNKNOWN"
                cur.execute("SELECT * FROM closed_outcomes WHERE strategy=%s ORDER BY id ASC", (strategy,))
                rows = cur.fetchall()
                p = performance_from_rows(rows)
                cur.execute("""
                    INSERT INTO strategy_performance
                    (strategy, trades, wins, losses, breakeven, win_rate, avg_win_r, avg_loss_r,
                     profit_factor, expectancy_r, total_r, max_win_r, max_loss_r, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                """, (
                    strategy, p["trades"], p["wins"], p["losses"], p["breakeven"], p["win_rate"],
                    p["avg_win_r"], p["avg_loss_r"], p["profit_factor"], p["expectancy_r"],
                    p["total_r"], p["max_win_r"], p["max_loss_r"]
                ))
        conn.commit()


def rebuild_equity_curve():
    init_db()
    with pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM closed_outcomes ORDER BY id ASC")
            rows = cur.fetchall()
            cur.execute("DELETE FROM equity_curve")
            equity = 0.0
            peak = 0.0
            for r in rows:
                rr = float(r["r_multiple"] or 0)
                equity += rr
                peak = max(peak, equity)
                dd = equity - peak
                cur.execute("""
                    INSERT INTO equity_curve(trade_id, symbol, strategy, r_multiple, equity_r, drawdown_r)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(trade_id) DO UPDATE SET
                        r_multiple=EXCLUDED.r_multiple,
                        equity_r=EXCLUDED.equity_r,
                        drawdown_r=EXCLUDED.drawdown_r
                """, (r["trade_id"], r["symbol"], r["strategy"], rr, equity, dd))
        conn.commit()


def open_trade(data):
    init_db()
    side = str(data.get("side", "CALL")).upper()
    symbol = str(data.get("symbol", "")).upper().strip()
    entry = safe_float(data.get("entry") or data.get("entry_price"))
    stop = safe_float(data.get("stop") or data.get("stop_price"))
    target = safe_float(data.get("target") or data.get("target_price"))
    qty = safe_float(data.get("qty"), 1)

    if not symbol:
        raise ValueError("symbol is required")
    if side not in ("CALL", "PUT", "BUY", "SELL", "LONG", "SHORT"):
        raise ValueError("side must be CALL/PUT/BUY/SELL/LONG/SHORT")
    if entry is None or entry <= 0:
        raise ValueError("entry must be positive")

    sizing = position_sizing(entry, stop or entry * 0.97)
    if auto_stop_status()["active"]:
        raise ValueError("AUTO_STOP_ACTIVE")

    row = db_execute("""
        INSERT INTO trade_journal
        (symbol, asset_type, side, strategy, setup, market_regime,
         entry_price, stop_price, target_price, qty, status,
         signal_score, probability, notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'OPEN',%s,%s,%s)
        RETURNING id
    """, (
        symbol,
        data.get("asset_type", "US_STOCK"),
        side,
        str(data.get("strategy", "MANUAL")).upper(),
        str(data.get("setup", data.get("strategy", "MANUAL"))).upper(),
        data.get("market_regime", data.get("regime", "UNKNOWN")),
        entry,
        stop,
        target,
        qty,
        safe_float(data.get("score")),
        safe_float(data.get("probability") or data.get("prob")),
        data.get("notes", "")
    ), fetch=True)

    return {"ok": True, "trade_id": row["id"], "position_sizing": sizing}


def close_trade(trade_id, exit_price, notes=None):
    init_db()
    trade_id = safe_int(trade_id)
    exit_price = safe_float(exit_price)
    if trade_id <= 0:
        raise ValueError("trade_id is required")
    if exit_price is None or exit_price <= 0:
        raise ValueError("exit must be positive")

    trade = db_fetchone("SELECT * FROM trade_journal WHERE id=%s", (trade_id,))
    if not trade:
        raise ValueError("trade not found")
    if str(trade["status"]).upper() == "CLOSED":
        return {"ok": True, "message": "already closed", "trade_id": trade_id}

    r = calc_r(trade["side"], trade["entry_price"], trade["stop_price"], exit_price)
    result = result_from_r(r)
    rpct = result_pct(trade["side"], trade["entry_price"], exit_price)
    qty = float(trade["qty"] or 1)
    entry = float(trade["entry_price"])
    pnl = (exit_price - entry) * qty if str(trade["side"]).upper() in ("CALL", "BUY", "LONG") else (entry - exit_price) * qty

    holding_minutes = None
    try:
        holding_minutes = (now_utc() - trade["created_at"]).total_seconds() / 60
    except Exception:
        pass

    with pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE trade_journal
                SET updated_at=NOW(), exit_price=%s, status='CLOSED',
                    result=%s, result_pct=%s, r_multiple=%s, pnl=%s,
                    notes=COALESCE(%s, notes)
                WHERE id=%s
            """, (exit_price, result, rpct, r, pnl, notes, trade_id))

            cur.execute("""
                INSERT INTO closed_outcomes
                (trade_id, symbol, asset_type, side, strategy, setup, market_regime,
                 entry_price, exit_price, stop_price, target_price, qty,
                 result, result_pct, r_multiple, pnl, holding_minutes, notes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(trade_id) DO UPDATE SET
                    exit_price=EXCLUDED.exit_price,
                    result=EXCLUDED.result,
                    result_pct=EXCLUDED.result_pct,
                    r_multiple=EXCLUDED.r_multiple,
                    pnl=EXCLUDED.pnl
            """, (
                trade_id, trade["symbol"], trade["asset_type"], trade["side"], trade["strategy"],
                trade["setup"], trade["market_regime"], trade["entry_price"], exit_price,
                trade["stop_price"], trade["target_price"], trade["qty"], result, rpct,
                r, pnl, holding_minutes, notes or trade["notes"]
            ))
        conn.commit()

    rebuild_strategy_performance()
    rebuild_equity_curve()

    return {
        "ok": True,
        "trade_id": trade_id,
        "symbol": trade["symbol"],
        "result": result,
        "result_pct": r4(rpct),
        "r_multiple": r4(r),
        "pnl": r4(pnl)
    }


# ============================================================
# RISK ENGINE
# ============================================================
def position_sizing(entry, stop, equity=None, risk_pct=None):
    equity = safe_float(equity, ACCOUNT_EQUITY)
    risk_pct = safe_float(risk_pct, RISK_PER_TRADE_PCT)
    entry = safe_float(entry)
    stop = safe_float(stop)

    if not entry or not stop or entry <= 0 or stop <= 0 or entry == stop:
        return {"ok": False, "reason": "invalid entry/stop", "qty": 0}

    risk_amount = equity * risk_pct / 100
    unit_risk = abs(entry - stop)
    qty = math.floor(risk_amount / unit_risk)
    position_value = qty * entry
    position_pct = position_value / equity * 100 if equity else 0

    return {
        "ok": True,
        "account_equity": r4(equity),
        "risk_pct": r4(risk_pct),
        "risk_amount": r4(risk_amount),
        "unit_risk": r4(unit_risk),
        "qty": int(max(qty, 0)),
        "position_value": r4(position_value),
        "position_pct": r4(position_pct)
    }


def equity_drawdown():
    init_db()
    rows = db_fetchall("SELECT * FROM equity_curve ORDER BY id ASC")
    if not rows:
        return {"equity_r": 0, "peak_r": 0, "current_dd_r": 0, "max_dd_r": 0, "closed_trades": 0}
    vals = [float(r["equity_r"] or 0) for r in rows]
    peak = max(vals)
    current = vals[-1]
    max_dd = min(float(r["drawdown_r"] or 0) for r in rows)
    return {
        "equity_r": r4(current),
        "peak_r": r4(peak),
        "current_dd_r": r4(current - peak),
        "max_dd_r": r4(max_dd),
        "closed_trades": len(rows)
    }


def portfolio_heat():
    init_db()
    sync_portfolio_from_env()
    static_rows = db_fetchall("SELECT * FROM portfolio_positions ORDER BY weight_pct DESC")
    open_rows = db_fetchall("SELECT * FROM trade_journal WHERE status='OPEN' ORDER BY id DESC")

    sector_exposure = {}
    for p in static_rows:
        sector = p["sector"] or symbol_sector(p["symbol"])
        sector_exposure[sector] = sector_exposure.get(sector, 0) + float(p["weight_pct"] or 0)

    open_risk_pct = 0
    open_positions = []
    for r in open_rows:
        entry = safe_float(r["entry_price"], 0)
        stop = safe_float(r["stop_price"], None)
        qty = safe_float(r["qty"], 1)
        risk_pct = 0
        if entry and stop:
            risk_amount = abs(entry - stop) * qty
            risk_pct = risk_amount / ACCOUNT_EQUITY * 100 if ACCOUNT_EQUITY else 0
        open_risk_pct += risk_pct
        open_positions.append({
            "id": r["id"],
            "symbol": r["symbol"],
            "side": r["side"],
            "strategy": r["strategy"],
            "qty": r4(qty),
            "risk_pct": r4(risk_pct),
            "sector": symbol_sector(r["symbol"])
        })

    top_sector = "N/A"
    top_sector_weight = 0
    for k, v in sector_exposure.items():
        if v > top_sector_weight:
            top_sector = k
            top_sector_weight = v

    heat_score = min(100, open_risk_pct / max(MAX_PORTFOLIO_HEAT_PCT, 0.01) * 100)
    status = "LOW"
    if heat_score >= 80:
        status = "HIGH"
    elif heat_score >= 50:
        status = "MEDIUM"

    return {
        "static_positions": static_rows,
        "sector_exposure": {k: r4(v) for k, v in sector_exposure.items()},
        "top_sector": top_sector,
        "top_sector_weight_pct": r4(top_sector_weight),
        "open_positions": open_positions,
        "open_risk_pct": r4(open_risk_pct),
        "max_heat_pct": MAX_PORTFOLIO_HEAT_PCT,
        "heat_score": r4(heat_score),
        "status": status
    }


def setup_stats():
    rows = db_fetchall("SELECT * FROM closed_outcomes ORDER BY id ASC")
    buckets = {}
    for r in rows:
        key = r["setup"] or r["strategy"] or "UNKNOWN"
        buckets.setdefault(key, []).append(r)
    out = []
    for k, rs in buckets.items():
        out.append({"setup": k, **performance_from_rows(rs)})
    return sorted(out, key=lambda x: (x["expectancy_r"], x["profit_factor"], x["trades"]), reverse=True)


def regime_stats():
    rows = db_fetchall("SELECT * FROM closed_outcomes ORDER BY id ASC")
    buckets = {}
    for r in rows:
        key = r["market_regime"] or "UNKNOWN"
        buckets.setdefault(key, []).append(r)
    out = []
    for k, rs in buckets.items():
        out.append({"market_regime": k, **performance_from_rows(rs)})
    return sorted(out, key=lambda x: (x["expectancy_r"], x["trades"]), reverse=True)


def get_state(key, default=None):
    row = db_fetchone("SELECT value FROM risk_state WHERE key=%s", (key,))
    return row["value"] if row else default


def set_state(key, value):
    db_execute("""
        INSERT INTO risk_state(key, value, updated_at)
        VALUES (%s,%s,NOW())
        ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()
    """, (key, str(value)))


def recent_loss_streak():
    rows = db_fetchall("SELECT r_multiple FROM closed_outcomes ORDER BY id DESC LIMIT 50")
    streak = 0
    for r in rows:
        rr = float(r["r_multiple"] or 0)
        if rr < 0:
            streak += 1
        else:
            break
    return streak


def today_r():
    rows = db_fetchall("SELECT r_multiple FROM closed_outcomes WHERE closed_at::date = CURRENT_DATE")
    return sum(float(r["r_multiple"] or 0) for r in rows)


def auto_stop_status():
    init_db()
    until_raw = get_state("auto_stop_until", "")
    now = now_utc()
    active_until = None
    try:
        if until_raw:
            active_until = datetime.fromisoformat(until_raw.replace("Z", "+00:00"))
    except Exception:
        active_until = None

    if active_until and now < active_until:
        return {
            "active": True,
            "reason": get_state("auto_stop_reason", "Rule Stop"),
            "until": active_until.isoformat(),
            "loss_streak": recent_loss_streak(),
            "today_r": r4(today_r())
        }

    streak = recent_loss_streak()
    tr = today_r()
    reason = None
    if streak >= MAX_CONSECUTIVE_LOSSES:
        reason = f"Consecutive losses >= {MAX_CONSECUTIVE_LOSSES}"
    elif tr <= MAX_DAILY_LOSS_R:
        reason = f"Daily loss reached {MAX_DAILY_LOSS_R}R"

    if reason:
        until = now + timedelta(hours=AUTO_STOP_HOURS)
        set_state("auto_stop_until", until.isoformat())
        set_state("auto_stop_reason", reason)
        db_execute("INSERT INTO risk_events(event_type, message, value, meta) VALUES (%s,%s,%s,%s)",
                   ("AUTO_STOP", reason, tr, json.dumps({"streak": streak})))
        return {"active": True, "reason": reason, "until": until.isoformat(), "loss_streak": streak, "today_r": r4(tr)}

    return {"active": False, "reason": "OK", "until": None, "loss_streak": streak, "today_r": r4(tr)}


def monte_carlo(runs=None, trades_per_run=None):
    init_db()
    runs = int(runs or MONTE_CARLO_RUNS)
    trades_per_run = int(trades_per_run or MONTE_CARLO_TRADES)
    rows = db_fetchall("SELECT r_multiple FROM closed_outcomes ORDER BY id ASC")
    samples = [float(r["r_multiple"] or 0) for r in rows]
    if not samples:
        samples = [1.0, -1.0, 0.5, -0.7, 1.5, -1.0]

    finals, max_dds = [], []
    ruin_count = 0
    for _ in range(runs):
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        ruined = False
        for _t in range(trades_per_run):
            rr = random.choice(samples)
            equity += rr
            peak = max(peak, equity)
            max_dd = min(max_dd, equity - peak)
            if equity <= MAX_DAILY_LOSS_R * 2:
                ruined = True
        if ruined:
            ruin_count += 1
        finals.append(equity)
        max_dds.append(max_dd)

    finals_sorted = sorted(finals)
    def pct(p):
        idx = int(max(0, min(len(finals_sorted)-1, round((p/100)*(len(finals_sorted)-1)))))
        return finals_sorted[idx]

    res = {
        "runs": runs,
        "trades_per_run": trades_per_run,
        "sample_size": len(samples),
        "p05": r4(pct(5)),
        "p50": r4(pct(50)),
        "p95": r4(pct(95)),
        "worst_final_r": r4(min(finals)),
        "best_final_r": r4(max(finals)),
        "avg_final_r": r4(sum(finals)/len(finals)),
        "avg_max_dd_r": r4(sum(max_dds)/len(max_dds)),
        "worst_max_dd_r": r4(min(max_dds)),
        "risk_of_ruin_pct": r4(ruin_count/runs*100),
        "note": "Uses real closed_outcomes if available; fallback synthetic sample if no closed trades."
    }
    db_execute("""
        INSERT INTO monte_carlo_results
        (runs, trades_per_run, sample_size, p05, p50, p95, worst_final_r, best_final_r,
         avg_final_r, avg_max_dd_r, worst_max_dd_r, risk_of_ruin_pct)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (runs, trades_per_run, len(samples), res["p05"], res["p50"], res["p95"], res["worst_final_r"],
          res["best_final_r"], res["avg_final_r"], res["avg_max_dd_r"], res["worst_max_dd_r"], res["risk_of_ruin_pct"]))
    return res


def snapshot():
    init_db()
    rebuild_strategy_performance()
    rebuild_equity_curve()
    closed = db_fetchall("SELECT * FROM closed_outcomes ORDER BY id ASC")
    strategies = db_fetchall("SELECT * FROM strategy_performance ORDER BY expectancy_r DESC, profit_factor DESC")
    equity = db_fetchall("SELECT * FROM equity_curve ORDER BY id ASC")
    open_count = db_fetchone("SELECT COUNT(*) AS c FROM trade_journal WHERE status='OPEN'")["c"]
    return {
        "version": "V22 Professional Edition",
        "database": "PostgreSQL" if DATABASE_URL else "NOT_CONFIGURED",
        "open_trades": open_count,
        "closed_outcomes": len(closed),
        "performance": performance_from_rows(closed),
        "strategy_performance": strategies,
        "equity_curve": equity[-100:],
        "risk": {
            "position_policy": {"account_equity": ACCOUNT_EQUITY, "risk_per_trade_pct": RISK_PER_TRADE_PCT},
            "drawdown": equity_drawdown(),
            "portfolio_heat": portfolio_heat(),
            "auto_stop": auto_stop_status(),
            "setup_stats": setup_stats(),
            "regime_stats": regime_stats(),
        }
    }


# ============================================================
# HTML DASHBOARD
# ============================================================
def html_page(title, body):
    nav = """
    <a href="/v22">Dashboard</a>
    <a href="/v22/journal">Journal</a>
    <a href="/v22/outcomes">Outcomes</a>
    <a href="/v22/strategy">Strategy</a>
    <a href="/v22/equity">Equity</a>
    <a href="/v22/risk">Risk</a>
    <a href="/v22/portfolio">Portfolio</a>
    <a href="/v22/monte-carlo">Monte Carlo</a>
    <a href="/v22/api/snapshot">JSON</a>
    """
    return f"""
    <!doctype html><html><head>
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{title}</title>
    <style>
    body{{margin:0;background:#0f172a;color:#e5e7eb;font-family:Arial,sans-serif}}
    .wrap{{max-width:1240px;margin:auto;padding:24px}}
    .top{{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;flex-wrap:wrap}}
    .badge{{background:#2563eb;color:white;border-radius:12px;padding:8px 12px;font-weight:800;display:inline-block}}
    nav a{{display:inline-block;margin:4px;padding:9px 12px;border-radius:10px;background:#1f2937;color:#dbeafe;text-decoration:none}}
    .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:16px 0}}
    .metric,.card{{background:#1e293b;border:1px solid #334155;border-radius:16px;padding:16px}}
    .label{{font-size:12px;color:#93c5fd;text-transform:uppercase;font-weight:800}}
    .value{{font-size:30px;font-weight:900;margin-top:6px}}
    table{{width:100%;border-collapse:collapse;background:#1e293b;border-radius:16px;overflow:hidden}}
    th,td{{padding:10px;border-bottom:1px solid #334155;text-align:left;font-size:14px}}
    th{{color:#93c5fd;font-size:12px;text-transform:uppercase}}
    pre{{background:#020617;border:1px solid #334155;border-radius:14px;padding:12px;overflow:auto;color:#bbf7d0}}
    .ok{{color:#86efac}} .warn{{color:#fde68a}} .bad{{color:#fca5a5}}
    </style></head><body><div class="wrap">
    <div class="top"><div><span class="badge">V22 Professional</span><h1>{title}</h1><p>PostgreSQL · Journal · Outcomes · Strategy · Equity · Risk · Portfolio · Monte Carlo</p></div><nav>{nav}</nav></div>
    {body}
    <p style="text-align:center;color:#94a3b8;margin-top:32px">Research dashboard only. Not investment advice.</p>
    </div></body></html>
    """


def table(rows, cols, empty="No data"):
    if not rows:
        return f"<table><tr><td>{empty}</td></tr></table>"
    head = "".join(f"<th>{c}</th>" for c in cols)
    body = ""
    for r in rows:
        body += "<tr>" + "".join(f"<td>{r.get(c, '')}</td>" for c in cols) + "</tr>"
    return f"<table><tr>{head}</tr>{body}</table>"


# ============================================================
# ROUTES
# ============================================================
@app.route("/")
def root():
    return Response('<meta http-equiv="refresh" content="0; url=/v22">', mimetype="text/html")


@app.route("/v22/status")
def v22_status():
    try:
        init_db()
        return jsonify({
            "ok": True,
            "version": "V22 Professional Edition",
            "database": "PostgreSQL",
            "database_url_configured": bool(DATABASE_URL),
            "routes": [
                "/v22",
                "/v22/status",
                "/v22/journal",
                "/v22/journal/open?symbol=NVDA&side=CALL&entry=212&stop=205&target=225&strategy=MOMENTUM&qty=1",
                "/v22/journal/close/1?exit=220",
                "/v22/outcomes",
                "/v22/strategy",
                "/v22/equity",
                "/v22/risk",
                "/v22/portfolio",
                "/v22/sizing?entry=212&stop=205",
                "/v22/monte-carlo?runs=10000&trades=100",
                "/v22/api/snapshot"
            ]
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "hint": "Check DATABASE_URL and requirements.txt"}), 500


@app.route("/v22")
@app.route("/v22/dashboard")
def v22_dashboard():
    s = snapshot()
    p = s["performance"]
    dd = s["risk"]["drawdown"]
    heat = s["risk"]["portfolio_heat"]
    astop = s["risk"]["auto_stop"]
    body = f"""
    <div class="grid">
      <div class="metric"><div class="label">Open Trades</div><div class="value">{s["open_trades"]}</div></div>
      <div class="metric"><div class="label">Closed Trades</div><div class="value">{s["closed_outcomes"]}</div></div>
      <div class="metric"><div class="label">Win Rate</div><div class="value">{p["win_rate"]}%</div></div>
      <div class="metric"><div class="label">Profit Factor</div><div class="value">{p["profit_factor"]}</div></div>
      <div class="metric"><div class="label">Expectancy</div><div class="value">{p["expectancy_r"]}R</div></div>
      <div class="metric"><div class="label">Max DD</div><div class="value">{dd["max_dd_r"]}R</div></div>
      <div class="metric"><div class="label">Portfolio Heat</div><div class="value">{heat["heat_score"]}</div><p>{heat["status"]}</p></div>
      <div class="metric"><div class="label">Auto Stop</div><div class="value">{"ON" if astop["active"] else "OFF"}</div><p>{astop["reason"]}</p></div>
    </div>
    <div class="card"><h2>Quick Test</h2><pre>/v22/journal/open?symbol=NVDA&side=CALL&entry=212&stop=205&target=225&strategy=MOMENTUM&qty=1
/v22/journal/close/1?exit=220
/v22/sizing?entry=212&stop=205
/v22/monte-carlo?runs=10000&trades=100</pre></div>
    """
    return html_page("Dashboard", body)


@app.route("/v22/journal/open", methods=["GET", "POST"])
def v22_open():
    try:
        data = dict(request.args) if request.method == "GET" else (request.get_json(silent=True) or {})
        return jsonify(open_trade(data))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/v22/journal/close/<int:trade_id>", methods=["GET", "POST"])
def v22_close(trade_id):
    try:
        data = dict(request.args) if request.method == "GET" else (request.get_json(silent=True) or {})
        return jsonify(close_trade(trade_id, data.get("exit") or data.get("exit_price"), data.get("notes")))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/v22/journal")
def v22_journal():
    init_db()
    rows = db_fetchall("SELECT id, symbol, side, strategy, setup, entry_price, stop_price, target_price, exit_price, status, r_multiple FROM trade_journal ORDER BY id DESC LIMIT 100")
    return html_page("Trade Journal", table(rows, ["id","symbol","side","strategy","setup","entry_price","stop_price","target_price","exit_price","status","r_multiple"], "No journal entries"))


@app.route("/v22/outcomes")
def v22_outcomes():
    init_db()
    rows = db_fetchall("SELECT trade_id, symbol, side, strategy, setup, entry_price, exit_price, result, result_pct, r_multiple, pnl FROM closed_outcomes ORDER BY id DESC LIMIT 100")
    return html_page("Closed Outcomes", table(rows, ["trade_id","symbol","side","strategy","setup","entry_price","exit_price","result","result_pct","r_multiple","pnl"], "No outcomes"))


@app.route("/v22/strategy")
def v22_strategy():
    rebuild_strategy_performance()
    rows = db_fetchall("SELECT * FROM strategy_performance ORDER BY expectancy_r DESC, profit_factor DESC")
    return html_page("Strategy Performance", table(rows, ["strategy","trades","wins","losses","win_rate","avg_win_r","avg_loss_r","profit_factor","expectancy_r","total_r"], "No strategy stats"))


@app.route("/v22/equity")
def v22_equity():
    rebuild_equity_curve()
    rows = db_fetchall("SELECT id, trade_id, symbol, strategy, r_multiple, equity_r, drawdown_r FROM equity_curve ORDER BY id ASC")
    bars = ""
    if rows:
        vals = [float(r["equity_r"] or 0) for r in rows]
        mn, mx = min(vals), max(vals)
        span = max(mx - mn, 1)
        for v in vals:
            h = 20 + int((v - mn) / span * 140)
            bars += f"<div title='{v:.2f}R' style='display:inline-block;width:10px;height:{h}px;background:#38bdf8;margin-right:4px;border-radius:4px'></div>"
    body = f"<div class='card'><h2>Equity Curve</h2><div style='height:180px;display:flex;align-items:end'>{bars}</div></div>"
    body += table(rows, ["id","trade_id","symbol","strategy","r_multiple","equity_r","drawdown_r"], "No equity curve")
    return html_page("Equity Curve", body)


@app.route("/v22/risk")
def v22_risk():
    dd = equity_drawdown()
    astop = auto_stop_status()
    body = f"""
    <div class="grid">
      <div class="metric"><div class="label">Equity R</div><div class="value">{dd["equity_r"]}R</div></div>
      <div class="metric"><div class="label">Peak R</div><div class="value">{dd["peak_r"]}R</div></div>
      <div class="metric"><div class="label">Current DD</div><div class="value">{dd["current_dd_r"]}R</div></div>
      <div class="metric"><div class="label">Max DD</div><div class="value">{dd["max_dd_r"]}R</div></div>
      <div class="metric"><div class="label">Loss Streak</div><div class="value">{astop["loss_streak"]}</div></div>
      <div class="metric"><div class="label">Today R</div><div class="value">{astop["today_r"]}R</div></div>
      <div class="metric"><div class="label">Auto Stop</div><div class="value">{"ON" if astop["active"] else "OFF"}</div><p>{astop["reason"]}</p></div>
    </div>
    """
    return html_page("Risk Monitor", body)


@app.route("/v22/portfolio")
def v22_portfolio():
    h = portfolio_heat()
    rows = h["open_positions"]
    body = f"""
    <div class="grid">
      <div class="metric"><div class="label">Heat Score</div><div class="value">{h["heat_score"]}</div></div>
      <div class="metric"><div class="label">Status</div><div class="value">{h["status"]}</div></div>
      <div class="metric"><div class="label">Open Risk</div><div class="value">{h["open_risk_pct"]}%</div></div>
      <div class="metric"><div class="label">Top Sector</div><div class="value">{h["top_sector"]}</div><p>{h["top_sector_weight_pct"]}%</p></div>
    </div>
    <div class="card"><h2>Sector Exposure</h2><pre>{json.dumps(h["sector_exposure"], indent=2)}</pre></div>
    """
    body += table(rows, ["id","symbol","side","strategy","qty","risk_pct","sector"], "No open positions")
    return html_page("Portfolio Heat", body)


@app.route("/v22/sizing")
def v22_sizing():
    return jsonify(position_sizing(
        request.args.get("entry"),
        request.args.get("stop"),
        request.args.get("equity") or ACCOUNT_EQUITY,
        request.args.get("risk_pct") or RISK_PER_TRADE_PCT
    ))


@app.route("/v22/setup-stats")
def v22_setup_stats():
    return jsonify({"ok": True, "setup_stats": setup_stats()})


@app.route("/v22/regime")
def v22_regime():
    return jsonify({"ok": True, "regime_stats": regime_stats()})


@app.route("/v22/auto-stop")
def v22_auto_stop():
    return jsonify({"ok": True, "auto_stop": auto_stop_status()})


@app.route("/v22/monte-carlo")
def v22_monte():
    runs = request.args.get("runs")
    trades = request.args.get("trades")
    m = monte_carlo(runs, trades)
    body = f"<div class='card'><h2>Monte Carlo Result</h2><pre>{json.dumps(m, indent=2)}</pre></div>"
    return html_page("Monte Carlo", body)


@app.route("/v22/api/snapshot")
def v22_snapshot():
    try:
        return jsonify(snapshot())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# Optional light quote endpoint using yfinance only, to avoid paid API pressure.
@app.route("/v22/quote/<symbol>")
def v22_quote(symbol):
    try:
        t = yf.Ticker(symbol.upper())
        hist = t.history(period="5d", interval="1d")
        if hist is None or hist.empty:
            return jsonify({"ok": False, "error": "No data"}), 404
        close = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else None
        chg = close - prev if prev else None
        pct = chg / prev * 100 if prev else None
        return jsonify({"ok": True, "symbol": symbol.upper(), "close": close, "change": chg, "percent_change": pct, "source": "yfinance"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    try:
        init_db()
        sync_portfolio_from_env()
        log_event("INFO", "V22 startup ok")
    except Exception as e:
        print("V22 startup warning:", e)
    app.run(host="0.0.0.0", port=PORT)
