"""
V28 Fund Validation Core
Real Audit DB, Auto Outcome Scheduler, Portfolio Risk Engine, Walk-forward Backtest,
and segmented Fund Dashboard.

Design principle: add a fund-validation layer without removing legacy V7-V27 features.
This module uses SQLite by default through DB_PATH, and is safe to run on Railway/Render.
"""
import os
import json
import math
import sqlite3
from datetime import datetime, timezone, timedelta
from statistics import mean, pstdev

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None

DB_PATH = os.getenv("DB_PATH", "signals.db")
V28_VERSION = "V28 Fund Validation Core"

MAX_TOTAL_HEAT_R = float(os.getenv("V28_MAX_TOTAL_HEAT_R", "6.0"))
MAX_SYMBOL_HEAT_R = float(os.getenv("V28_MAX_SYMBOL_HEAT_R", "1.25"))
MAX_THEME_HEAT_R = float(os.getenv("V28_MAX_THEME_HEAT_R", "2.5"))
MAX_CORRELATION = float(os.getenv("V28_MAX_CORRELATION", "0.80"))
MAX_PORTFOLIO_VAR_R = float(os.getenv("V28_MAX_PORTFOLIO_VAR_R", "3.5"))
OUTCOME_CHECK_LIMIT = int(os.getenv("V28_OUTCOME_CHECK_LIMIT", "100"))

THEME_MAP = {
    "NVDA":"SEMICONDUCTOR_AI", "AMD":"SEMICONDUCTOR_AI", "AVGO":"SEMICONDUCTOR_AI", "TSM":"SEMICONDUCTOR_AI", "SMCI":"SEMICONDUCTOR_AI", "MU":"SEMICONDUCTOR_AI", "ARM":"SEMICONDUCTOR_AI", "INTC":"SEMICONDUCTOR_AI",
    "AAPL":"MEGA_CAP_TECH", "MSFT":"MEGA_CAP_TECH", "META":"MEGA_CAP_TECH", "GOOGL":"MEGA_CAP_TECH", "GOOG":"MEGA_CAP_TECH", "AMZN":"MEGA_CAP_TECH",
    "TSLA":"EV_HIGH_BETA", "PLTR":"AI_SOFTWARE", "SNOW":"AI_SOFTWARE", "CRWD":"CYBER_SOFTWARE", "NET":"CYBER_SOFTWARE", "DDOG":"CLOUD_SOFTWARE",
    "QQQ":"INDEX", "SPY":"INDEX", "IWM":"INDEX", "DIA":"INDEX", "TQQQ":"LEVERAGED_INDEX", "SQQQ":"LEVERAGED_INDEX", "SOXL":"LEVERAGED_SEMICONDUCTOR", "SOXS":"LEVERAGED_SEMICONDUCTOR",
    "GOLD":"GOLD", "XAUUSD":"GOLD", "XAU/USD":"GOLD",
    "JPM":"FINANCIAL", "BAC":"FINANCIAL", "XOM":"ENERGY", "CVX":"ENERGY", "LLY":"HEALTHCARE", "UNH":"HEALTHCARE",
}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(obj):
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return json.dumps({"raw": str(obj)}, ensure_ascii=False)


def conn():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def rows_to_dicts(rows):
    return [dict(r) for r in rows or []]


def execute(sql, params=(), fetch=None):
    c = conn()
    try:
        cur = c.execute(sql, params)
        if fetch == "one":
            row = cur.fetchone()
            return dict(row) if row else None
        if fetch == "all":
            return rows_to_dicts(cur.fetchall())
        c.commit()
        return cur.lastrowid
    finally:
        c.close()


