import os
import json
import math
import random
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, request, jsonify, Response, redirect

try:
    import psycopg2
    import psycopg2.extras
except Exception:
    psycopg2 = None

app = Flask(__name__)

# ============================================================
# V22 PROFESSIONAL EDITION — TRUE POSTGRESQL CORE
# ฟรี: Railway + Railway PostgreSQL + Flask Dashboard
# ============================================================

PORT = int(os.getenv("PORT", "8000"))
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DB_PATH = os.getenv("DB_PATH", "/app/signals.db")
APP_VERSION = "V22 Professional PostgreSQL Core"

ACCOUNT_EQUITY = float(os.getenv("ACCOUNT_EQUITY", "10000"))
RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", "1.0"))
MAX_PORTFOLIO_HEAT_PCT = float(os.getenv("MAX_PORTFOLIO_HEAT_PCT", "6.0"))
MAX_DAILY_LOSS_R = float(os.getenv("MAX_DAILY_LOSS_R", "-3.0"))
MAX_CONSECUTIVE_LOSSES = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "5"))
MONTE_CARLO_RUNS = int(os.getenv("MONTE_CARLO_RUNS", "1000"))
MONTE_CARLO_TRADES = int(os.getenv("MONTE_CARLO_TRADES", "100"))

USE_POSTGRES = bool(DATABASE_URL)

# Railway/Heroku sometimes use postgres://. psycopg2 accepts both, but normalize safely.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]


# ============================================================
# TIME / UTILS
# ============================================================
def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_th_text() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")


