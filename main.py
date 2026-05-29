import os
import json
import math
import random
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests
from flask import Flask, request, jsonify, Response, redirect

try:
    import psycopg2
    import psycopg2.extras
except Exception:
    psycopg2 = None

app = Flask(__name__)

APP_VERSION = "V22.1 Professional PostgreSQL + LINE Fixed"
PORT = int(os.getenv("PORT", "8000"))
DB_PATH = os.getenv("DB_PATH", "/app/signals.db")

# Railway may expose DATABASE_URL on worker, or DATABASE_PUBLIC_URL if copied manually.
DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("DATABASE_PUBLIC_URL")
    or os.getenv("POSTGRES_URL")
    or ""
).strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]
USE_POSTGRES = bool(DATABASE_URL)

ACCOUNT_EQUITY = float(os.getenv("ACCOUNT_EQUITY", "10000"))
RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", "1.0"))
MAX_PORTFOLIO_HEAT_PCT = float(os.getenv("MAX_PORTFOLIO_HEAT_PCT", "6.0"))
MAX_DAILY_LOSS_R = float(os.getenv("MAX_DAILY_LOSS_R", "-3.0"))
MAX_CONSECUTIVE_LOSSES = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "5"))
MONTE_CARLO_RUNS = int(os.getenv("MONTE_CARLO_RUNS", "1000"))
MONTE_CARLO_TRADES = int(os.getenv("MONTE_CARLO_TRADES", "100"))

# LINE Messaging API variables. Supports old/new names.
LINE_CHANNEL_ACCESS_TOKEN = (
    os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    or os.getenv("LINE_TOKEN")
    or os.getenv("LINE_ACCESS_TOKEN")
    or ""
).strip()
LINE_USER_IDS_RAW = (
    os.getenv("ALERT_USER_IDS")
    or os.getenv("LINE_USER_ID")
    or os.getenv("LINE_USER_IDS")
    or ""
).strip()
LINE_USER_IDS = [x.strip() for x in LINE_USER_IDS_RAW.replace(";", ",").split(",") if x.strip()]
ENABLE_AUTO_ALERTS = os.getenv("ENABLE_AUTO_ALERTS", "false").lower() in {"1", "true", "yes", "on"}

# ---------- utils ----------
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

def side_norm(x: Any) -> str:
    s = str(x or "CALL").strip().upper()
    return "PUT" if s in {"PUT", "P", "SHORT", "SELL"} else "CALL"

