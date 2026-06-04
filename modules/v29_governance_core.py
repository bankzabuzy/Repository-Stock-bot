"""
V29 Production Hardening & Governance Core

Adds a production safety layer on top of V28 Fund Validation Core:
- PostgreSQL-ready schema and migration helpers with SQLite fallback.
- Governance API key validation helpers for sensitive routes.
- Alert kill-switch and drawdown circuit breaker.
- Provider health monitor.
- Real cron-style scheduler loop helpers.
- Strategy performance feedback loop based on realised outcomes.

This module is intentionally dependency-light. It uses psycopg2 only when DATABASE_URL
is set to a PostgreSQL URL; otherwise it falls back to SQLite via DB_PATH.
"""
from __future__ import annotations

import os
import json
import time
import math
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:  # Optional; installed on Railway/Render via requirements.txt.
    import psycopg2
    import psycopg2.extras
except Exception:  # pragma: no cover
    psycopg2 = None

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None

from modules import v28_fund_validation_core as v28

V29_VERSION = "V29 Production Hardening & Governance Core"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DB_PATH = os.getenv("DB_PATH", "signals.db")

V29_API_KEY = os.getenv("V29_API_KEY") or os.getenv("ADMIN_TOKEN", "")
V29_REQUIRE_API_KEY = os.getenv("V29_REQUIRE_API_KEY", "true").lower() == "true"
V29_ENABLE_CRON = os.getenv("V29_ENABLE_CRON", "false").lower() == "true"
V29_CRON_INTERVAL_SECONDS = int(os.getenv("V29_CRON_INTERVAL_SECONDS", "900"))
V29_OUTCOME_LIMIT = int(os.getenv("V29_OUTCOME_LIMIT", os.getenv("V28_OUTCOME_CHECK_LIMIT", "100")))
V29_MAX_DAILY_ALERTS = int(os.getenv("V29_MAX_DAILY_ALERTS", "30"))
V29_MAX_DAILY_SYMBOL_ALERTS = int(os.getenv("V29_MAX_DAILY_SYMBOL_ALERTS", "3"))
V29_MAX_LOSS_STREAK = int(os.getenv("V29_MAX_LOSS_STREAK", "4"))
V29_MAX_DRAWDOWN_R = float(os.getenv("V29_MAX_DRAWDOWN_R", "-6.0"))
V29_FEEDBACK_LOOKBACK = int(os.getenv("V29_FEEDBACK_LOOKBACK", "50"))
V29_MIN_PROVIDER_HEALTH_SCORE = int(os.getenv("V29_MIN_PROVIDER_HEALTH_SCORE", "60"))
V29_PROVIDER_CACHE_SECONDS = int(os.getenv("V29_PROVIDER_CACHE_SECONDS", "300"))

_provider_cache: Dict[str, Any] = {"ts": 0.0, "payload": None}
_scheduler_lock = threading.Lock()
_scheduler_started = False


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat(timespec="seconds")


def today_prefix() -> str:
    return now_utc().date().isoformat()


def as_json(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, default=str, sort_keys=True)
    except Exception:
        return json.dumps({"raw": str(obj)}, ensure_ascii=False)


def safe_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if v is None or v == "":
            return default
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def using_postgres() -> bool:
    return bool(DATABASE_URL and DATABASE_URL.startswith(("postgres://", "postgresql://")) and psycopg2 is not None)


class Store:
    def __init__(self) -> None:
        self.pg = using_postgres()

    def connect(self):
        if self.pg:
            conn = psycopg2.connect(DATABASE_URL)
            return conn
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def ph(self) -> str:
        return "%s" if self.pg else "?"

    def serial(self) -> str:
        return "SERIAL PRIMARY KEY" if self.pg else "INTEGER PRIMARY KEY AUTOINCREMENT"

    def json_type(self) -> str:
        return "JSONB" if self.pg else "TEXT"

    def execute(self, sql: str, params: Tuple[Any, ...] = (), fetch: Optional[str] = None):
        conn = self.connect()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if self.pg else conn.cursor()
            cur.execute(sql, params)
            if fetch == "one":
                row = cur.fetchone()
                return dict(row) if row else None
            if fetch == "all":
                rows = cur.fetchall()
                return [dict(r) for r in rows]
            conn.commit()
            try:
                return cur.lastrowid
            except Exception:
                return None
        finally:
            try:
                conn.close()
            except Exception:
                pass