def init_v28_db():
    c = conn()
    try:
        cur = c.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS v28_signal_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS v28_open_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS v28_signal_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER NOT NULL,
                checked_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT,
                price REAL,
                outcome TEXT,
                return_r REAL,
                note TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS v28_portfolio_risk_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS v28_walk_forward_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        """)
        c.commit()
    finally:
        c.close()


def normalize_symbol(symbol):
    s = str(symbol or "").strip().upper()
    if s in {"XAU/USD", "XAUUSD", "GOLD"}:
        return "GOLD"
    return s


def theme(symbol):
    return THEME_MAP.get(normalize_symbol(symbol), "OTHER")


def safe_float(v, default=None):
    try:
        if v is None or v == "":
            return default
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def infer_side(sig):
    s = str(sig or "").upper()
    if s in {"BUY", "CALL", "STRONG_CALL", "LONG"}:
        return "BUY"
    if s in {"SELL", "PUT", "STRONG_PUT", "SHORT"}:
        return "SELL"
    return s or "NONE"


def extract_trade_plan(analysis, side):
    price = safe_float(analysis.get("price") or analysis.get("entry") or analysis.get("last") or analysis.get("close"), None)
    if price is None:
        price = 0.0
    sl = safe_float(analysis.get("sl") or analysis.get("stop_loss"), None)
    tp1 = safe_float(analysis.get("tp1") or analysis.get("target1"), None)
    tp2 = safe_float(analysis.get("tp2") or analysis.get("target2"), None)
    tp3 = safe_float(analysis.get("tp3") or analysis.get("target3"), None)
    atr = safe_float(analysis.get("atr"), None)
    # Fund validation needs a measurable plan. If legacy analysis has no TP/SL,
    # create conservative validation levels only for tracking, not as advice.
    if price and (sl is None or sl <= 0):
        risk_pct = 0.025 if side == "BUY" else 0.025
        sl = price * (1 - risk_pct) if side == "BUY" else price * (1 + risk_pct)
        if atr and atr > 0:
            sl = price - atr if side == "BUY" else price + atr
    if price and (tp1 is None or tp1 <= 0):
        risk_abs = abs(price - sl) if sl else price * 0.025
        tp1 = price + risk_abs if side == "BUY" else price - risk_abs
        tp2 = price + 2 * risk_abs if side == "BUY" else price - 2 * risk_abs
        tp3 = price + 3 * risk_abs if side == "BUY" else price - 3 * risk_abs
    risk_abs = abs(price - sl) if price and sl else 0.0
    return {"entry": price, "stop_loss": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3, "risk_abs": risk_abs, "risk_r": 1.0}


def _decision_hash(payload):
    raw = _json(payload)
    import hashlib
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def audit_signal(symbol, asset_type, sig, analysis, decision, reason, portfolio_gate=None, market_open=None, message=None):
    init_v28_db()
    side = infer_side(sig)
    plan = extract_trade_plan(analysis or {}, side)
    payload = {
        "created_at": now_iso(), "symbol": normalize_symbol(symbol), "asset_type": asset_type, "side": side,
        "decision": str(decision or "UNKNOWN").upper(), "reason": reason, "analysis": analysis or {},
        "portfolio_gate": portfolio_gate or {}, "message_preview": (message or "")[:500]
    }
    h = _decision_hash(payload)
    try:
        audit_id = execute("""
            INSERT OR IGNORE INTO v28_signal_audit
            (created_at, symbol, asset_type, side, decision, reason, score, confidence, trend_strength, rvol, regime,
             risk_grade, entry, stop_loss, tp1, tp2, tp3, risk_r, portfolio_gate, portfolio_reason, market_open, raw_payload, decision_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            payload["created_at"], payload["symbol"], asset_type, side, payload["decision"], str(reason or ""),
            safe_float((analysis or {}).get("score"), None), safe_float((analysis or {}).get("confidence"), None), safe_float((analysis or {}).get("trend_strength"), None), safe_float((analysis or {}).get("rvol"), None), str((analysis or {}).get("regime") or ""),
            str((analysis or {}).get("risk_grade") or (analysis or {}).get("conviction_grade") or ""),
            plan["entry"], plan["stop_loss"], plan["tp1"], plan["tp2"], plan["tp3"], plan["risk_r"],
            str((portfolio_gate or {}).get("decision") or ""), str((portfolio_gate or {}).get("reason") or ""), 1 if market_open else 0 if market_open is not None else None,
            _json(payload), h,
        ))
    except sqlite3.IntegrityError:
        row = execute("SELECT id FROM v28_signal_audit WHERE decision_hash=?", (h,), fetch="one")
        audit_id = row.get("id") if row else None
    if str(decision or "").upper() in {"PASS", "SEND", "SENT", "ALLOW"} and plan["entry"] > 0 and side in {"BUY", "SELL"}:
        open_existing = execute("SELECT id FROM v28_open_signals WHERE symbol=? AND side=? AND status='OPEN' ORDER BY id DESC LIMIT 1", (payload["symbol"], side), fetch="one")
        if not open_existing:
            execute("""
                INSERT INTO v28_open_signals
                (audit_id, created_at, symbol, asset_type, side, entry, stop_loss, tp1, tp2, tp3, risk_r, score, max_price, min_price, last_price, message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (audit_id, payload["created_at"], payload["symbol"], asset_type, side, plan["entry"], plan["stop_loss"], plan["tp1"], plan["tp2"], plan["tp3"], plan["risk_r"], safe_float((analysis or {}).get("score"), None), plan["entry"], plan["entry"], plan["entry"], message or ""))
    return {"ok": True, "audit_id": audit_id, "decision_hash": h, "plan": plan}


def y_symbol(symbol):
    s = normalize_symbol(symbol)
    if s == "GOLD":
        return "GC=F"
    if s.endswith(".BK"):
        return s
    thai = {"SCB","AOT","PTT","CPALL","KBANK","BBL","KTB","ADVANC","BDMS","PTTEP"}
    if s in thai:
        return s + ".BK"
    return s


def price_now(symbol):
    if yf is None:
        return None
    try:
        hist = yf.Ticker(y_symbol(symbol)).history(period="5d", interval="1d")
        if hist is None or hist.empty:
            return None
        return float(hist["Close"].dropna().iloc[-1])
    except Exception:
        return None


def fetch_closes(symbol, period="1y", interval="1d"):
    if yf is None:
        return []
    try:
        hist = yf.Ticker(y_symbol(symbol)).history(period=period, interval=interval)
        if hist is None or hist.empty:
            return []
        return [float(x) for x in hist["Close"].dropna().tolist()]
    except Exception:
        return []


def returns(values):
    out = []
    for i in range(1, len(values)):
        prev = values[i-1]
        cur = values[i]
        if prev:
            out.append((cur - prev) / prev)
    return out


def corr(xs, ys):
    n = min(len(xs), len(ys))
    if n < 20:
        return None
    xs, ys = xs[-n:], ys[-n:]
    mx, my = mean(xs), mean(ys)
    vx = sum((x-mx)**2 for x in xs)
    vy = sum((y-my)**2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    cov = sum((xs[i]-mx)*(ys[i]-my) for i in range(n))
    return cov / ((vx * vy) ** 0.5)


def open_signals(limit=200):
    init_v28_db()
    return execute("SELECT * FROM v28_open_signals WHERE status='OPEN' ORDER BY id DESC LIMIT ?", (int(limit),), fetch="all") or []


def evaluate_portfolio_risk(candidate=None, save=True):
    init_v28_db()
    candidate = candidate or {}
    cand_symbol = normalize_symbol(candidate.get("symbol")) if candidate.get("symbol") else None
    cand_risk = safe_float(candidate.get("risk_r"), 1.0) or 1.0
    cand_theme = theme(cand_symbol) if cand_symbol else None
    positions = open_signals(250)
    total_heat = sum(safe_float(p.get("risk_r"), 1.0) or 1.0 for p in positions)
    theme_heat = sum((safe_float(p.get("risk_r"), 1.0) or 1.0) for p in positions if cand_theme and theme(p.get("symbol")) == cand_theme)
    symbol_heat = sum((safe_float(p.get("risk_r"), 1.0) or 1.0) for p in positions if cand_symbol and normalize_symbol(p.get("symbol")) == cand_symbol)
    symbols = [p.get("symbol") for p in positions if p.get("symbol")]
    if cand_symbol:
        symbols.append(cand_symbol)
    symbols = list(dict.fromkeys(symbols))[:25]
    ret_map = {s: returns(fetch_closes(s, "6mo", "1d")) for s in symbols}
    max_pair = 0.0
    high_corr = []
    if cand_symbol:
        for s in symbols:
            if s == cand_symbol:
                continue
            c = corr(ret_map.get(cand_symbol, []), ret_map.get(s, []))
            if c is not None:
                max_pair = max(max_pair, abs(c))
                if abs(c) >= MAX_CORRELATION:
                    high_corr.append({"symbol": s, "correlation": round(c, 4)})
    spy_ret = returns(fetch_closes("SPY", "6mo", "1d"))
    beta = None
    if cand_symbol:
        c_ret = ret_map.get(cand_symbol, [])
        n = min(len(c_ret), len(spy_ret))
        if n >= 20 and pstdev(spy_ret[-n:]) > 0:
            beta = (corr(c_ret[-n:], spy_ret[-n:]) or 0) * (pstdev(c_ret[-n:]) / pstdev(spy_ret[-n:]))
    # Conservative portfolio VaR in R units: sqrt(sum vol-adjusted risk^2 + covariance proxy)
    vols = []
    for p in positions:
        r = ret_map.get(p.get("symbol"), [])
        vol = pstdev(r[-60:]) if len(r) >= 20 else 0.025
        vols.append((safe_float(p.get("risk_r"), 1.0) or 1.0) * max(0.5, min(2.0, vol / 0.025)))
    if cand_symbol:
        r = ret_map.get(cand_symbol, [])
        vol = pstdev(r[-60:]) if len(r) >= 20 else 0.025
        vols.append(cand_risk * max(0.5, min(2.0, vol / 0.025)))
    portfolio_var = math.sqrt(sum(v*v for v in vols)) if vols else 0.0
    reasons = []
    if total_heat + (cand_risk if cand_symbol else 0) > MAX_TOTAL_HEAT_R:
        reasons.append("TOTAL_HEAT_LIMIT")
    if cand_symbol and symbol_heat + cand_risk > MAX_SYMBOL_HEAT_R:
        reasons.append("SYMBOL_DUPLICATE_HEAT")
    if cand_symbol and theme_heat + cand_risk > MAX_THEME_HEAT_R:
        reasons.append("THEME_HEAT_LIMIT:" + str(cand_theme))
    if high_corr:
        reasons.append("HIGH_CORRELATION_WITH_OPEN_POSITION")
    if portfolio_var > MAX_PORTFOLIO_VAR_R:
        reasons.append("PORTFOLIO_VAR_LIMIT")
    decision = "BLOCK" if reasons else "PASS"
    result = {
        "ok": True, "version": V28_VERSION, "candidate_symbol": cand_symbol, "candidate_theme": cand_theme,
        "decision": decision, "reasons": reasons, "open_positions": len(positions),
        "total_heat_r": round(total_heat + (cand_risk if cand_symbol else 0), 3),
        "theme_heat_r": round(theme_heat + (cand_risk if cand_symbol else 0), 3) if cand_symbol else round(theme_heat, 3),
        "symbol_heat_r": round(symbol_heat + (cand_risk if cand_symbol else 0), 3) if cand_symbol else 0,
        "max_pair_correlation": round(max_pair, 4), "high_correlation": high_corr,
        "portfolio_var_r": round(portfolio_var, 3), "beta_to_spy": round(beta, 4) if beta is not None else None,
        "limits": {"max_total_heat_r": MAX_TOTAL_HEAT_R, "max_symbol_heat_r": MAX_SYMBOL_HEAT_R, "max_theme_heat_r": MAX_THEME_HEAT_R, "max_correlation": MAX_CORRELATION, "max_portfolio_var_r": MAX_PORTFOLIO_VAR_R},
    }
    if save:
        execute("""
            INSERT INTO v28_portfolio_risk_snapshots
            (created_at, candidate_symbol, total_heat_r, theme_heat_r, max_pair_correlation, portfolio_var_r, beta_to_spy, decision, reasons, snapshot)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (now_iso(), cand_symbol, result["total_heat_r"], result["theme_heat_r"], result["max_pair_correlation"], result["portfolio_var_r"], result["beta_to_spy"], decision, " | ".join(reasons), _json(result)))
    return result