def fnum(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == "":
            return default
        return float(str(x).replace(",", "").strip())
    except Exception:
        return default


def inum(x: Any, default: int = 0) -> int:
    try:
        if x is None or x == "":
            return default
        return int(float(str(x).replace(",", "").strip()))
    except Exception:
        return default


def fmt(x: Any, digits: int = 2) -> str:
    try:
        return f"{float(x):,.{digits}f}"
    except Exception:
        return "0.00"


def side_norm(x: Any) -> str:
    s = str(x or "CALL").strip().upper()
    if s in {"PUT", "P", "SHORT", "SELL"}:
        return "PUT"
    return "CALL"


def rowdict(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    try:
        return dict(row)
    except Exception:
        return {}


# ============================================================
# DATABASE ADAPTER
# ============================================================
def pg_available() -> bool:
    return USE_POSTGRES and psycopg2 is not None


def convert_placeholders(sql: str) -> str:
    # Convert SQLite-style ? placeholders to psycopg2 %s.
    return sql.replace("?", "%s")


def get_conn():
    if USE_POSTGRES:
        if psycopg2 is None:
            raise RuntimeError("DATABASE_URL is set but psycopg2 is not installed. Add psycopg2-binary to requirements.txt")
        return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    conn = sqlite3.connect(DB_PATH, timeout=60, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=60000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except Exception:
        pass
    return conn


def fetch_all(sql: str, params: Tuple = ()) -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(convert_placeholders(sql) if USE_POSTGRES else sql, params)
        rows = cur.fetchall()
        return [rowdict(r) for r in rows]
    finally:
        conn.close()


def fetch_one(sql: str, params: Tuple = ()) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(convert_placeholders(sql) if USE_POSTGRES else sql, params)
        r = cur.fetchone()
        return rowdict(r) if r else None
    finally:
        conn.close()


def execute(sql: str, params: Tuple = ()) -> None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(convert_placeholders(sql) if USE_POSTGRES else sql, params)
        conn.commit()
    finally:
        conn.close()


def execute_returning_id(sql_no_returning: str, params: Tuple = ()) -> int:
    conn = get_conn()
    try:
        cur = conn.cursor()
        if USE_POSTGRES:
            cur.execute(convert_placeholders(sql_no_returning + " RETURNING id"), params)
            row = cur.fetchone()
            new_id = int(row["id"])
        else:
            cur.execute(sql_no_returning, params)
            new_id = int(cur.lastrowid)
        conn.commit()
        return new_id
    finally:
        conn.close()


# ============================================================
# SCHEMA
# ============================================================
def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()
    try:
        if USE_POSTGRES:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trade_journal (
                    id SERIAL PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    created_ts TEXT NOT NULL,
                    updated_at TEXT,
                    symbol TEXT NOT NULL,
                    asset_type TEXT DEFAULT 'US_STOCK',
                    side TEXT NOT NULL,
                    strategy TEXT DEFAULT 'MANUAL',
                    entry_price DOUBLE PRECISION NOT NULL DEFAULT 0,
                    stop_price DOUBLE PRECISION NOT NULL DEFAULT 0,
                    target_price DOUBLE PRECISION NOT NULL DEFAULT 0,
                    exit_price DOUBLE PRECISION,
                    qty DOUBLE PRECISION NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    r_multiple DOUBLE PRECISION NOT NULL DEFAULT 0,
                    result_pct DOUBLE PRECISION NOT NULL DEFAULT 0,
                    pnl DOUBLE PRECISION NOT NULL DEFAULT 0,
                    source TEXT DEFAULT 'manual',
                    notes TEXT,
                    regime TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS closed_outcomes (
                    id SERIAL PRIMARY KEY,
                    trade_id INTEGER UNIQUE,
                    created_at TEXT NOT NULL,
                    closed_at TEXT NOT NULL,
                    symbol TEXT,
                    asset_type TEXT,
                    side TEXT,
                    strategy TEXT,
                    entry_price DOUBLE PRECISION,
                    exit_price DOUBLE PRECISION,
                    stop_price DOUBLE PRECISION,
                    target_price DOUBLE PRECISION,
                    qty DOUBLE PRECISION,
                    result TEXT,
                    result_pct DOUBLE PRECISION,
                    r_multiple DOUBLE PRECISION,
                    pnl DOUBLE PRECISION,
                    holding_minutes INTEGER DEFAULT 0,
                    source TEXT,
                    notes TEXT,
                    regime TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS strategy_performance (
                    strategy TEXT PRIMARY KEY,
                    trades INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    losses INTEGER DEFAULT 0,
                    breakeven INTEGER DEFAULT 0,
                    win_rate DOUBLE PRECISION DEFAULT 0,
                    avg_win_r DOUBLE PRECISION DEFAULT 0,
                    avg_loss_r DOUBLE PRECISION DEFAULT 0,
                    profit_factor DOUBLE PRECISION DEFAULT 0,
                    expectancy_r DOUBLE PRECISION DEFAULT 0,
                    total_r DOUBLE PRECISION DEFAULT 0,
                    max_win_r DOUBLE PRECISION DEFAULT 0,
                    max_loss_r DOUBLE PRECISION DEFAULT 0,
                    updated_at TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS equity_curve (
                    id SERIAL PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    trade_id INTEGER,
                    symbol TEXT,
                    strategy TEXT,
                    r_multiple DOUBLE PRECISION,
                    equity_r DOUBLE PRECISION,
                    drawdown_r DOUBLE PRECISION
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS risk_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT
                )
            """)
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trade_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    created_ts TEXT NOT NULL,
                    updated_at TEXT,
                    symbol TEXT NOT NULL,
                    asset_type TEXT DEFAULT 'US_STOCK',
                    side TEXT NOT NULL,
                    strategy TEXT DEFAULT 'MANUAL',
                    entry_price REAL NOT NULL DEFAULT 0,
                    stop_price REAL NOT NULL DEFAULT 0,
                    target_price REAL NOT NULL DEFAULT 0,
                    exit_price REAL,
                    qty REAL NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    r_multiple REAL NOT NULL DEFAULT 0,
                    result_pct REAL NOT NULL DEFAULT 0,
                    pnl REAL NOT NULL DEFAULT 0,
                    source TEXT DEFAULT 'manual',
                    notes TEXT,
                    regime TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS closed_outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id INTEGER UNIQUE,
                    created_at TEXT NOT NULL,
                    closed_at TEXT NOT NULL,
                    symbol TEXT,
                    asset_type TEXT,
                    side TEXT,
                    strategy TEXT,
                    entry_price REAL,
                    exit_price REAL,
                    stop_price REAL,
                    target_price REAL,
                    qty REAL,
                    result TEXT,
                    result_pct REAL,
                    r_multiple REAL,
                    pnl REAL,
                    holding_minutes INTEGER DEFAULT 0,
                    source TEXT,
                    notes TEXT,
                    regime TEXT
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
                    trade_id INTEGER,
                    symbol TEXT,
                    strategy TEXT,
                    r_multiple REAL,
                    equity_r REAL,
                    drawdown_r REAL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS risk_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT
                )
            """)
        conn.commit()
    finally:
        conn.close()


# ============================================================
# CORE JOURNAL ENGINE
# ============================================================
def calc_trade_result(side: str, entry: float, stop: float, exit_price: float, qty: float) -> Dict[str, float]:
    side = side_norm(side)
    risk = abs(entry - stop)
    if risk <= 0:
        risk = max(entry * 0.03, 0.01)
    raw = (exit_price - entry) if side == "CALL" else (entry - exit_price)
    r_multiple = raw / risk
    result_pct = (raw / entry * 100.0) if entry else 0.0
    pnl = raw * qty
    return {
        "r_multiple": round(r_multiple, 4),
        "result_pct": round(result_pct, 4),
        "pnl": round(pnl, 4),
    }


def open_trade_from_args(args) -> Dict[str, Any]:
    symbol = str(args.get("symbol") or args.get("ticker") or "NVDA").strip().upper()
    side = side_norm(args.get("side"))
    strategy = str(args.get("strategy") or "MANUAL").strip().upper()
    entry = fnum(args.get("entry") or args.get("entry_price"), 0)
    stop = fnum(args.get("stop") or args.get("stop_price"), 0)
    target = fnum(args.get("target") or args.get("target_price"), 0)
    qty = fnum(args.get("qty"), 1)
    asset_type = str(args.get("asset_type") or "US_STOCK").strip().upper()
    source = str(args.get("source") or "manual").strip()
    notes = str(args.get("notes") or "")[:2000]
    regime = str(args.get("regime") or "")[:100]

    if entry <= 0:
        raise ValueError("entry must be greater than 0")
    if stop <= 0:
        stop = entry * (0.97 if side == "CALL" else 1.03)
    if target <= 0:
        target = entry * (1.05 if side == "CALL" else 0.95)

    # Auto stop check
    st = auto_stop_status()
    if st.get("active"):
        raise ValueError(f"AUTO_STOP_ACTIVE: {st.get('reason')}")

    created_at = now_th_text()
    created_ts = now_utc_iso()

    sql = """
        INSERT INTO trade_journal
        (created_at, created_ts, updated_at, symbol, asset_type, side, strategy,
         entry_price, stop_price, target_price, qty, status, source, notes, regime)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?)
    """
    trade_id = execute_returning_id(sql, (
        created_at, created_ts, created_ts, symbol, asset_type, side, strategy,
        entry, stop, target, qty, source, notes, regime
    ))
    return {"ok": True, "trade_id": trade_id, "symbol": symbol, "side": side, "entry": entry}


def close_trade(trade_id: int, exit_price: float, notes: str = "") -> Dict[str, Any]:
    r = fetch_one("SELECT * FROM trade_journal WHERE id=?", (trade_id,))
    if not r:
        raise ValueError(f"trade_id {trade_id} not found")
    if str(r.get("status", "")).upper() == "CLOSED":
        return {"ok": True, "trade_id": trade_id, "already_closed": True}

    entry = fnum(r.get("entry_price"))
    stop = fnum(r.get("stop_price"))
    qty = fnum(r.get("qty"), 1)
    side = side_norm(r.get("side"))
    res = calc_trade_result(side, entry, stop, exit_price, qty)
    result = "WIN" if res["r_multiple"] > 0 else "LOSS" if res["r_multiple"] < 0 else "BREAKEVEN"
    closed_at = now_th_text()
    updated_at = now_utc_iso()

    execute("""
        UPDATE trade_journal
        SET exit_price=?, status='CLOSED', r_multiple=?, result_pct=?, pnl=?, updated_at=?, notes=?
        WHERE id=?
    """, (
        exit_price, res["r_multiple"], res["result_pct"], res["pnl"], updated_at,
        (notes or r.get("notes") or ""), trade_id
    ))

    # Replace outcome idempotently.
    execute("DELETE FROM closed_outcomes WHERE trade_id=?", (trade_id,))
    execute("""
        INSERT INTO closed_outcomes
        (trade_id, created_at, closed_at, symbol, asset_type, side, strategy,
         entry_price, exit_price, stop_price, target_price, qty, result,
         result_pct, r_multiple, pnl, holding_minutes, source, notes, regime)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        trade_id, r.get("created_at"), closed_at, r.get("symbol"), r.get("asset_type"),
        r.get("side"), r.get("strategy"), entry, exit_price, stop, fnum(r.get("target_price")),
        qty, result, res["result_pct"], res["r_multiple"], res["pnl"], 0,
        r.get("source"), notes or r.get("notes"), r.get("regime")
    ))

    rebuild_analytics()
    return {"ok": True, "trade_id": trade_id, "result": result, **res}


# ============================================================
# ANALYTICS
# ============================================================
def performance_from_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    trades = len(rows)
    rs = [fnum(r.get("r_multiple")) for r in rows]
    wins = [x for x in rs if x > 0]
    losses = [x for x in rs if x < 0]
    breakeven = trades - len(wins) - len(losses)

    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_win / gross_loss if gross_loss else (gross_win if gross_win else 0)
    expectancy = sum(rs) / trades if trades else 0

    return {
        "trades": trades,
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": breakeven,
        "win_rate": round((len(wins) / trades * 100) if trades else 0, 2),
        "avg_win_r": round((sum(wins) / len(wins)) if wins else 0, 3),
        "avg_loss_r": round((sum(losses) / len(losses)) if losses else 0, 3),
        "profit_factor": round(profit_factor, 3),
        "expectancy_r": round(expectancy, 3),
        "total_r": round(sum(rs), 3),
        "max_win_r": round(max(rs), 3) if rs else 0,
        "max_loss_r": round(min(rs), 3) if rs else 0,
    }


def rebuild_analytics() -> None:
    outcomes = fetch_all("SELECT * FROM closed_outcomes ORDER BY id ASC")

    # Strategy performance
    execute("DELETE FROM strategy_performance")
    strategies = sorted(set((r.get("strategy") or "MANUAL") for r in outcomes))
    for st in strategies:
        rows = [r for r in outcomes if (r.get("strategy") or "MANUAL") == st]
        p = performance_from_rows(rows)
        execute("""
            INSERT INTO strategy_performance
            (strategy, trades, wins, losses, breakeven, win_rate, avg_win_r, avg_loss_r,
             profit_factor, expectancy_r, total_r, max_win_r, max_loss_r, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            st, p["trades"], p["wins"], p["losses"], p["breakeven"], p["win_rate"],
            p["avg_win_r"], p["avg_loss_r"], p["profit_factor"], p["expectancy_r"],
            p["total_r"], p["max_win_r"], p["max_loss_r"], now_utc_iso()
        ))

    # Equity curve in R
    execute("DELETE FROM equity_curve")
    equity = 0.0
    peak = 0.0
    for r in outcomes:
        rr = fnum(r.get("r_multiple"))
        equity += rr
        peak = max(peak, equity)
        dd = equity - peak
        execute("""
            INSERT INTO equity_curve
            (created_at, trade_id, symbol, strategy, r_multiple, equity_r, drawdown_r)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (r.get("closed_at") or now_th_text(), r.get("trade_id"), r.get("symbol"), r.get("strategy"), rr, equity, dd))


def drawdown_stats() -> Dict[str, Any]:
    eq = fetch_all("SELECT * FROM equity_curve ORDER BY id ASC")
    if not eq:
        return {"max_dd_r": 0, "current_dd_r": 0, "peak_r": 0, "equity_r": 0}
    vals = [fnum(x.get("equity_r")) for x in eq]
    peak = vals[0]
    max_dd = 0.0
    for v in vals:
        peak = max(peak, v)
        max_dd = min(max_dd, v - peak)
    current_peak = max(vals)
    current_dd = vals[-1] - current_peak
    return {
        "max_dd_r": round(max_dd, 3),
        "current_dd_r": round(current_dd, 3),
        "peak_r": round(current_peak, 3),
        "equity_r": round(vals[-1], 3),
    }


def portfolio_heat() -> Dict[str, Any]:
    opens = fetch_all("SELECT * FROM trade_journal WHERE status='OPEN' ORDER BY id ASC")
    total_risk_pct = 0.0
    by_symbol: Dict[str, float] = {}
    by_strategy: Dict[str, float] = {}

    for r in opens:
        entry = fnum(r.get("entry_price"))
        stop = fnum(r.get("stop_price"))
        qty = fnum(r.get("qty"), 1)
        risk_cash = abs(entry - stop) * qty
        risk_pct = (risk_cash / ACCOUNT_EQUITY * 100.0) if ACCOUNT_EQUITY else 0
        total_risk_pct += risk_pct
        sym = r.get("symbol") or "UNKNOWN"
        st = r.get("strategy") or "MANUAL"
        by_symbol[sym] = by_symbol.get(sym, 0) + risk_pct
        by_strategy[st] = by_strategy.get(st, 0) + risk_pct

    status = "OK"
    if total_risk_pct >= MAX_PORTFOLIO_HEAT_PCT:
        status = "HOT / REDUCE RISK"
    elif total_risk_pct >= MAX_PORTFOLIO_HEAT_PCT * 0.7:
        status = "WARM / CAUTION"

    top_symbol = max(by_symbol.items(), key=lambda x: x[1])[0] if by_symbol else "N/A"
    return {
        "open_positions": len(opens),
        "open_risk_pct": round(total_risk_pct, 2),
        "max_portfolio_heat_pct": MAX_PORTFOLIO_HEAT_PCT,
        "heat_score": round(min(100, (total_risk_pct / MAX_PORTFOLIO_HEAT_PCT * 100) if MAX_PORTFOLIO_HEAT_PCT else 0), 1),
        "status": status,
        "top_symbol": top_symbol,
        "by_symbol": {k: round(v, 2) for k, v in by_symbol.items()},
        "by_strategy": {k: round(v, 2) for k, v in by_strategy.items()},
    }


def auto_stop_status() -> Dict[str, Any]:
    outcomes = fetch_all("SELECT * FROM closed_outcomes ORDER BY id DESC LIMIT 20")
    today = now_th_text()[:10]
    today_r = sum(fnum(r.get("r_multiple")) for r in outcomes if str(r.get("closed_at") or "").startswith(today))

    consec = 0
    for r in outcomes:
        if fnum(r.get("r_multiple")) < 0:
            consec += 1
        else:
            break

    active = False
    reason = ""
    if today_r <= MAX_DAILY_LOSS_R:
        active = True
        reason = f"daily loss {round(today_r,2)}R <= {MAX_DAILY_LOSS_R}R"
    elif consec >= MAX_CONSECUTIVE_LOSSES:
        active = True
        reason = f"{consec} consecutive losses"

    return {
        "active": active,
        "reason": reason or "OK",
        "today_r": round(today_r, 3),
        "consecutive_losses": consec,
        "max_daily_loss_r": MAX_DAILY_LOSS_R,
        "max_consecutive_losses": MAX_CONSECUTIVE_LOSSES,
    }


def position_size(entry: Any, stop: Any, equity: Any = None, risk_pct: Any = None) -> Dict[str, Any]:
    entry = fnum(entry)
    stop = fnum(stop)
    equity = fnum(equity, ACCOUNT_EQUITY)
    risk_pct = fnum(risk_pct, RISK_PER_TRADE_PCT)
    per_unit_risk = abs(entry - stop)
    risk_cash = equity * risk_pct / 100.0
    qty = math.floor(risk_cash / per_unit_risk) if per_unit_risk > 0 else 0
    return {
        "entry": entry,
        "stop": stop,
        "account_equity": equity,
        "risk_pct": risk_pct,
        "risk_cash": round(risk_cash, 2),
        "per_unit_risk": round(per_unit_risk, 4),
        "qty": int(qty),
    }


def market_regime_stats() -> Dict[str, Any]:
    rows = fetch_all("SELECT regime, r_multiple FROM closed_outcomes")
    groups: Dict[str, List[float]] = {}
    for r in rows:
        k = r.get("regime") or "UNKNOWN"
        groups.setdefault(k, []).append(fnum(r.get("r_multiple")))
    out = {}
    for k, vals in groups.items():
        out[k] = {
            "trades": len(vals),
            "win_rate": round(sum(1 for v in vals if v > 0) / len(vals) * 100, 2) if vals else 0,
            "expectancy_r": round(sum(vals) / len(vals), 3) if vals else 0,
        }
    return out


def monte_carlo(runs: Any = None, trades: Any = None) -> Dict[str, Any]:
    runs = inum(runs, MONTE_CARLO_RUNS)
    trades = inum(trades, MONTE_CARLO_TRADES)
    outcomes = fetch_all("SELECT r_multiple FROM closed_outcomes")
    rs = [fnum(r.get("r_multiple")) for r in outcomes]
    if len(rs) < 5:
        return {"ok": False, "message": "Need at least 5 closed trades for Monte Carlo", "closed_trades": len(rs)}

    finals = []
    max_dds = []
    for _ in range(max(1, runs)):
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for _ in range(max(1, trades)):
            equity += random.choice(rs)
            peak = max(peak, equity)
            max_dd = min(max_dd, equity - peak)
        finals.append(equity)
        max_dds.append(max_dd)

    finals.sort()
    max_dds.sort()
    def pct(arr, p):
        idx = min(len(arr)-1, max(0, int(len(arr)*p)))
        return round(arr[idx], 3)

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


def snapshot() -> Dict[str, Any]:
    open_trades = fetch_all("SELECT * FROM trade_journal WHERE status='OPEN' ORDER BY id ASC")
    closed = fetch_all("SELECT * FROM closed_outcomes ORDER BY id ASC")
    perf = performance_from_rows(closed)
    strategy = fetch_all("SELECT * FROM strategy_performance ORDER BY expectancy_r DESC, trades DESC")
    equity = fetch_all("SELECT * FROM equity_curve ORDER BY id ASC")
    return {
        "ok": True,
        "version": APP_VERSION,
        "database": "PostgreSQL" if USE_POSTGRES else "SQLite",
        "_db_path": "DATABASE_URL" if USE_POSTGRES else DB_PATH,
        "open_trades": len(open_trades),
        "closed_outcomes": len(closed),
        "performance": perf,
        "recent_outcomes": closed[-10:],
        "open_trade_rows": open_trades,
        "strategy_performance_db": strategy,
        "equity_curve": equity,
        "v22": {
            "position_sizing": "enabled",
            "drawdown": drawdown_stats(),
            "portfolio_heat": portfolio_heat(),
            "auto_stop": auto_stop_status(),
            "market_regime": market_regime_stats(),
        },
        "sample_open_url": "/v21-6/journal/open?symbol=NVDA&side=CALL&entry=212&stop=205&target=225&strategy=MOMENTUM&qty=1",
        "sample_close_url": "/v21-6/journal/close/1?exit=220",
    }


# ============================================================
# HTML
# ============================================================
CSS = """
body{margin:0;background:#0f172a;color:#e5e7eb;font-family:Arial,Helvetica,sans-serif}
.wrap{max-width:1100px;margin:36px auto;padding:0 18px}
.badge{display:inline-block;background:#2563eb;color:white;border-radius:10px;padding:6px 10px;font-size:13px}
h1{font-size:30px;margin:14px 0 6px}
.nav{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}
.nav a{color:#e5e7eb;text-decoration:none;background:#334155;padding:10px 14px;border-radius:10px}
.nav a.active{background:#2563eb}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}
.metric,.card{background:#1e293b;border:1px solid #334155;border-radius:14px;padding:18px;margin:12px 0}
.label{font-size:12px;text-transform:uppercase;color:#94a3b8}
.value{font-size:28px;font-weight:bold;margin-top:6px}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{border-bottom:1px solid #334155;padding:9px;text-align:left;white-space:nowrap}
th{color:#93c5fd;font-size:12px;text-transform:uppercase}
input,select{width:100%;box-sizing:border-box;background:#0f172a;color:#e5e7eb;border:1px solid #475569;border-radius:8px;padding:10px}
button{background:#2563eb;color:white;border:0;border-radius:9px;padding:11px 16px;cursor:pointer}
pre{background:#020617;border-radius:10px;padding:14px;overflow:auto}
.small{color:#94a3b8;font-size:13px}
.warn{color:#fde68a}.good{color:#86efac}.bad{color:#fca5a5}
"""


def page(title: str, body: str, active: str = "dashboard") -> Response:
    def a(path, name, key):
        return f'<a class="{"active" if active==key else ""}" href="{path}">{name}</a>'
    nav = "".join([
        a("/v21-6/dashboard","Dashboard","dashboard"),
        a("/v21-6/journal","Journal","journal"),
        a("/v21-6/outcomes","Outcomes","outcomes"),
        a("/v21-6/stats","Stats","stats"),
        a("/v21-6/equity","Equity","equity"),
        a("/v22/risk","Risk V22","risk"),
        a("/v21-6/api/snapshot","JSON","json"),
    ])
    html = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{title}</title><style>{CSS}</style></head><body><div class="wrap">
    <span class="badge">{APP_VERSION}</span><h1>{title}</h1>
    <p class="small">Database: <b>{"PostgreSQL" if USE_POSTGRES else "SQLite"}</b> · Research cockpit only. Not investment advice.</p>
    <div class="nav">{nav}</div>{body}</div></body></html>"""
    return Response(html, mimetype="text/html")


def table(rows: List[Dict[str, Any]], cols: List[Tuple[str, str]]) -> str:
    if not rows:
        return "<p class='small'>No records yet.</p>"
    head = "".join(f"<th>{label}</th>" for key, label in cols)
    body = ""
    for r in rows:
        body += "<tr>" + "".join(f"<td>{r.get(key, '')}</td>" for key, label in cols) + "</tr>"
    return f"<div style='overflow:auto'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


# ============================================================
# ROUTES
# ============================================================
@app.route("/")
def root():
    return redirect("/v21-6/dashboard")


@app.route("/health")
def health():
    return jsonify({"ok": True, "version": APP_VERSION, "database": "PostgreSQL" if USE_POSTGRES else "SQLite"})


@app.route("/v21-6")
@app.route("/v21-6/dashboard")
@app.route("/v22")
@app.route("/v22/dashboard")
def dashboard():
    s = snapshot()
    p = s["performance"]
    dd = s["v22"]["drawdown"]
    heat = s["v22"]["portfolio_heat"]
    astop = s["v22"]["auto_stop"]
    body = f"""
    <div class="grid">
      <div class="metric"><div class="label">Open Trades</div><div class="value">{s["open_trades"]}</div></div>
      <div class="metric"><div class="label">Closed Trades</div><div class="value">{s["closed_outcomes"]}</div></div>
      <div class="metric"><div class="label">Profit Factor</div><div class="value">{p["profit_factor"]}</div></div>
      <div class="metric"><div class="label">Expectancy</div><div class="value">{p["expectancy_r"]}R</div></div>
      <div class="metric"><div class="label">Max DD</div><div class="value">{dd["max_dd_r"]}R</div></div>
      <div class="metric"><div class="label">Portfolio Heat</div><div class="value">{heat["open_risk_pct"]}%</div><p>{heat["status"]}</p></div>
      <div class="metric"><div class="label">Auto Stop</div><div class="value">{"ON" if astop["active"] else "OFF"}</div><p>{astop["reason"]}</p></div>
    </div>

    <div class="card">
      <h2>Open Trade Form</h2>
      <form method="get" action="/v21-6/journal/open">
        <div class="grid">
          <label>Symbol<input name="symbol" value="NVDA"></label>
          <label>Side<select name="side"><option>CALL</option><option>PUT</option></select></label>
          <label>Entry<input name="entry" value="212"></label>
          <label>Stop<input name="stop" value="205"></label>
          <label>Target<input name="target" value="225"></label>
          <label>Strategy<input name="strategy" value="MOMENTUM"></label>
          <label>Qty<input name="qty" value="1"></label>
        </div><br><button type="submit">Open Trade</button>
      </form>
    </div>

    <div class="card">
      <h2>Close Trade Form</h2>
      <form method="get" onsubmit="this.action='/v21-6/journal/close/'+this.trade_id.value">
        <div class="grid">
          <label>Trade ID<input name="trade_id" value="1"></label>
          <label>Exit Price<input name="exit" value="220"></label>
        </div><br><button type="submit">Close Trade</button>
      </form>
    </div>

    <div class="card"><h2>Quick Test URLs</h2>
    <pre>/v21-6/journal/open?symbol=NVDA&side=CALL&entry=212&stop=205&target=225&strategy=MOMENTUM&qty=1
/v21-6/journal/close/1?exit=220
/v21-6/api/snapshot
/v21-7/sizing?entry=212&stop=205</pre></div>
    """
    return page("V22 Professional Dashboard", body, "dashboard")


@app.route("/v21-6/journal/open")
@app.route("/v22/journal/open")
def route_open():
    try:
        res = open_trade_from_args(request.args)
        return jsonify({**res, "close_url_example": f"/v21-6/journal/close/{res['trade_id']}?exit=YOUR_EXIT_PRICE"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/v21-6/journal/close/<int:trade_id>")
@app.route("/v22/journal/close/<int:trade_id>")
def route_close(trade_id: int):
    try:
        exit_price = fnum(request.args.get("exit") or request.args.get("exit_price"), 0)
        if exit_price <= 0:
            raise ValueError("exit price is required. Example: /v21-6/journal/close/1?exit=220")
        res = close_trade(trade_id, exit_price, request.args.get("notes") or "")
        return jsonify(res)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/v21-6/journal")
@app.route("/v22/journal")
def route_journal():
    rows = fetch_all("SELECT * FROM trade_journal ORDER BY id DESC")
    cols = [
        ("id","ID"),("symbol","Symbol"),("side","Side"),("strategy","Strategy"),
        ("entry_price","Entry"),("stop_price","Stop"),("target_price","Target"),
        ("exit_price","Exit"),("status","Status"),("r_multiple","R"),("created_at","Entry Time")
    ]
    return page("Real Trade Journal", f"<div class='card'><h2>Real Trade Journal</h2>{table(rows, cols)}</div>", "journal")


@app.route("/v21-6/outcomes")
@app.route("/v22/outcomes")
def route_outcomes():
    rows = fetch_all("SELECT * FROM closed_outcomes ORDER BY id DESC")
    cols = [
        ("trade_id","Trade ID"),("symbol","Symbol"),("side","Side"),("strategy","Strategy"),
        ("entry_price","Entry"),("exit_price","Exit"),("result","Result"),("result_pct","%"),("r_multiple","R"),("pnl","PnL"),("closed_at","Closed")
    ]
    return page("Trade Outcomes", f"<div class='card'><h2>Closed Outcomes</h2>{table(rows, cols)}</div>", "outcomes")


@app.route("/v21-6/stats")
@app.route("/v22/stats")
def route_stats():
    rebuild_analytics()
    rows = fetch_all("SELECT * FROM strategy_performance ORDER BY expectancy_r DESC, trades DESC")
    cols = [
        ("strategy","Strategy"),("trades","Trades"),("wins","Wins"),("losses","Losses"),
        ("win_rate","Win Rate"),("profit_factor","PF"),("expectancy_r","Expectancy R"),("total_r","Total R")
    ]
    return page("Strategy Stats", f"<div class='card'><h2>Win Rate by Setup</h2>{table(rows, cols)}</div>", "stats")


@app.route("/v21-6/equity")
@app.route("/v22/equity")
def route_equity():
    rows = fetch_all("SELECT * FROM equity_curve ORDER BY id ASC")
    cols = [
        ("id","ID"),("created_at","Time"),("trade_id","Trade ID"),("symbol","Symbol"),
        ("strategy","Strategy"),("r_multiple","R"),("equity_r","Equity R"),("drawdown_r","DD R")
    ]
    return page("Equity Curve", f"<div class='card'><h2>Real Equity Curve</h2>{table(rows, cols)}</div>", "equity")


@app.route("/v21-6/json")
@app.route("/v21-6/api/snapshot")
@app.route("/v21-7/api/snapshot")
@app.route("/v22/api/snapshot")
def route_snapshot():
    return jsonify(snapshot())


@app.route("/v21-7/sizing")
@app.route("/v22/sizing")
def route_sizing():
    return jsonify({"ok": True, "position_sizing": position_size(
        request.args.get("entry"), request.args.get("stop"), request.args.get("equity"), request.args.get("risk_pct")
    )})


@app.route("/v21-7/drawdown")
@app.route("/v22/drawdown")
def route_drawdown():
    return jsonify({"ok": True, "drawdown": drawdown_stats()})


@app.route("/v21-7/portfolio-heat")
@app.route("/v22/portfolio-heat")
def route_portfolio_heat():
    return jsonify({"ok": True, "portfolio_heat": portfolio_heat()})


@app.route("/v21-7/setup-stats")
@app.route("/v22/setup-stats")
def route_setup_stats():
    rebuild_analytics()
    return jsonify({"ok": True, "setup_stats": fetch_all("SELECT * FROM strategy_performance ORDER BY expectancy_r DESC, trades DESC")})


@app.route("/v21-7/regime")
@app.route("/v22/regime")
def route_regime():
    return jsonify({"ok": True, "market_regime": market_regime_stats()})


@app.route("/v21-7/auto-stop")
@app.route("/v22/auto-stop")
def route_auto_stop():
    return jsonify({"ok": True, "auto_stop": auto_stop_status()})


@app.route("/v21-7/monte-carlo")
@app.route("/v22/monte-carlo")
def route_monte_carlo():
    return jsonify({"ok": True, "monte_carlo": monte_carlo(request.args.get("runs"), request.args.get("trades"))})


@app.route("/v22/risk")
def route_risk_page():
    s = snapshot()
    body = f"""
    <div class="grid">
      <div class="metric"><div class="label">Position Sizing</div><div class="value">ON</div><p>/v22/sizing?entry=212&stop=205</p></div>
      <div class="metric"><div class="label">Portfolio Heat</div><div class="value">{s["v22"]["portfolio_heat"]["open_risk_pct"]}%</div></div>
      <div class="metric"><div class="label">Max Drawdown</div><div class="value">{s["v22"]["drawdown"]["max_dd_r"]}R</div></div>
      <div class="metric"><div class="label">Auto Stop</div><div class="value">{"ON" if s["v22"]["auto_stop"]["active"] else "OFF"}</div></div>
    </div>
    <div class="card"><h2>Monte Carlo</h2><pre>{json.dumps(monte_carlo(), ensure_ascii=False, indent=2)}</pre></div>
    <div class="card"><h2>Market Regime Analysis</h2><pre>{json.dumps(market_regime_stats(), ensure_ascii=False, indent=2)}</pre></div>
    """
    return page("V22 Risk Engine", body, "risk")


# Init at startup
try:
    init_db()
    rebuild_analytics()
except Exception as e:
    print("V22 init error:", e)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