store = Store()


def init_v29_db() -> Dict[str, Any]:
    """Create V29 production tables. Also initializes V28 tables for backward compatibility."""
    v28.init_v28_db()
    idcol = store.serial()
    jtype = store.json_type()
    bool_type = "BOOLEAN" if store.pg else "INTEGER"
    # V28-compatible tables are created here as well so PostgreSQL deployments can
    # receive migrated V28 data and V29 can read outcomes/risk from the same store.
    ddl = [
        f"""
        CREATE TABLE IF NOT EXISTS v28_signal_audit (
            id {idcol},
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            asset_type TEXT,
            side TEXT,
            decision TEXT NOT NULL,
            reason TEXT,
            score REAL,
            confidence REAL,
            trend_strength REAL,
            rvol REAL,
            regime TEXT,
            risk_grade TEXT,
            entry REAL,
            stop_loss REAL,
            tp1 REAL,
            tp2 REAL,
            tp3 REAL,
            risk_r REAL,
            portfolio_gate TEXT,
            portfolio_reason TEXT,
            market_open INTEGER,
            raw_payload TEXT,
            decision_hash TEXT UNIQUE
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS v28_open_signals (
            id {idcol},
            audit_id INTEGER,
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            asset_type TEXT,
            side TEXT NOT NULL,
            entry REAL NOT NULL,
            stop_loss REAL,
            tp1 REAL,
            tp2 REAL,
            tp3 REAL,
            risk_r REAL DEFAULT 1.0,
            score REAL,
            status TEXT DEFAULT 'OPEN',
            max_price REAL,
            min_price REAL,
            last_price REAL,
            last_checked_at TEXT,
            closed_at TEXT,
            outcome TEXT,
            return_r REAL,
            message TEXT
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS v28_signal_outcomes (
            id {idcol},
            signal_id INTEGER NOT NULL,
            checked_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT,
            price REAL,
            outcome TEXT,
            return_r REAL,
            note TEXT
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS v28_portfolio_risk_snapshots (
            id {idcol},
            created_at TEXT NOT NULL,
            candidate_symbol TEXT,
            total_heat_r REAL,
            theme_heat_r REAL,
            max_pair_correlation REAL,
            portfolio_var_r REAL,
            beta_to_spy REAL,
            decision TEXT,
            reasons TEXT,
            snapshot TEXT
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS v28_walk_forward_runs (
            id {idcol},
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            period TEXT,
            interval TEXT,
            train_bars INTEGER,
            test_bars INTEGER,
            windows INTEGER,
            trades INTEGER,
            win_rate REAL,
            expectancy_r REAL,
            total_return_r REAL,
            max_drawdown_r REAL,
            profit_factor REAL,
            pass_fail TEXT,
            config TEXT,
            result_json TEXT
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS v29_system_state (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT NOT NULL,
            updated_by TEXT,
            note TEXT
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS v29_governance_events (
            id {idcol},
            created_at TEXT NOT NULL,
            event_type TEXT NOT NULL,
            severity TEXT DEFAULT 'INFO',
            symbol TEXT,
            decision TEXT,
            reason TEXT,
            payload {jtype}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS v29_provider_health (
            id {idcol},
            checked_at TEXT NOT NULL,
            provider TEXT NOT NULL,
            status TEXT NOT NULL,
            latency_ms REAL,
            score INTEGER,
            error TEXT,
            details {jtype}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS v29_strategy_feedback (
            id {idcol},
            created_at TEXT NOT NULL,
            strategy_key TEXT NOT NULL,
            symbol TEXT,
            trades INTEGER DEFAULT 0,
            win_rate REAL,
            expectancy_r REAL,
            total_return_r REAL,
            max_drawdown_r REAL,
            loss_streak INTEGER,
            weight_multiplier REAL DEFAULT 1.0,
            action TEXT,
            reason TEXT,
            stats {jtype}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS v29_scheduler_runs (
            id {idcol},
            started_at TEXT NOT NULL,
            finished_at TEXT,
            job_name TEXT NOT NULL,
            status TEXT NOT NULL,
            duration_ms REAL,
            rows_processed INTEGER DEFAULT 0,
            error TEXT,
            details {jtype}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS v29_migration_log (
            id {idcol},
            created_at TEXT NOT NULL,
            migration_name TEXT NOT NULL,
            status TEXT NOT NULL,
            details {jtype}
        )
        """,
    ]
    for stmt in ddl:
        store.execute(stmt)
    seed_default_state()
    return {"ok": True, "version": V29_VERSION, "database": "postgresql" if store.pg else "sqlite", "db_path": None if store.pg else DB_PATH}