def portfolio_gate(symbol, analysis=None, sig=None):
    side = infer_side(sig)
    plan = extract_trade_plan(analysis or {}, side)
    result = evaluate_portfolio_risk({"symbol": symbol, "risk_r": plan.get("risk_r", 1.0)}, save=True)
    return result["decision"] == "PASS", result


def check_signal_outcome(signal, price):
    side = str(signal.get("side") or "BUY").upper()
    entry = safe_float(signal.get("entry"), 0) or 0
    sl = safe_float(signal.get("stop_loss"), None)
    tp1 = safe_float(signal.get("tp1"), None)
    tp2 = safe_float(signal.get("tp2"), None)
    tp3 = safe_float(signal.get("tp3"), None)
    risk_abs = abs(entry - sl) if entry and sl else max(entry * 0.025, 0.01)
    if side == "BUY":
        ret_r = (price - entry) / risk_abs
        if sl and price <= sl: return "SL", round(ret_r, 3)
        if tp3 and price >= tp3: return "TP3", round(ret_r, 3)
        if tp2 and price >= tp2: return "TP2", round(ret_r, 3)
        if tp1 and price >= tp1: return "TP1", round(ret_r, 3)
    else:
        ret_r = (entry - price) / risk_abs
        if sl and price >= sl: return "SL", round(ret_r, 3)
        if tp3 and price <= tp3: return "TP3", round(ret_r, 3)
        if tp2 and price <= tp2: return "TP2", round(ret_r, 3)
        if tp1 and price <= tp1: return "TP1", round(ret_r, 3)
    return "OPEN", round(ret_r, 3)