def rowdict(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    try:
        return dict(row)
    except Exception:
        return {}

def placeholders(sql: str) -> str:
    return sql.replace("?", "%s") if USE_POSTGRES else sql

# ---------- database ----------
def get_conn():
    if USE_POSTGRES:
        if psycopg2 is None:
            raise RuntimeError("psycopg2-binary is not installed")
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
        cur.execute(placeholders(sql), params)
        return [rowdict(r) for r in cur.fetchall()]
    finally:
        conn.close()

def fetch_one(sql: str, params: Tuple = ()) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(placeholders(sql), params)
        r = cur.fetchone()
        return rowdict(r) if r else None
    finally:
        conn.close()

def execute(sql: str, params: Tuple = ()) -> None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(placeholders(sql), params)
        conn.commit()
    finally:
        conn.close()

def execute_returning_id(sql_no_returning: str, params: Tuple = ()) -> int:
    conn = get_conn()
    try:
        cur = conn.cursor()
        if USE_POSTGRES:
            cur.execute(placeholders(sql_no_returning + " RETURNING id"), params)
            new_id = int(cur.fetchone()["id"])
        else:
            cur.execute(sql_no_returning, params)
            new_id = int(cur.lastrowid)
        conn.commit()
        return new_id
    finally:
        conn.close()

def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()
    try:
        if USE_POSTGRES:
            id_col = "SERIAL PRIMARY KEY"
            real = "DOUBLE PRECISION"
        else:
            id_col = "INTEGER PRIMARY KEY AUTOINCREMENT"
            real = "REAL"
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS trade_journal (
                id {id_col}, created_at TEXT NOT NULL, created_ts TEXT NOT NULL, updated_at TEXT,
                symbol TEXT NOT NULL, asset_type TEXT DEFAULT 'US_STOCK', side TEXT NOT NULL,
                strategy TEXT DEFAULT 'MANUAL', entry_price {real} NOT NULL DEFAULT 0,
                stop_price {real} NOT NULL DEFAULT 0, target_price {real} NOT NULL DEFAULT 0,
                exit_price {real}, qty {real} NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'OPEN',
                r_multiple {real} NOT NULL DEFAULT 0, result_pct {real} NOT NULL DEFAULT 0, pnl {real} NOT NULL DEFAULT 0,
                source TEXT DEFAULT 'manual', notes TEXT, regime TEXT
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS closed_outcomes (
                id {id_col}, trade_id INTEGER UNIQUE, created_at TEXT NOT NULL, closed_at TEXT NOT NULL,
                symbol TEXT, asset_type TEXT, side TEXT, strategy TEXT,
                entry_price {real}, exit_price {real}, stop_price {real}, target_price {real}, qty {real},
                result TEXT, result_pct {real}, r_multiple {real}, pnl {real}, holding_minutes INTEGER DEFAULT 0,
                source TEXT, notes TEXT, regime TEXT
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS strategy_performance (
                strategy TEXT PRIMARY KEY, trades INTEGER DEFAULT 0, wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0,
                breakeven INTEGER DEFAULT 0, win_rate {real} DEFAULT 0, avg_win_r {real} DEFAULT 0,
                avg_loss_r {real} DEFAULT 0, profit_factor {real} DEFAULT 0, expectancy_r {real} DEFAULT 0,
                total_r {real} DEFAULT 0, max_win_r {real} DEFAULT 0, max_loss_r {real} DEFAULT 0, updated_at TEXT
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS equity_curve (
                id {id_col}, created_at TEXT NOT NULL, trade_id INTEGER, symbol TEXT, strategy TEXT,
                r_multiple {real}, equity_r {real}, drawdown_r {real}
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS risk_state (
                key TEXT PRIMARY KEY, value TEXT, updated_at TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()

# ---------- LINE ----------
def line_ready() -> bool:
    return bool(LINE_CHANNEL_ACCESS_TOKEN and LINE_USER_IDS)

def line_push_text(text: str) -> Dict[str, Any]:
    if not LINE_CHANNEL_ACCESS_TOKEN:
        return {"ok": False, "error": "missing LINE_CHANNEL_ACCESS_TOKEN or LINE_TOKEN"}
    if not LINE_USER_IDS:
        return {"ok": False, "error": "missing LINE_USER_ID or ALERT_USER_IDS"}
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}", "Content-Type": "application/json"}
    results = []
    for uid in LINE_USER_IDS:
        payload = {"to": uid, "messages": [{"type": "text", "text": text[:4900]}]}
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=15)
            results.append({"to": uid[-6:] if len(uid) > 6 else uid, "status": r.status_code, "body": r.text[:500]})
        except Exception as e:
            results.append({"to": uid[-6:] if len(uid) > 6 else uid, "error": str(e)})
    ok = all(x.get("status") in (200, 201) for x in results)
    return {"ok": ok, "results": results}

def trade_message(kind: str, data: Dict[str, Any]) -> str:
    if kind == "open":
        return f"📌 OPEN {data.get('symbol')} {data.get('side')}\nEntry: {data.get('entry')}\nID: {data.get('trade_id')}\nTime: {now_th_text()}"
    return f"✅ CLOSE Trade #{data.get('trade_id')}\nResult: {data.get('result')}\nR: {data.get('r_multiple')}\nPnL: {data.get('pnl')}\nTime: {now_th_text()}"

# ---------- trading core ----------
def calc_trade_result(side: str, entry: float, stop: float, exit_price: float, qty: float) -> Dict[str, float]:
    risk = abs(entry - stop) or max(entry * 0.03, 0.01)
    raw = (exit_price - entry) if side_norm(side) == "CALL" else (entry - exit_price)
    return {
        "r_multiple": round(raw / risk, 4),
        "result_pct": round((raw / entry * 100.0) if entry else 0.0, 4),
        "pnl": round(raw * qty, 4),
    }

def auto_stop_status() -> Dict[str, Any]:
    rows = fetch_all("SELECT * FROM closed_outcomes ORDER BY id DESC LIMIT 30")
    today = now_th_text()[:10]
    today_r = sum(fnum(r.get("r_multiple")) for r in rows if str(r.get("closed_at") or "").startswith(today))
    consec = 0
    for r in rows:
        if fnum(r.get("r_multiple")) < 0:
            consec += 1
        else:
            break
    active, reason = False, "OK"
    if today_r <= MAX_DAILY_LOSS_R:
        active, reason = True, f"daily loss {round(today_r, 2)}R"
    elif consec >= MAX_CONSECUTIVE_LOSSES:
        active, reason = True, f"{consec} consecutive losses"
    return {"active": active, "reason": reason, "today_r": round(today_r, 3), "consecutive_losses": consec,
            "max_daily_loss_r": MAX_DAILY_LOSS_R, "max_consecutive_losses": MAX_CONSECUTIVE_LOSSES}

def open_trade_from_args(args) -> Dict[str, Any]:
    st = auto_stop_status()
    if st.get("active"):
        raise ValueError(f"AUTO_STOP_ACTIVE: {st.get('reason')}")
    symbol = str(args.get("symbol") or args.get("ticker") or "NVDA").strip().upper()
    side = side_norm(args.get("side"))
    strategy = str(args.get("strategy") or "MANUAL").strip().upper()
    entry = fnum(args.get("entry") or args.get("entry_price"), 0)
    if entry <= 0:
        raise ValueError("entry must be greater than 0")
    stop = fnum(args.get("stop") or args.get("stop_price"), entry * (0.97 if side == "CALL" else 1.03))
    target = fnum(args.get("target") or args.get("target_price"), entry * (1.05 if side == "CALL" else 0.95))
    qty = fnum(args.get("qty"), 1)
    created_at = now_th_text()
    created_ts = now_utc_iso()
    sql = """
        INSERT INTO trade_journal
        (created_at, created_ts, updated_at, symbol, asset_type, side, strategy, entry_price, stop_price, target_price, qty, status, source, notes, regime)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?)
    """
    trade_id = execute_returning_id(sql, (
        created_at, created_ts, created_ts, symbol, str(args.get("asset_type") or "US_STOCK").upper(), side, strategy,
        entry, stop, target, qty, str(args.get("source") or "manual"), str(args.get("notes") or "")[:2000], str(args.get("regime") or "")[:100]
    ))
    res = {"ok": True, "trade_id": trade_id, "symbol": symbol, "side": side, "entry": entry}
    if os.getenv("LINE_ON_TRADE", "true").lower() in {"1", "true", "yes", "on"}:
        res["line"] = line_push_text(trade_message("open", res))
    return res

def close_trade(trade_id: int, exit_price: float, notes: str = "") -> Dict[str, Any]:
    r = fetch_one("SELECT * FROM trade_journal WHERE id=?", (trade_id,))
    if not r:
        raise ValueError(f"trade_id {trade_id} not found")
    if str(r.get("status", "")).upper() == "CLOSED":
        return {"ok": True, "trade_id": trade_id, "already_closed": True}
    res = calc_trade_result(r.get("side"), fnum(r.get("entry_price")), fnum(r.get("stop_price")), exit_price, fnum(r.get("qty"), 1))
    result = "WIN" if res["r_multiple"] > 0 else "LOSS" if res["r_multiple"] < 0 else "BREAKEVEN"
    execute("""
        UPDATE trade_journal SET exit_price=?, status='CLOSED', r_multiple=?, result_pct=?, pnl=?, updated_at=?, notes=? WHERE id=?
    """, (exit_price, res["r_multiple"], res["result_pct"], res["pnl"], now_utc_iso(), notes or r.get("notes") or "", trade_id))
    execute("DELETE FROM closed_outcomes WHERE trade_id=?", (trade_id,))
    execute("""
        INSERT INTO closed_outcomes
        (trade_id, created_at, closed_at, symbol, asset_type, side, strategy, entry_price, exit_price, stop_price, target_price, qty, result, result_pct, r_multiple, pnl, holding_minutes, source, notes, regime)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (trade_id, r.get("created_at"), now_th_text(), r.get("symbol"), r.get("asset_type"), r.get("side"), r.get("strategy"),
          fnum(r.get("entry_price")), exit_price, fnum(r.get("stop_price")), fnum(r.get("target_price")), fnum(r.get("qty"), 1),
          result, res["result_pct"], res["r_multiple"], res["pnl"], 0, r.get("source"), notes or r.get("notes"), r.get("regime")))
    rebuild_analytics()
    out = {"ok": True, "trade_id": trade_id, "result": result, **res}
    if os.getenv("LINE_ON_TRADE", "true").lower() in {"1", "true", "yes", "on"}:
        out["line"] = line_push_text(trade_message("close", out))
    return out

# ---------- analytics ----------
def performance_from_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    rs = [fnum(r.get("r_multiple")) for r in rows]
    wins = [x for x in rs if x > 0]
    losses = [x for x in rs if x < 0]
    trades = len(rs)
    gross_win, gross_loss = sum(wins), abs(sum(losses))
    return {"trades": trades, "wins": len(wins), "losses": len(losses), "breakeven": trades-len(wins)-len(losses),
            "win_rate": round((len(wins)/trades*100) if trades else 0, 2),
            "avg_win_r": round(sum(wins)/len(wins), 3) if wins else 0,
            "avg_loss_r": round(sum(losses)/len(losses), 3) if losses else 0,
            "profit_factor": round(gross_win/gross_loss, 3) if gross_loss else round(gross_win, 3),
            "expectancy_r": round(sum(rs)/trades, 3) if trades else 0,
            "total_r": round(sum(rs), 3), "max_win_r": round(max(rs), 3) if rs else 0, "max_loss_r": round(min(rs), 3) if rs else 0}

def rebuild_analytics() -> None:
    outcomes = fetch_all("SELECT * FROM closed_outcomes ORDER BY id ASC")
    execute("DELETE FROM strategy_performance")
    for st in sorted(set((r.get("strategy") or "MANUAL") for r in outcomes)):
        p = performance_from_rows([r for r in outcomes if (r.get("strategy") or "MANUAL") == st])
        execute("""
            INSERT INTO strategy_performance
            (strategy, trades, wins, losses, breakeven, win_rate, avg_win_r, avg_loss_r, profit_factor, expectancy_r, total_r, max_win_r, max_loss_r, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (st, p["trades"], p["wins"], p["losses"], p["breakeven"], p["win_rate"], p["avg_win_r"], p["avg_loss_r"], p["profit_factor"], p["expectancy_r"], p["total_r"], p["max_win_r"], p["max_loss_r"], now_utc_iso()))
    execute("DELETE FROM equity_curve")
    equity = peak = 0.0
    for r in outcomes:
        rr = fnum(r.get("r_multiple"))
        equity += rr
        peak = max(peak, equity)
        execute("INSERT INTO equity_curve (created_at, trade_id, symbol, strategy, r_multiple, equity_r, drawdown_r) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (r.get("closed_at") or now_th_text(), r.get("trade_id"), r.get("symbol"), r.get("strategy"), rr, round(equity, 3), round(equity-peak, 3)))

def drawdown_stats() -> Dict[str, Any]:
    rows = fetch_all("SELECT equity_r FROM equity_curve ORDER BY id ASC")
    vals = [fnum(x.get("equity_r")) for x in rows]
    if not vals:
        return {"max_dd_r": 0, "current_dd_r": 0, "peak_r": 0, "equity_r": 0}
    peak = vals[0]; max_dd = 0.0
    for v in vals:
        peak = max(peak, v); max_dd = min(max_dd, v-peak)
    return {"max_dd_r": round(max_dd,3), "current_dd_r": round(vals[-1]-max(vals),3), "peak_r": round(max(vals),3), "equity_r": round(vals[-1],3)}

def portfolio_heat() -> Dict[str, Any]:
    rows = fetch_all("SELECT * FROM trade_journal WHERE status='OPEN' ORDER BY id ASC")
    total = 0.0; by_symbol = {}; by_strategy = {}
    for r in rows:
        risk_pct = abs(fnum(r.get("entry_price"))-fnum(r.get("stop_price"))) * fnum(r.get("qty"),1) / ACCOUNT_EQUITY * 100 if ACCOUNT_EQUITY else 0
        total += risk_pct
        by_symbol[r.get("symbol") or "UNKNOWN"] = by_symbol.get(r.get("symbol") or "UNKNOWN",0)+risk_pct
        by_strategy[r.get("strategy") or "MANUAL"] = by_strategy.get(r.get("strategy") or "MANUAL",0)+risk_pct
    status = "OK" if total < MAX_PORTFOLIO_HEAT_PCT*0.7 else "WARM / CAUTION" if total < MAX_PORTFOLIO_HEAT_PCT else "HOT / REDUCE RISK"
    return {"open_positions": len(rows), "open_risk_pct": round(total,2), "max_portfolio_heat_pct": MAX_PORTFOLIO_HEAT_PCT,
            "heat_score": round(min(100, total/MAX_PORTFOLIO_HEAT_PCT*100),1) if MAX_PORTFOLIO_HEAT_PCT else 0,
            "status": status, "top_symbol": max(by_symbol, key=by_symbol.get) if by_symbol else "N/A",
            "by_symbol": {k: round(v,2) for k,v in by_symbol.items()}, "by_strategy": {k: round(v,2) for k,v in by_strategy.items()}}

def position_size(entry: Any, stop: Any, equity: Any=None, risk_pct: Any=None) -> Dict[str, Any]:
    entry=fnum(entry); stop=fnum(stop); equity=fnum(equity, ACCOUNT_EQUITY); risk_pct=fnum(risk_pct, RISK_PER_TRADE_PCT)
    per=abs(entry-stop); cash=equity*risk_pct/100
    return {"entry":entry,"stop":stop,"account_equity":equity,"risk_pct":risk_pct,"risk_cash":round(cash,2),"per_unit_risk":round(per,4),"qty":int(math.floor(cash/per)) if per>0 else 0}

def market_regime_stats() -> Dict[str, Any]:
    groups: Dict[str, List[float]] = {}
    for r in fetch_all("SELECT regime, r_multiple FROM closed_outcomes"):
        groups.setdefault(r.get("regime") or "UNKNOWN", []).append(fnum(r.get("r_multiple")))
    return {k: {"trades": len(v), "win_rate": round(sum(1 for x in v if x>0)/len(v)*100,2) if v else 0, "expectancy_r": round(sum(v)/len(v),3) if v else 0} for k,v in groups.items()}

def monte_carlo(runs=None, trades=None) -> Dict[str, Any]:
    runs=inum(runs, MONTE_CARLO_RUNS); trades=inum(trades, MONTE_CARLO_TRADES)
    rs=[fnum(r.get("r_multiple")) for r in fetch_all("SELECT r_multiple FROM closed_outcomes")]
    if len(rs)<5: return {"ok": False, "message": "Need at least 5 closed trades for Monte Carlo", "closed_trades": len(rs)}
    finals=[]; dds=[]
    for _ in range(max(1,runs)):
        e=p=dd=0.0
        for _ in range(max(1,trades)):
            e += random.choice(rs); p=max(p,e); dd=min(dd,e-p)
        finals.append(e); dds.append(dd)
    finals.sort(); dds.sort()
    pick=lambda arr,p: round(arr[min(len(arr)-1,max(0,int(len(arr)*p)))],3)
    return {"ok": True, "runs": runs, "trades_per_run": trades, "final_r_p10": pick(finals,.10), "final_r_p50": pick(finals,.50), "final_r_p90": pick(finals,.90), "max_dd_r_p10": pick(dds,.10), "max_dd_r_p50": pick(dds,.50), "max_dd_r_p90": pick(dds,.90)}

def snapshot() -> Dict[str, Any]:
    open_trades=fetch_all("SELECT * FROM trade_journal WHERE status='OPEN' ORDER BY id ASC")
    closed=fetch_all("SELECT * FROM closed_outcomes ORDER BY id ASC")
    return {"ok": True, "version": APP_VERSION, "database": "PostgreSQL" if USE_POSTGRES else "SQLite", "db_url_exists": bool(DATABASE_URL),
            "_db_path": "DATABASE_URL" if USE_POSTGRES else DB_PATH, "line_ready": line_ready(), "open_trades": len(open_trades), "closed_outcomes": len(closed),
            "performance": performance_from_rows(closed), "recent_outcomes": closed[-10:], "open_trade_rows": open_trades,
            "strategy_performance_db": fetch_all("SELECT * FROM strategy_performance ORDER BY expectancy_r DESC, trades DESC"),
            "equity_curve": fetch_all("SELECT * FROM equity_curve ORDER BY id ASC"),
            "v22": {"position_sizing":"enabled", "drawdown": drawdown_stats(), "portfolio_heat": portfolio_heat(), "auto_stop": auto_stop_status(), "market_regime": market_regime_stats()},
            "sample_open_url":"/v21-6/journal/open?symbol=NVDA&side=CALL&entry=212&stop=205&target=225&strategy=MOMENTUM&qty=1", "sample_close_url":"/v21-6/journal/close/1?exit=220"}

# ---------- html ----------
CSS = """
body{margin:0;background:#0f172a;color:#e5e7eb;font-family:Arial,Helvetica,sans-serif}.wrap{max-width:1100px;margin:36px auto;padding:0 18px}.badge{display:inline-block;background:#2563eb;color:white;border-radius:10px;padding:6px 10px;font-size:13px}h1{font-size:32px;margin:14px 0 6px}.nav{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}.nav a{color:#e5e7eb;text-decoration:none;background:#334155;padding:10px 14px;border-radius:10px}.nav a.active{background:#2563eb}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}.metric,.card{background:#1e293b;border:1px solid #334155;border-radius:14px;padding:18px;margin:12px 0}.label{font-size:12px;text-transform:uppercase;color:#94a3b8}.value{font-size:28px;font-weight:bold;margin-top:6px}table{width:100%;border-collapse:collapse;font-size:14px}th,td{border-bottom:1px solid #334155;padding:9px;text-align:left;white-space:nowrap}th{color:#93c5fd;font-size:12px;text-transform:uppercase}input,select{width:100%;box-sizing:border-box;background:#0f172a;color:#e5e7eb;border:1px solid #475569;border-radius:8px;padding:10px}button{background:#2563eb;color:white;border:0;border-radius:9px;padding:11px 16px;cursor:pointer}pre{background:#020617;border-radius:10px;padding:14px;overflow:auto}.small{color:#94a3b8;font-size:13px}.good{color:#86efac}.bad{color:#fca5a5}
"""

def nav(active: str) -> str:
    items=[("/v21-6/dashboard","Dashboard","dashboard"),("/v21-6/journal","Journal","journal"),("/v21-6/outcomes","Outcomes","outcomes"),("/v21-6/stats","Stats","stats"),("/v21-6/equity","Equity","equity"),("/v22/risk","Risk V22","risk"),("/v21-6/api/snapshot","JSON","json")]
    return ''.join(f'<a class="{"active" if key==active else ""}" href="{path}">{name}</a>' for path,name,key in items)

def page(title: str, body: str, active: str="dashboard") -> Response:
    db = "PostgreSQL" if USE_POSTGRES else "SQLite"
    html=f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{title}</title><style>{CSS}</style></head><body><div class='wrap'><span class='badge'>{APP_VERSION}</span><h1>{title}</h1><p class='small'>Database: <b>{db}</b> · LINE: <b>{'Ready' if line_ready() else 'Not configured'}</b> · Research cockpit only. Not investment advice.</p><div class='nav'>{nav(active)}</div>{body}</div></body></html>"""
    return Response(html, mimetype="text/html")

def table(rows: List[Dict[str, Any]], cols: List[Tuple[str,str]]) -> str:
    if not rows: return "<div class='card'><p class='small'>No records yet.</p></div>"
    head=''.join(f'<th>{label}</th>' for key,label in cols)
    body=''.join('<tr>'+''.join(f'<td>{r.get(key, "") if r.get(key, "") is not None else ""}</td>' for key,label in cols)+'</tr>' for r in rows)
    return f'<div class="card"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'

# ---------- routes ----------
@app.route("/")
def root(): return redirect("/v21-6/dashboard")

@app.route("/health")
def health(): return jsonify({"ok": True, "version": APP_VERSION, "database": "PostgreSQL" if USE_POSTGRES else "SQLite", "line_ready": line_ready()})

@app.route("/v22/debug-db")
def debug_db():
    info = {"database_url_exists": bool(DATABASE_URL), "use_postgres": USE_POSTGRES, "psycopg2_loaded": psycopg2 is not None, "database": "PostgreSQL" if USE_POSTGRES else "SQLite", "db_path": DB_PATH, "version": APP_VERSION, "line_ready": line_ready()}
    try:
        r = fetch_one("SELECT 1 AS ok")
        info["connection_ok"] = True; info["select_1"] = r
    except Exception as e:
        info["connection_ok"] = False; info["error"] = str(e)
    return jsonify(info)

@app.route("/line/test")
@app.route("/v22/line/test")
def line_test(): return jsonify(line_push_text("✅ LINE test from V22.1: ระบบส่งไลน์ทำงานแล้ว " + now_th_text()))

@app.route("/webhook", methods=["GET","POST"])
def webhook(): return jsonify({"ok": True, "message": "webhook received", "time": now_th_text()})

@app.route("/v21-6")
@app.route("/v21-6/dashboard")
@app.route("/v22")
@app.route("/v22/dashboard")
def dashboard():
    s=snapshot(); p=s["performance"]; dd=s["v22"]["drawdown"]; heat=s["v22"]["portfolio_heat"]; astop=s["v22"]["auto_stop"]
    body=f"""<div class='grid'><div class='metric'><div class='label'>Open Trades</div><div class='value'>{s['open_trades']}</div></div><div class='metric'><div class='label'>Closed Trades</div><div class='value'>{s['closed_outcomes']}</div></div><div class='metric'><div class='label'>Profit Factor</div><div class='value'>{p['profit_factor']}</div></div><div class='metric'><div class='label'>Expectancy</div><div class='value'>{p['expectancy_r']}R</div></div><div class='metric'><div class='label'>Max DD</div><div class='value'>{dd['max_dd_r']}R</div></div><div class='metric'><div class='label'>Portfolio Heat</div><div class='value'>{heat['open_risk_pct']}%</div><p>{heat['status']}</p></div><div class='metric'><div class='label'>Auto Stop</div><div class='value'>{'ON' if astop['active'] else 'OFF'}</div><p>{astop['reason']}</p></div><div class='metric'><div class='label'>LINE</div><div class='value'>{'Ready' if line_ready() else 'Off'}</div></div></div><div class='card'><h2>Quick Test</h2><pre>/v21-6/journal/open?symbol=NVDA&side=CALL&entry=212&stop=205&target=225&strategy=MOMENTUM&qty=1
/v21-6/journal/close/1?exit=220
/v22/line/test
/v22/debug-db</pre></div>"""
    return page("V22 Professional Dashboard", body, "dashboard")

@app.route("/v21-6/journal/open")
@app.route("/v22/journal/open")
def route_open():
    try:
        res=open_trade_from_args(request.args)
        return jsonify({**res, "close_url_example": f"/v21-6/journal/close/{res['trade_id']}?exit=YOUR_EXIT_PRICE"})
    except Exception as e: return jsonify({"ok": False, "error": str(e)}), 400

@app.route("/v21-6/journal/close/<int:trade_id>")
@app.route("/v22/journal/close/<int:trade_id>")
def route_close(trade_id: int):
    try:
        exit_price=fnum(request.args.get("exit") or request.args.get("exit_price"),0)
        if exit_price<=0: raise ValueError("exit price is required")
        return jsonify(close_trade(trade_id, exit_price, request.args.get("notes") or ""))
    except Exception as e: return jsonify({"ok": False, "error": str(e)}), 400

@app.route("/v21-6/journal")
@app.route("/v22/journal")
def route_journal():
    cols=[("id","ID"),("symbol","Symbol"),("side","Side"),("strategy","Strategy"),("entry_price","Entry"),("stop_price","Stop"),("target_price","Target"),("exit_price","Exit"),("status","Status"),("r_multiple","R"),("created_at","Entry Time")]
    return page("Real Trade Journal", "<h2>Real Trade Journal</h2>"+table(fetch_all("SELECT * FROM trade_journal ORDER BY id DESC"), cols), "journal")

@app.route("/v21-6/outcomes")
@app.route("/v22/outcomes")
def route_outcomes():
    cols=[("trade_id","Trade ID"),("symbol","Symbol"),("side","Side"),("strategy","Strategy"),("entry_price","Entry"),("exit_price","Exit"),("result","Result"),("result_pct","%"),("r_multiple","R"),("pnl","PnL"),("closed_at","Closed")]
    return page("Trade Outcomes", "<h2>Closed Outcomes</h2>"+table(fetch_all("SELECT * FROM closed_outcomes ORDER BY id DESC"), cols), "outcomes")

@app.route("/v21-6/stats")
@app.route("/v22/stats")
def route_stats():
    rebuild_analytics(); cols=[("strategy","Strategy"),("trades","Trades"),("wins","Wins"),("losses","Losses"),("win_rate","Win Rate"),("profit_factor","PF"),("expectancy_r","Expectancy R"),("total_r","Total R")]
    return page("Strategy Stats", "<h2>Win Rate by Setup</h2>"+table(fetch_all("SELECT * FROM strategy_performance ORDER BY expectancy_r DESC, trades DESC"), cols), "stats")

@app.route("/v21-6/equity")
@app.route("/v22/equity")
def route_equity():
    cols=[("id","ID"),("created_at","Time"),("trade_id","Trade ID"),("symbol","Symbol"),("strategy","Strategy"),("r_multiple","R"),("equity_r","Equity R"),("drawdown_r","DD R")]
    return page("Equity Curve", "<h2>Real Equity Curve</h2>"+table(fetch_all("SELECT * FROM equity_curve ORDER BY id ASC"), cols), "equity")

@app.route("/v21-6/json")
@app.route("/v21-6/api/snapshot")
@app.route("/v21-7/api/snapshot")
@app.route("/v22/api/snapshot")
def route_snapshot(): return jsonify(snapshot())

@app.route("/v21-7/sizing")
@app.route("/v22/sizing")
def route_sizing(): return jsonify({"ok": True, "position_sizing": position_size(request.args.get("entry"), request.args.get("stop"), request.args.get("equity"), request.args.get("risk_pct"))})
@app.route("/v21-7/drawdown")
@app.route("/v22/drawdown")
def route_drawdown(): return jsonify({"ok": True, "drawdown": drawdown_stats()})
@app.route("/v21-7/portfolio-heat")
@app.route("/v22/portfolio-heat")
def route_portfolio_heat(): return jsonify({"ok": True, "portfolio_heat": portfolio_heat()})
@app.route("/v21-7/regime")
@app.route("/v22/regime")
def route_regime(): return jsonify({"ok": True, "market_regime": market_regime_stats()})
@app.route("/v21-7/auto-stop")
@app.route("/v22/auto-stop")
def route_auto_stop(): return jsonify({"ok": True, "auto_stop": auto_stop_status()})
@app.route("/v21-7/monte-carlo")
@app.route("/v22/monte-carlo")
def route_monte_carlo(): return jsonify({"ok": True, "monte_carlo": monte_carlo(request.args.get("runs"), request.args.get("trades"))})

@app.route("/v22/risk")
def route_risk_page():
    s=snapshot()
    body=f"""<div class='grid'><div class='metric'><div class='label'>Position Sizing</div><div class='value'>ON</div></div><div class='metric'><div class='label'>Portfolio Heat</div><div class='value'>{s['v22']['portfolio_heat']['open_risk_pct']}%</div></div><div class='metric'><div class='label'>Max Drawdown</div><div class='value'>{s['v22']['drawdown']['max_dd_r']}R</div></div><div class='metric'><div class='label'>Auto Stop</div><div class='value'>{'ON' if s['v22']['auto_stop']['active'] else 'OFF'}</div></div></div><div class='card'><h2>Monte Carlo</h2><pre>{json.dumps(monte_carlo(), ensure_ascii=False, indent=2)}</pre></div><div class='card'><h2>Market Regime</h2><pre>{json.dumps(market_regime_stats(), ensure_ascii=False, indent=2)}</pre></div>"""
    return page("V22 Risk Engine", body, "risk")

try:
    init_db()
    rebuild_analytics()
    print(f"{APP_VERSION} started | database={'PostgreSQL' if USE_POSTGRES else 'SQLite'} | line_ready={line_ready()}")
except Exception as e:
    print("V22 startup warning:", e)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