def seed_default_state() -> None:
    defaults = {
        "alert_kill_switch": os.getenv("V29_ALERT_KILL_SWITCH", "off"),
        "drawdown_circuit_breaker": os.getenv("V29_DRAWDOWN_CIRCUIT_BREAKER", "on"),
        "provider_gate": os.getenv("V29_PROVIDER_GATE", "warn"),  # off|warn|block
        "last_scheduler_heartbeat": "never",
    }
    for k, v in defaults.items():
        if get_state(k) is None:
            set_state(k, v, updated_by="system", note="default seed")


def get_state(key: str) -> Optional[str]:
    ph = store.ph()
    row = store.execute(f"SELECT value FROM v29_system_state WHERE key={ph}", (key,), fetch="one")
    return row.get("value") if row else None


def set_state(key: str, value: str, updated_by: str = "system", note: str = "") -> Dict[str, Any]:
    ph = store.ph()
    if store.pg:
        sql = """
        INSERT INTO v29_system_state(key, value, updated_at, updated_by, note)
        VALUES(%s,%s,%s,%s,%s)
        ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value, updated_at=EXCLUDED.updated_at, updated_by=EXCLUDED.updated_by, note=EXCLUDED.note
        """
    else:
        sql = """
        INSERT INTO v29_system_state(key, value, updated_at, updated_by, note)
        VALUES(?,?,?,?,?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, updated_by=excluded.updated_by, note=excluded.note
        """
    store.execute(sql, (key, value, now_iso(), updated_by, note))
    return {"ok": True, "key": key, "value": value}


def governance_event(event_type: str, severity: str = "INFO", symbol: str = "", decision: str = "", reason: str = "", payload: Any = None) -> None:
    ph = store.ph()
    store.execute(
        f"INSERT INTO v29_governance_events(created_at,event_type,severity,symbol,decision,reason,payload) VALUES({ph},{ph},{ph},{ph},{ph},{ph},{ph})",
        (now_iso(), event_type, severity, symbol, decision, reason, as_json(payload or {})),
    )


def require_api_key(headers: Dict[str, str], args: Dict[str, Any] = None) -> Tuple[bool, str]:
    if not V29_REQUIRE_API_KEY:
        return True, "API key disabled by config"
    if not V29_API_KEY:
        return False, "V29_API_KEY or ADMIN_TOKEN is not configured"
    supplied = ""
    try:
        supplied = headers.get("X-API-Key") or headers.get("X-Admin-Token") or ""
        auth = headers.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            supplied = auth.split(" ", 1)[1].strip()
        if not supplied and args:
            supplied = args.get("api_key") or args.get("token") or ""
    except Exception:
        supplied = ""
    if supplied == V29_API_KEY:
        return True, "PASS"
    return False, "Invalid or missing API key"