def run_outcome_scheduler(limit=OUTCOME_CHECK_LIMIT):
    init_v28_db()
    signals = open_signals(limit)
    results = []
    for sig in signals:
        price = price_now(sig.get("symbol"))
        if price is None:
            results.append({"signal_id": sig.get("id"), "symbol": sig.get("symbol"), "ok": False, "reason": "NO_PRICE"})
            continue
        old_max = safe_float(sig.get("max_price"), price) or price
        old_min = safe_float(sig.get("min_price"), price) or price
        max_price = max(old_max, price)
        min_price = min(old_min, price)
        outcome, ret_r = check_signal_outcome(sig, price)
        checked_at = now_iso()
        execute("""
            INSERT INTO v28_signal_outcomes (signal_id, checked_at, symbol, side, price, outcome, return_r, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (sig.get("id"), checked_at, sig.get("symbol"), sig.get("side"), price, outcome, ret_r, "auto_scheduler"))
        if outcome == "OPEN":
            execute("UPDATE v28_open_signals SET max_price=?, min_price=?, last_price=?, last_checked_at=? WHERE id=?", (max_price, min_price, price, checked_at, sig.get("id")))
        else:
            execute("UPDATE v28_open_signals SET max_price=?, min_price=?, last_price=?, last_checked_at=?, status='CLOSED', closed_at=?, outcome=?, return_r=? WHERE id=?", (max_price, min_price, price, checked_at, checked_at, outcome, ret_r, sig.get("id")))
        results.append({"signal_id": sig.get("id"), "symbol": sig.get("symbol"), "price": price, "outcome": outcome, "return_r": ret_r})
    return {"ok": True, "version": V28_VERSION, "checked_at": now_iso(), "checked": len(results), "results": results}


def ema(values, n):
    if not values:
        return []
    k = 2 / (n + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def rsi(values, n=14):
    if len(values) < n + 1:
        return [50.0] * len(values)
    out = [50.0] * len(values)
    gains, losses = [], []
    for i in range(1, len(values)):
        ch = values[i] - values[i-1]
        gains.append(max(ch, 0)); losses.append(max(-ch, 0))
        if i >= n:
            avg_g = mean(gains[-n:]); avg_l = mean(losses[-n:])
            out[i] = 100 if avg_l == 0 else 100 - (100 / (1 + avg_g / avg_l))
    return out


def run_walk_forward(symbol="SPY", period="2y", interval="1d", train_bars=120, test_bars=30, fast=10, slow=30):
    init_v28_db()
    closes = fetch_closes(symbol, period, interval)
    if len(closes) < train_bars + test_bars + slow + 10:
        result = {"ok": False, "version": V28_VERSION, "symbol": normalize_symbol(symbol), "reason": "INSUFFICIENT_PRICE_HISTORY", "bars": len(closes)}
        return result
    efast = ema(closes, fast); eslow = ema(closes, slow); rs = rsi(closes)
    all_trades = []
    windows = []
    start = slow + 5
    while start + train_bars + test_bars <= len(closes):
        test_start = start + train_bars
        test_end = test_start + test_bars
        trades = []
        pos = None
        for i in range(test_start, test_end):
            if pos is None and efast[i] > eslow[i] and rs[i] >= 50:
                pos = {"entry": closes[i], "entry_i": i, "sl": closes[i] * 0.975, "tp": closes[i] * 1.05}
            elif pos:
                ret = None
                if closes[i] <= pos["sl"]:
                    ret = -1.0
                elif closes[i] >= pos["tp"]:
                    ret = 2.0
                elif i == test_end - 1:
                    risk = abs(pos["entry"] - pos["sl"])
                    ret = (closes[i] - pos["entry"]) / risk if risk else 0
                if ret is not None:
                    trades.append(ret); all_trades.append(ret); pos = None
        windows.append({"start_bar": test_start, "end_bar": test_end, "trades": len(trades), "return_r": round(sum(trades), 3), "win_rate": round(sum(1 for x in trades if x > 0) / len(trades) * 100, 2) if trades else 0})
        start += test_bars
    trades_count = len(all_trades)
    wins = sum(1 for x in all_trades if x > 0)
    losses = [abs(x) for x in all_trades if x < 0]
    gains = [x for x in all_trades if x > 0]
    equity = 0.0; peak = 0.0; max_dd = 0.0
    for tr in all_trades:
        equity += tr; peak = max(peak, equity); max_dd = min(max_dd, equity - peak)
    profit_factor = (sum(gains) / sum(losses)) if losses and sum(losses) else (999.0 if gains else 0.0)
    expectancy = mean(all_trades) if all_trades else 0.0
    pass_fail = "PASS" if trades_count >= 5 and expectancy > 0 and profit_factor >= 1.2 and max_dd >= -6 else "FAIL"
    result = {
        "ok": True, "version": V28_VERSION, "symbol": normalize_symbol(symbol), "period": period, "interval": interval,
        "config": {"train_bars": train_bars, "test_bars": test_bars, "fast": fast, "slow": slow},
        "bars": len(closes), "windows": windows, "metrics": {"trades": trades_count, "win_rate": round(wins / trades_count * 100, 2) if trades_count else 0, "expectancy_r": round(expectancy, 3), "total_return_r": round(sum(all_trades), 3), "max_drawdown_r": round(max_dd, 3), "profit_factor": round(profit_factor, 3), "pass_fail": pass_fail}
    }
    execute("""
        INSERT INTO v28_walk_forward_runs
        (created_at, symbol, period, interval, train_bars, test_bars, windows, trades, win_rate, expectancy_r, total_return_r, max_drawdown_r, profit_factor, pass_fail, config, result_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (now_iso(), normalize_symbol(symbol), period, interval, train_bars, test_bars, len(windows), trades_count, result["metrics"]["win_rate"], result["metrics"]["expectancy_r"], result["metrics"]["total_return_r"], result["metrics"]["max_drawdown_r"], result["metrics"]["profit_factor"], pass_fail, _json(result["config"]), _json(result)))
    return result


def recent(table, limit=50):
    init_v28_db()
    allowed = {"v28_signal_audit", "v28_open_signals", "v28_signal_outcomes", "v28_portfolio_risk_snapshots", "v28_walk_forward_runs"}
    if table not in allowed:
        return []
    return execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (int(limit),), fetch="all") or []