def migrate_v28_to_postgres(limit: int = 10000) -> Dict[str, Any]:
    """Best-effort migration from local SQLite V28 tables into PostgreSQL when DATABASE_URL is configured.

    In SQLite mode this is a no-op. This keeps existing deployments safe and makes Railway/Render
    PostgreSQL migration explicit via /v29/migrate.
    """
    init_v29_db()
    if not store.pg:
        return {"ok": True, "mode": "sqlite", "migrated": 0, "note": "DATABASE_URL is not PostgreSQL; no migration needed"}
    if not os.path.exists(DB_PATH):
        return {"ok": True, "mode": "postgresql", "migrated": 0, "note": f"SQLite source not found: {DB_PATH}"}
    src = sqlite3.connect(DB_PATH)
    src.row_factory = sqlite3.Row
    migrated = 0
    tables = ["v28_signal_audit", "v28_open_signals", "v28_signal_outcomes", "v28_portfolio_risk_snapshots", "v28_walk_forward_runs"]
    for table in tables:
        try:
            rows = src.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            if not rows:
                continue
            # Only insert into matching table if it exists with same columns. Ignore duplicates.
            cols = [d[1] for d in src.execute(f"PRAGMA table_info({table})").fetchall()]
            no_id_cols = [c for c in cols if c != "id"]
            placeholders = ",".join([store.ph()] * len(no_id_cols))
            col_sql = ",".join(no_id_cols)
            if store.pg:
                sql = f"INSERT INTO {table}({col_sql}) VALUES({placeholders}) ON CONFLICT DO NOTHING"
            else:
                sql = f"INSERT OR IGNORE INTO {table}({col_sql}) VALUES({placeholders})"
            for r in rows:
                store.execute(sql, tuple(r[c] for c in no_id_cols))
                migrated += 1
        except Exception as e:
            governance_event("migration_warning", "WARN", decision="PARTIAL", reason=f"{table}: {e}")
    src.close()
    store.execute(f"INSERT INTO v29_migration_log(created_at,migration_name,status,details) VALUES({store.ph()},{store.ph()},{store.ph()},{store.ph()})", (now_iso(), "v28_sqlite_to_postgres", "DONE", as_json({"rows": migrated})))
    return {"ok": True, "mode": "postgresql", "migrated": migrated}


def count_rows(table: str, where: str = "", params: Tuple[Any, ...] = ()) -> int:
    sql = f"SELECT COUNT(*) AS n FROM {table} " + (where or "")
    row = store.execute(sql, params, fetch="one")
    return int(row.get("n", 0)) if row else 0


def recent_rows(table: str, limit: int = 50) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    return store.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT {limit}", fetch="all")


def realised_outcomes(limit: int = 200) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 1000))
    return store.execute(f"SELECT * FROM v28_open_signals WHERE status='CLOSED' ORDER BY id DESC LIMIT {limit}", fetch="all")


def compute_drawdown_r(outcomes: List[Dict[str, Any]]) -> float:
    eq = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in reversed(outcomes):
        rr = safe_float(r.get("return_r"), 0.0) or 0.0
        eq += rr
        peak = max(peak, eq)
        max_dd = min(max_dd, eq - peak)
    return round(max_dd, 4)


def current_loss_streak(outcomes: List[Dict[str, Any]]) -> int:
    streak = 0
    for r in outcomes:
        rr = safe_float(r.get("return_r"), 0.0) or 0.0
        if rr < 0:
            streak += 1
        else:
            break
    return streak


def today_alert_counts(symbol: str = "") -> Tuple[int, int]:
    ph = store.ph()
    day = today_prefix() + "%"
    total = count_rows("v28_signal_audit", f"WHERE created_at LIKE {ph} AND decision='PASS'", (day,))
    if symbol:
        sym = count_rows("v28_signal_audit", f"WHERE created_at LIKE {ph} AND decision='PASS' AND symbol={ph}", (day, symbol.upper()))
    else:
        sym = 0
    return total, sym


def provider_health(force: bool = False) -> Dict[str, Any]:
    init_v29_db()
    if not force and _provider_cache.get("payload") and (time.time() - _provider_cache.get("ts", 0)) < V29_PROVIDER_CACHE_SECONDS:
        return _provider_cache["payload"]

    checks: List[Dict[str, Any]] = []

    def add(provider: str, status: str, latency_ms: float = 0.0, score: int = 0, error: str = "", details: Any = None) -> None:
        row = {"provider": provider, "status": status, "latency_ms": round(latency_ms, 2), "score": int(score), "error": error, "details": details or {}}
        checks.append(row)
        ph = store.ph()
        store.execute(
            f"INSERT INTO v29_provider_health(checked_at,provider,status,latency_ms,score,error,details) VALUES({ph},{ph},{ph},{ph},{ph},{ph},{ph})",
            (now_iso(), provider, status, row["latency_ms"], row["score"], error, as_json(details or {})),
        )

    # Yahoo/yfinance check.
    t0 = time.time()
    try:
        if yf is None:
            raise RuntimeError("yfinance unavailable")
        hist = yf.Ticker("SPY").history(period="5d", interval="1d")
        ok = hist is not None and len(hist) > 0
        add("yfinance", "OK" if ok else "DEGRADED", (time.time() - t0) * 1000, 90 if ok else 35, "" if ok else "empty history", {"rows": int(len(hist) if hist is not None else 0)})
    except Exception as e:
        add("yfinance", "DOWN", (time.time() - t0) * 1000, 0, str(e), {})

    # HTTP baseline check. Keeps monitoring generic when vendor API keys are missing.
    t0 = time.time()
    try:
        if requests is None:
            raise RuntimeError("requests unavailable")
        r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/SPY", timeout=8)
        ok = 200 <= r.status_code < 300
        add("http_market_endpoint", "OK" if ok else "DEGRADED", (time.time() - t0) * 1000, 85 if ok else 40, "" if ok else f"HTTP {r.status_code}", {"status_code": r.status_code})
    except Exception as e:
        add("http_market_endpoint", "DOWN", (time.time() - t0) * 1000, 0, str(e), {})

    scores = [c["score"] for c in checks]
    aggregate = int(sum(scores) / len(scores)) if scores else 0
    status = "OK" if aggregate >= 75 else "DEGRADED" if aggregate >= V29_MIN_PROVIDER_HEALTH_SCORE else "DOWN"
    payload = {"ok": status != "DOWN", "version": V29_VERSION, "checked_at": now_iso(), "aggregate_score": aggregate, "status": status, "providers": checks}
    _provider_cache.update({"ts": time.time(), "payload": payload})
    return payload


def feedback_loop(strategy_key: str = "GLOBAL", limit: int = V29_FEEDBACK_LOOKBACK) -> Dict[str, Any]:
    init_v29_db()
    outcomes = realised_outcomes(limit)
    trades = len(outcomes)
    returns = [(safe_float(r.get("return_r"), 0.0) or 0.0) for r in outcomes]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]
    win_rate = (len(wins) / trades * 100.0) if trades else 0.0
    expectancy = (sum(returns) / trades) if trades else 0.0
    total_r = sum(returns)
    max_dd = compute_drawdown_r(outcomes)
    loss_streak = current_loss_streak(outcomes)

    if trades < 10:
        action, multiplier, reason = "LEARN_ONLY", 1.0, "insufficient closed trades"
    elif max_dd <= V29_MAX_DRAWDOWN_R or loss_streak >= V29_MAX_LOSS_STREAK:
        action, multiplier, reason = "REDUCE_OR_PAUSE", 0.5, "drawdown or loss-streak breach"
    elif expectancy > 0.25 and win_rate >= 50:
        action, multiplier, reason = "ALLOW_NORMAL_OR_SCALE", 1.1, "positive validated expectancy"
    elif expectancy < 0:
        action, multiplier, reason = "REDUCE", 0.75, "negative expectancy"
    else:
        action, multiplier, reason = "NORMAL", 1.0, "neutral validation"

    stats = {"trades": trades, "wins": len(wins), "losses": len(losses), "returns_r": returns[:100]}
    ph = store.ph()
    store.execute(
        f"INSERT INTO v29_strategy_feedback(created_at,strategy_key,symbol,trades,win_rate,expectancy_r,total_return_r,max_drawdown_r,loss_streak,weight_multiplier,action,reason,stats) VALUES({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
        (now_iso(), strategy_key, None, trades, round(win_rate, 2), round(expectancy, 4), round(total_r, 4), max_dd, loss_streak, multiplier, action, reason, as_json(stats)),
    )
    return {"ok": True, "version": V29_VERSION, "strategy_key": strategy_key, "trades": trades, "win_rate": round(win_rate, 2), "expectancy_r": round(expectancy, 4), "total_return_r": round(total_r, 4), "max_drawdown_r": max_dd, "loss_streak": loss_streak, "weight_multiplier": multiplier, "action": action, "reason": reason}