def performance_summary():
    init_v28_db()
    rows = execute("SELECT * FROM v28_open_signals WHERE status='CLOSED' ORDER BY id DESC LIMIT 500", fetch="all") or []
    trades = len(rows)
    wins = sum(1 for r in rows if safe_float(r.get("return_r"), 0) > 0)
    total_r = sum(safe_float(r.get("return_r"), 0) or 0 for r in rows)
    avg_r = total_r / trades if trades else 0
    return {"closed_trades": trades, "win_rate_pct": round(wins / trades * 100, 2) if trades else 0, "total_return_r": round(total_r, 3), "expectancy_r": round(avg_r, 3)}


def dashboard_payload():
    init_v28_db()
    audit = recent("v28_signal_audit", 30)
    open_rows = recent("v28_open_signals", 50)
    risk = recent("v28_portfolio_risk_snapshots", 10)
    wf = recent("v28_walk_forward_runs", 10)
    perf = performance_summary()
    total_audit = execute("SELECT COUNT(*) AS n FROM v28_signal_audit", fetch="one") or {"n": 0}
    pass_audit = execute("SELECT COUNT(*) AS n FROM v28_signal_audit WHERE decision IN ('PASS','SEND','SENT','ALLOW')", fetch="one") or {"n": 0}
    return {
        "ok": True, "version": V28_VERSION, "updated_at": now_iso(),
        "signal": {"total_audit_records": total_audit.get("n", 0), "passed_records": pass_audit.get("n", 0), "latest_audit": audit},
        "risk": {"latest_snapshots": risk, "open_positions": [r for r in open_rows if r.get("status") == "OPEN"]},
        "performance": {**perf, "latest_outcomes": recent("v28_signal_outcomes", 30), "latest_walk_forward": wf},
        "compliance": {"audit_db": "ACTIVE", "outcome_scheduler": "ACTIVE_ON_DEMAND", "limitations": ["No broker execution integration", "No immutable external log store", "SQLite default; use managed PostgreSQL for true fund operations"]}
    }