def governance_gate(symbol: str, sig: str = "", analysis: Dict[str, Any] = None) -> Tuple[bool, Dict[str, Any]]:
    init_v29_db()
    symbol = str(symbol or "").upper()
    reasons: List[str] = []
    decision = "PASS"

    if get_state("alert_kill_switch") == "on":
        reasons.append("manual alert kill-switch is ON")

    total, sym = today_alert_counts(symbol)
    if total >= V29_MAX_DAILY_ALERTS:
        reasons.append(f"daily alert limit reached: {total}/{V29_MAX_DAILY_ALERTS}")
    if symbol and sym >= V29_MAX_DAILY_SYMBOL_ALERTS:
        reasons.append(f"daily symbol alert limit reached: {symbol} {sym}/{V29_MAX_DAILY_SYMBOL_ALERTS}")

    outcomes = realised_outcomes(V29_FEEDBACK_LOOKBACK)
    dd = compute_drawdown_r(outcomes)
    streak = current_loss_streak(outcomes)
    if get_state("drawdown_circuit_breaker") == "on":
        if dd <= V29_MAX_DRAWDOWN_R:
            reasons.append(f"drawdown circuit breaker: {dd}R <= {V29_MAX_DRAWDOWN_R}R")
        if streak >= V29_MAX_LOSS_STREAK:
            reasons.append(f"loss streak circuit breaker: {streak} >= {V29_MAX_LOSS_STREAK}")

    ph_mode = get_state("provider_gate") or "warn"
    health = provider_health(force=False)
    if health.get("aggregate_score", 0) < V29_MIN_PROVIDER_HEALTH_SCORE:
        msg = f"provider health weak: {health.get('aggregate_score')}/{V29_MIN_PROVIDER_HEALTH_SCORE}"
        if ph_mode == "block":
            reasons.append(msg)
        elif ph_mode == "warn":
            governance_event("provider_health_warning", "WARN", symbol=symbol, decision="WARN", reason=msg, payload=health)

    if reasons:
        decision = "BLOCK"
        governance_event("governance_gate", "WARN", symbol=symbol, decision=decision, reason=" | ".join(reasons), payload={"sig": sig, "analysis_score": (analysis or {}).get("score")})
        return False, {"version": V29_VERSION, "decision": decision, "reasons": reasons, "drawdown_r": dd, "loss_streak": streak, "provider_health": health}

    return True, {"version": V29_VERSION, "decision": decision, "reasons": ["PASS"], "drawdown_r": dd, "loss_streak": streak, "provider_health": {"aggregate_score": health.get("aggregate_score"), "status": health.get("status")}}


def scheduler_run_once() -> Dict[str, Any]:
    init_v29_db()
    started = time.time()
    ph = store.ph()
    run_id = store.execute(
        f"INSERT INTO v29_scheduler_runs(started_at,job_name,status,details) VALUES({ph},{ph},{ph},{ph})",
        (now_iso(), "v29_governance_cron", "RUNNING", as_json({"interval_seconds": V29_CRON_INTERVAL_SECONDS})),
    )
    details: Dict[str, Any] = {}
    status = "OK"
    error = ""
    rows = 0
    try:
        outcome = v28.run_outcome_scheduler(V29_OUTCOME_LIMIT)
        details["outcome"] = outcome
        rows += int(outcome.get("checked", 0) or outcome.get("closed", 0) or 0)
        details["provider_health"] = provider_health(force=True)
        details["feedback"] = feedback_loop("GLOBAL", V29_FEEDBACK_LOOKBACK)
        set_state("last_scheduler_heartbeat", now_iso(), updated_by="scheduler", note="cron run completed")
    except Exception as e:
        status = "ERROR"
        error = str(e)
        governance_event("scheduler_error", "ERROR", decision="ERROR", reason=error)
    duration_ms = round((time.time() - started) * 1000, 2)
    # Update by id when possible; for psycopg lastrowid is unavailable, insert final event instead.
    try:
        if run_id:
            store.execute(f"UPDATE v29_scheduler_runs SET finished_at={ph}, status={ph}, duration_ms={ph}, rows_processed={ph}, error={ph}, details={ph} WHERE id={ph}", (now_iso(), status, duration_ms, rows, error, as_json(details), run_id))
        else:
            store.execute(f"INSERT INTO v29_scheduler_runs(started_at,finished_at,job_name,status,duration_ms,rows_processed,error,details) VALUES({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})", (now_iso(), now_iso(), "v29_governance_cron_result", status, duration_ms, rows, error, as_json(details)))
    except Exception:
        pass
    return {"ok": status == "OK", "version": V29_VERSION, "status": status, "duration_ms": duration_ms, "rows_processed": rows, "error": error, "details": details}