def html_table(rows, max_cols=12):
    if not rows:
        return "<p>No records.</p>"
    keys = list(rows[0].keys())[:max_cols]
    html = "<table><tr>" + "".join(f"<th>{k}</th>" for k in keys) + "</tr>"
    for r in rows:
        html += "<tr>" + "".join(f"<td>{str(r.get(k,''))[:160]}</td>" for k in keys) + "</tr>"
    return html + "</table>"


def dashboard_html():
    p = dashboard_payload()
    return f"""
    <html><head><meta charset='utf-8'><title>V28 Fund Validation Core</title>
    <style>
      body{{font-family:Arial, sans-serif;background:#07111f;color:#e5e7eb;padding:24px}}
      h1{{color:#38bdf8}} h2{{color:#a7f3d0;margin-top:28px}} .grid{{display:grid;grid-template-columns:repeat(4,minmax(180px,1fr));gap:12px}}
      .card{{background:#111827;border:1px solid #334155;border-radius:10px;padding:14px}}
      table{{border-collapse:collapse;width:100%;font-size:12px;background:#0f172a}} th,td{{border:1px solid #334155;padding:7px;vertical-align:top}} th{{background:#1e293b;color:#bfdbfe}}
      a{{color:#93c5fd}}
    </style></head><body>
    <h1>V28 Fund Validation Core</h1>
    <p>แยก Dashboard เป็น Signal / Risk / Performance / Compliance และใช้ฐานข้อมูลจริงสำหรับ Audit + Outcome</p>
    <p><a href='/v28/fund-dashboard.json'>JSON</a> | <a href='/v28/outcome/run'>Run Outcome Scheduler</a> | <a href='/v28/risk'>Portfolio Risk</a> | <a href='/v28/walk-forward?symbol=SPY'>Walk-forward SPY</a></p>
    <div class='grid'>
      <div class='card'><b>Audit Records</b><br>{p['signal']['total_audit_records']}</div>
      <div class='card'><b>Passed</b><br>{p['signal']['passed_records']}</div>
      <div class='card'><b>Closed Trades</b><br>{p['performance']['closed_trades']}</div>
      <div class='card'><b>Expectancy R</b><br>{p['performance']['expectancy_r']}</div>
    </div>
    <h2>Signal Audit</h2>{html_table(p['signal']['latest_audit'])}
    <h2>Risk</h2>{html_table(p['risk']['latest_snapshots'])}<h3>Open Positions</h3>{html_table(p['risk']['open_positions'])}
    <h2>Performance</h2><p>Win Rate: {p['performance']['win_rate_pct']}% | Total R: {p['performance']['total_return_r']}</p>{html_table(p['performance']['latest_outcomes'])}<h3>Walk-forward Runs</h3>{html_table(p['performance']['latest_walk_forward'])}
    <h2>Compliance</h2><pre>{_json(p['compliance'])}</pre>
    </body></html>
    """