def scheduler_loop() -> None:
    while True:
        try:
            scheduler_run_once()
        except Exception as e:  # pragma: no cover
            try:
                governance_event("scheduler_loop_error", "ERROR", decision="ERROR", reason=str(e))
            except Exception:
                pass
        time.sleep(max(60, V29_CRON_INTERVAL_SECONDS))


def start_scheduler_once() -> Dict[str, Any]:
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return {"ok": True, "started": False, "reason": "already running"}
        t = threading.Thread(target=scheduler_loop, daemon=True, name="v29-governance-cron")
        t.start()
        _scheduler_started = True
        governance_event("scheduler_started", "INFO", decision="STARTED", reason=f"interval={V29_CRON_INTERVAL_SECONDS}s")
        return {"ok": True, "started": True, "interval_seconds": V29_CRON_INTERVAL_SECONDS}


def dashboard_payload() -> Dict[str, Any]:
    init_v29_db()
    outcomes = realised_outcomes(V29_FEEDBACK_LOOKBACK)
    dd = compute_drawdown_r(outcomes)
    streak = current_loss_streak(outcomes)
    total_alerts, _ = today_alert_counts("")
    return {
        "ok": True,
        "version": V29_VERSION,
        "database": "postgresql" if store.pg else "sqlite",
        "state": recent_rows("v29_system_state", 50),
        "governance": {
            "today_pass_alerts": total_alerts,
            "max_daily_alerts": V29_MAX_DAILY_ALERTS,
            "drawdown_r": dd,
            "max_drawdown_r": V29_MAX_DRAWDOWN_R,
            "loss_streak": streak,
            "max_loss_streak": V29_MAX_LOSS_STREAK,
        },
        "provider_health": provider_health(force=False),
        "strategy_feedback": recent_rows("v29_strategy_feedback", 20),
        "scheduler_runs": recent_rows("v29_scheduler_runs", 20),
        "events": recent_rows("v29_governance_events", 50),
        "v28_dashboard": v28.dashboard_payload(),
    }


def html_table(rows: List[Dict[str, Any]], limit: int = 20) -> str:
    rows = rows[:limit] if rows else []
    if not rows:
        return "<p>No data</p>"
    cols = list(rows[0].keys())[:10]
    html = "<table border='1' cellpadding='6' cellspacing='0'><tr>" + "".join(f"<th>{c}</th>" for c in cols) + "</tr>"
    for r in rows:
        html += "<tr>" + "".join(f"<td>{str(r.get(c, ''))[:180]}</td>" for c in cols) + "</tr>"
    return html + "</table>"


def dashboard_html() -> str:
    p = dashboard_payload()
    g = p["governance"]
    h = p["provider_health"]
    return f"""
    <html><head><title>V29 Fund Governance Dashboard</title></head>
    <body style="font-family:Arial,sans-serif;margin:24px;">
      <h1>V29 Production Hardening & Governance Core</h1>
      <p><b>Database:</b> {p['database']} | <b>Provider:</b> {h.get('status')} ({h.get('aggregate_score')})</p>
      <h2>Risk / Compliance</h2>
      <ul>
        <li>Today PASS alerts: {g['today_pass_alerts']} / {g['max_daily_alerts']}</li>
        <li>Drawdown: {g['drawdown_r']}R / limit {g['max_drawdown_r']}R</li>
        <li>Loss streak: {g['loss_streak']} / {g['max_loss_streak']}</li>
      </ul>
      <h2>System State</h2>{html_table(p['state'])}
      <h2>Provider Health</h2>{html_table(h.get('providers', []))}
      <h2>Strategy Feedback</h2>{html_table(p['strategy_feedback'])}
      <h2>Scheduler Runs</h2>{html_table(p['scheduler_runs'])}
      <h2>Governance Events</h2>{html_table(p['events'])}
      <p style="margin-top:30px;color:#666;">V29 dashboard separates governance/compliance from V28 signal, risk and performance data.</p>
    </body></html>
    """


# Initialize at import so routes are immediately usable.
try:
    init_v29_db()
except Exception as e:  # pragma: no cover
    print("V29 init warning:", e)
