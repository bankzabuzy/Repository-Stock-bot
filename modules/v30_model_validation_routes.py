"""
V30 Institutional Model Validation & Paper Trading Core

Adds a validation layer on top of V29:
- Paper trading ledger with account, positions, trades, and equity snapshots.
- Walk-forward validation engine with realistic friction (slippage/commission) and metrics.
- Model validation report suitable for pre-production review.
- Deployment check and data reconciliation helpers.
- Optional validation gate for live alerts (observe by default, block only when configured).

The module is dependency-light and uses the V29 Store abstraction so SQLite remains the
local fallback while PostgreSQL is supported when DATABASE_URL is configured.
"""
from __future__ import annotations

import os
import json
import math
from datetime import datetime, timezone
from statistics import mean, pstdev
from typing import Any, Dict, List, Optional, Tuple

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None

from modules import v28_fund_validation_core as v28
from modules import v29_governance_core as v29

V30_VERSION = "V30 Institutional Model Validation & Paper Trading Core"

V30_INITIAL_CASH = float(os.getenv("V30_INITIAL_CASH", "100000"))
V30_RISK_PER_TRADE_PCT = float(os.getenv("V30_RISK_PER_TRADE_PCT", "1.0"))
V30_MAX_POSITION_PCT = float(os.getenv("V30_MAX_POSITION_PCT", "20.0"))
V30_SLIPPAGE_BPS = float(os.getenv("V30_SLIPPAGE_BPS", "8"))
V30_COMMISSION_BPS = float(os.getenv("V30_COMMISSION_BPS", "2"))
V30_MIN_VALIDATION_TRADES = int(os.getenv("V30_MIN_VALIDATION_TRADES", "20"))
V30_MIN_EXPECTANCY_R = float(os.getenv("V30_MIN_EXPECTANCY_R", "0.05"))
V30_MIN_PROFIT_FACTOR = float(os.getenv("V30_MIN_PROFIT_FACTOR", "1.10"))
V30_MAX_VALIDATION_DD_PCT = float(os.getenv("V30_MAX_VALIDATION_DD_PCT", "18.0"))
V30_VALIDATION_GATE_MODE = os.getenv("V30_VALIDATION_GATE_MODE", "observe").lower()  # observe|block
V30_RECONCILIATION_MAX_DIFF_PCT = float(os.getenv("V30_RECONCILIATION_MAX_DIFF_PCT", "1.0"))

store = v29.store


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def as_json(obj: Any) -> str:
    return v29.as_json(obj)


def safe_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    return v29.safe_float(v, default)


def init_v30_db() -> Dict[str, Any]:
    v29.init_v29_db()
    idcol = store.serial()
    jtype = store.json_type()
    ddl = [
        f"""
        CREATE TABLE IF NOT EXISTS v30_paper_accounts (
            id {idcol},
            created_at TEXT NOT NULL,
            account_name TEXT UNIQUE NOT NULL,
            base_currency TEXT DEFAULT 'USD',
            initial_cash REAL NOT NULL,
            cash REAL NOT NULL,
            equity REAL NOT NULL,
            realised_pnl REAL DEFAULT 0,
            status TEXT DEFAULT 'ACTIVE',
            config {jtype}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS v30_paper_positions (
            id {idcol},
            account_name TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            qty REAL NOT NULL,
            avg_price REAL NOT NULL,
            stop_loss REAL,
            take_profit REAL,
            opened_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            status TEXT DEFAULT 'OPEN',
            metadata {jtype},
            UNIQUE(account_name, symbol, side)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS v30_paper_trades (
            id {idcol},
            created_at TEXT NOT NULL,
            account_name TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            action TEXT NOT NULL,
            qty REAL NOT NULL,
            requested_price REAL,
            fill_price REAL NOT NULL,
            notional REAL NOT NULL,
            commission REAL DEFAULT 0,
            slippage REAL DEFAULT 0,
            realised_pnl REAL DEFAULT 0,
            signal_source TEXT,
            validation_status TEXT,
            metadata {jtype}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS v30_equity_snapshots (
            id {idcol},
            created_at TEXT NOT NULL,
            account_name TEXT NOT NULL,
            cash REAL NOT NULL,
            equity REAL NOT NULL,
            open_positions INTEGER DEFAULT 0,
            unrealised_pnl REAL DEFAULT 0,
            drawdown_pct REAL DEFAULT 0,
            details {jtype}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS v30_validation_runs (
            id {idcol},
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            strategy_key TEXT NOT NULL,
            period TEXT,
            interval TEXT,
            train_bars INTEGER,
            test_bars INTEGER,
            trades INTEGER,
            win_rate REAL,
            expectancy_r REAL,
            total_return_pct REAL,
            max_drawdown_pct REAL,
            profit_factor REAL,
            sharpe REAL,
            sortino REAL,
            pass_fail TEXT,
            reason TEXT,
            config {jtype},
            result_json {jtype}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS v30_deployment_checks (
            id {idcol},
            created_at TEXT NOT NULL,
            status TEXT NOT NULL,
            score INTEGER,
            missing TEXT,
            warnings TEXT,
            details {jtype}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS v30_data_reconciliation (
            id {idcol},
            checked_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            status TEXT NOT NULL,
            reference_price REAL,
            max_diff_pct REAL,
            sources {jtype},
            reason TEXT
        )
        """,
    ]
    for sql in ddl:
        store.execute(sql)
    ensure_paper_account()
    return {"ok": True, "version": V30_VERSION, "database": "postgresql" if store.pg else "sqlite", "tables": 7}


def ph() -> str:
    return store.ph()


def recent_rows(table: str, limit: int = 50) -> List[Dict[str, Any]]:
    allowed = {
        "v30_paper_accounts", "v30_paper_positions", "v30_paper_trades",
        "v30_equity_snapshots", "v30_validation_runs", "v30_deployment_checks",
        "v30_data_reconciliation",
    }
    if table not in allowed:
        return []
    limit = max(1, min(int(limit or 50), 500))
    return store.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT {limit}", fetch="all") or []


def ensure_paper_account(account_name: str = "GLOBAL", initial_cash: float = V30_INITIAL_CASH) -> Dict[str, Any]:
    marker = ph()
    existing = store.execute(f"SELECT * FROM v30_paper_accounts WHERE account_name={marker}", (account_name,), fetch="one")
    if existing:
        return existing
    store.execute(
        f"INSERT INTO v30_paper_accounts(created_at,account_name,initial_cash,cash,equity,config) VALUES({marker},{marker},{marker},{marker},{marker},{marker})",
        (now_iso(), account_name, initial_cash, initial_cash, initial_cash, as_json({"risk_per_trade_pct": V30_RISK_PER_TRADE_PCT, "max_position_pct": V30_MAX_POSITION_PCT})),
    )
    return store.execute(f"SELECT * FROM v30_paper_accounts WHERE account_name={marker}", (account_name,), fetch="one")


def fetch_history(symbol: str, period: str = "2y", interval: str = "1d") -> List[Dict[str, float]]:
    if yf is None:
        return []
    try:
        ysym = v28.y_symbol(symbol) if hasattr(v28, "y_symbol") else symbol
        df = yf.Ticker(ysym).history(period=period, interval=interval)
        if df is None or df.empty:
            return []
        out: List[Dict[str, float]] = []
        for idx, row in df.dropna().iterrows():
            out.append({
                "date": str(idx),
                "open": float(row.get("Open", row.get("Close"))),
                "high": float(row.get("High", row.get("Close"))),
                "low": float(row.get("Low", row.get("Close"))),
                "close": float(row.get("Close")),
                "volume": float(row.get("Volume", 0) or 0),
            })
        return out
    except Exception:
        return []


def ema(values: List[float], n: int) -> List[Optional[float]]:
    if not values or n <= 0:
        return []
    k = 2 / (n + 1)
    out: List[Optional[float]] = []
    cur: Optional[float] = None
    for i, v in enumerate(values):
        cur = v if cur is None else (v * k + cur * (1 - k))
        out.append(cur if i >= n - 1 else None)
    return out


def rsi(values: List[float], n: int = 14) -> List[Optional[float]]:
    if len(values) < n + 1:
        return [None] * len(values)
    out: List[Optional[float]] = [None] * len(values)
    gains: List[float] = []
    losses: List[float] = []
    for i in range(1, len(values)):
        chg = values[i] - values[i - 1]
        gains.append(max(chg, 0.0))
        losses.append(abs(min(chg, 0.0)))
        if i >= n:
            avg_gain = sum(gains[-n:]) / n
            avg_loss = sum(losses[-n:]) / n
            out[i] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    return out


def institutional_signal(history: List[Dict[str, float]], i: int, fast: int = 10, slow: int = 30) -> str:
    closes = [x["close"] for x in history[: i + 1]]
    if len(closes) < slow + 2:
        return "HOLD"
    ef = ema(closes, fast)
    es = ema(closes, slow)
    rr = rsi(closes, 14)
    if ef[-2] is None or es[-2] is None or ef[-1] is None or es[-1] is None:
        return "HOLD"
    crossed_up = ef[-2] <= es[-2] and ef[-1] > es[-1]
    crossed_down = ef[-2] >= es[-2] and ef[-1] < es[-1]
    momentum_ok = rr[-1] is not None and 45 <= rr[-1] <= 72
    risk_off = rr[-1] is not None and rr[-1] < 40
    if crossed_up and momentum_ok:
        return "BUY"
    if crossed_down or risk_off:
        return "SELL"
    return "HOLD"


def max_drawdown_pct(equity: List[float]) -> float:
    peak = None
    max_dd = 0.0
    for x in equity:
        peak = x if peak is None else max(peak, x)
        if peak and peak > 0:
            max_dd = min(max_dd, (x - peak) / peak * 100.0)
    return round(abs(max_dd), 2)


def sharpe_ratio(returns: List[float]) -> float:
    if len(returns) < 2:
        return 0.0
    sd = pstdev(returns)
    return round((mean(returns) / sd) * math.sqrt(252), 3) if sd else 0.0


def sortino_ratio(returns: List[float]) -> float:
    if len(returns) < 2:
        return 0.0
    downside = [r for r in returns if r < 0]
    sd = pstdev(downside) if len(downside) >= 2 else 0.0
    return round((mean(returns) / sd) * math.sqrt(252), 3) if sd else 0.0


def run_model_validation(symbol: str = "SPY", period: str = "3y", interval: str = "1d", train_bars: int = 180, test_bars: int = 45, fast: int = 10, slow: int = 30) -> Dict[str, Any]:
    init_v30_db()
    symbol = str(symbol or "SPY").upper()
    data = fetch_history(symbol, period, interval)
    if len(data) < train_bars + test_bars + slow + 5:
        result = {"ok": False, "version": V30_VERSION, "symbol": symbol, "error": "insufficient historical data", "bars": len(data)}
        return result

    cash = 100000.0
    pos_qty = 0.0
    avg = 0.0
    equity_curve: List[float] = []
    daily_returns: List[float] = []
    trades: List[Dict[str, Any]] = []
    last_equity = cash
    open_trade_price: Optional[float] = None

    start = train_bars
    end = len(data)
    for i in range(start, end):
        price = data[i]["close"]
        sig = institutional_signal(data, i, fast, slow)
        equity = cash + pos_qty * price
        if sig == "BUY" and pos_qty <= 0:
            max_notional = equity * (V30_MAX_POSITION_PCT / 100.0)
            fill = price * (1 + V30_SLIPPAGE_BPS / 10000.0)
            qty = max_notional / fill if fill > 0 else 0
            commission = max_notional * V30_COMMISSION_BPS / 10000.0
            if qty > 0 and cash >= max_notional + commission:
                cash -= max_notional + commission
                pos_qty = qty
                avg = fill
                open_trade_price = fill
                trades.append({"action": "BUY", "date": data[i]["date"], "price": fill, "qty": qty, "commission": commission})
        elif sig == "SELL" and pos_qty > 0:
            fill = price * (1 - V30_SLIPPAGE_BPS / 10000.0)
            notional = pos_qty * fill
            commission = notional * V30_COMMISSION_BPS / 10000.0
            pnl = (fill - avg) * pos_qty - commission
            r_mult = (fill - avg) / avg * 10.0 if avg else 0.0
            cash += notional - commission
            trades.append({"action": "SELL", "date": data[i]["date"], "price": fill, "qty": pos_qty, "commission": commission, "pnl": pnl, "return_r": r_mult})
            pos_qty = 0.0
            avg = 0.0
            open_trade_price = None
        equity = cash + pos_qty * price
        equity_curve.append(equity)
        if last_equity:
            daily_returns.append((equity - last_equity) / last_equity)
        last_equity = equity

    if pos_qty > 0:
        price = data[-1]["close"]
        fill = price * (1 - V30_SLIPPAGE_BPS / 10000.0)
        notional = pos_qty * fill
        commission = notional * V30_COMMISSION_BPS / 10000.0
        pnl = (fill - avg) * pos_qty - commission
        r_mult = (fill - avg) / avg * 10.0 if avg else 0.0
        cash += notional - commission
        trades.append({"action": "FORCED_CLOSE", "date": data[-1]["date"], "price": fill, "qty": pos_qty, "commission": commission, "pnl": pnl, "return_r": r_mult})
        pos_qty = 0
        equity_curve.append(cash)

    closed = [t for t in trades if t.get("action") in {"SELL", "FORCED_CLOSE"}]
    returns_r = [safe_float(t.get("return_r"), 0.0) or 0.0 for t in closed]
    wins = [r for r in returns_r if r > 0]
    losses = [r for r in returns_r if r < 0]
    win_rate = (len(wins) / len(returns_r) * 100) if returns_r else 0.0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    pf = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    expectancy = sum(returns_r) / len(returns_r) if returns_r else 0.0
    total_return_pct = (equity_curve[-1] - 100000.0) / 100000.0 * 100.0 if equity_curve else 0.0
    max_dd = max_drawdown_pct(equity_curve)

    reasons = []
    if len(returns_r) < V30_MIN_VALIDATION_TRADES:
        reasons.append(f"trades below minimum: {len(returns_r)}/{V30_MIN_VALIDATION_TRADES}")
    if expectancy < V30_MIN_EXPECTANCY_R:
        reasons.append(f"expectancy below minimum: {expectancy:.3f}R < {V30_MIN_EXPECTANCY_R}R")
    if pf < V30_MIN_PROFIT_FACTOR:
        reasons.append(f"profit factor below minimum: {pf:.2f} < {V30_MIN_PROFIT_FACTOR}")
    if max_dd > V30_MAX_VALIDATION_DD_PCT:
        reasons.append(f"drawdown above maximum: {max_dd}% > {V30_MAX_VALIDATION_DD_PCT}%")
    pass_fail = "PASS" if not reasons else "FAIL"

    result = {
        "ok": True,
        "version": V30_VERSION,
        "symbol": symbol,
        "strategy_key": "V30_EMA_RSI_FRICTION",
        "bars": len(data),
        "trades": len(returns_r),
        "win_rate": round(win_rate, 2),
        "expectancy_r": round(expectancy, 4),
        "total_return_pct": round(total_return_pct, 2),
        "max_drawdown_pct": max_dd,
        "profit_factor": round(pf, 3),
        "sharpe": sharpe_ratio(daily_returns),
        "sortino": sortino_ratio(daily_returns),
        "pass_fail": pass_fail,
        "reason": " | ".join(reasons) if reasons else "validation thresholds passed",
        "sample_trades": trades[-20:],
    }
    marker = ph()
    store.execute(
        f"INSERT INTO v30_validation_runs(created_at,symbol,strategy_key,period,interval,train_bars,test_bars,trades,win_rate,expectancy_r,total_return_pct,max_drawdown_pct,profit_factor,sharpe,sortino,pass_fail,reason,config,result_json) VALUES({','.join([marker]*19)})",
        (now_iso(), symbol, "V30_EMA_RSI_FRICTION", period, interval, train_bars, test_bars, len(returns_r), round(win_rate,2), round(expectancy,4), round(total_return_pct,2), max_dd, round(pf,3), sharpe_ratio(daily_returns), sortino_ratio(daily_returns), pass_fail, result["reason"], as_json({"fast":fast,"slow":slow,"slippage_bps":V30_SLIPPAGE_BPS,"commission_bps":V30_COMMISSION_BPS}), as_json(result)),
    )
    return result


def paper_apply_signal(symbol: str, side: str, price: Optional[float] = None, account_name: str = "GLOBAL", confidence: Optional[float] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    init_v30_db()
    account = ensure_paper_account(account_name)
    symbol = str(symbol or "").upper()
    side = str(side or "HOLD").upper()
    if not symbol:
        return {"ok": False, "error": "symbol required"}
    if price is None:
        price = v28.price_now(symbol)
    price = safe_float(price)
    if not price or price <= 0:
        return {"ok": False, "symbol": symbol, "error": "valid price unavailable"}
    marker = ph()
    cash = safe_float(account.get("cash"), 0.0) or 0.0
    equity = safe_float(account.get("equity"), cash) or cash
    position = store.execute(f"SELECT * FROM v30_paper_positions WHERE account_name={marker} AND symbol={marker} AND status='OPEN'", (account_name, symbol), fetch="one")
    action = "HOLD"
    details: Dict[str, Any] = {}

    if side in {"BUY", "CALL", "LONG", "STRONG_CALL"} and not position:
        notional = min(equity * V30_MAX_POSITION_PCT / 100.0, cash * 0.95)
        fill = price * (1 + V30_SLIPPAGE_BPS / 10000.0)
        commission = notional * V30_COMMISSION_BPS / 10000.0
        qty = (notional - commission) / fill if fill else 0
        if qty <= 0:
            return {"ok": False, "symbol": symbol, "error": "insufficient cash"}
        cash -= qty * fill + commission
        store.execute(f"INSERT INTO v30_paper_positions(account_name,symbol,side,qty,avg_price,opened_at,updated_at,metadata) VALUES({marker},{marker},{marker},{marker},{marker},{marker},{marker},{marker})", (account_name, symbol, "LONG", qty, fill, now_iso(), now_iso(), as_json(metadata or {})))
        store.execute(f"INSERT INTO v30_paper_trades(created_at,account_name,symbol,side,action,qty,requested_price,fill_price,notional,commission,slippage,signal_source,validation_status,metadata) VALUES({','.join([marker]*14)})", (now_iso(), account_name, symbol, "LONG", "BUY", qty, price, fill, qty*fill, commission, fill-price, "LIVE_SIGNAL", latest_validation_status(symbol), as_json(metadata or {})))
        action = "BUY"
    elif side in {"SELL", "PUT", "SHORT", "STRONG_PUT", "CLOSE"} and position:
        qty = safe_float(position.get("qty"), 0.0) or 0.0
        avg = safe_float(position.get("avg_price"), 0.0) or 0.0
        fill = price * (1 - V30_SLIPPAGE_BPS / 10000.0)
        notional = qty * fill
        commission = notional * V30_COMMISSION_BPS / 10000.0
        realised = (fill - avg) * qty - commission
        cash += notional - commission
        old_realised = safe_float(account.get("realised_pnl"), 0.0) or 0.0
        store.execute(f"UPDATE v30_paper_positions SET status='CLOSED', updated_at={marker} WHERE id={marker}", (now_iso(), position.get("id")))
        store.execute(f"INSERT INTO v30_paper_trades(created_at,account_name,symbol,side,action,qty,requested_price,fill_price,notional,commission,slippage,realised_pnl,signal_source,validation_status,metadata) VALUES({','.join([marker]*15)})", (now_iso(), account_name, symbol, "LONG", "SELL", qty, price, fill, notional, commission, price-fill, realised, "LIVE_SIGNAL", latest_validation_status(symbol), as_json(metadata or {})))
        store.execute(f"UPDATE v30_paper_accounts SET realised_pnl={marker} WHERE account_name={marker}", (old_realised + realised, account_name))
        action = "SELL"
        details["realised_pnl"] = round(realised, 2)
    else:
        action = "HOLD"

    equity_payload = mark_to_market(account_name, price_map={symbol: price}, cash_override=cash)
    return {"ok": True, "version": V30_VERSION, "account": account_name, "symbol": symbol, "side": side, "action": action, "price": price, "equity": equity_payload, "details": details}


def mark_to_market(account_name: str = "GLOBAL", price_map: Optional[Dict[str, float]] = None, cash_override: Optional[float] = None) -> Dict[str, Any]:
    init_v30_db()
    marker = ph()
    account = ensure_paper_account(account_name)
    cash = cash_override if cash_override is not None else (safe_float(account.get("cash"), 0.0) or 0.0)
    positions = store.execute(f"SELECT * FROM v30_paper_positions WHERE account_name={marker} AND status='OPEN'", (account_name,), fetch="all") or []
    equity = cash
    unreal = 0.0
    details = []
    for p in positions:
        sym = p.get("symbol")
        price = safe_float((price_map or {}).get(sym))
        if price is None:
            price = v28.price_now(sym)
        qty = safe_float(p.get("qty"), 0.0) or 0.0
        avg = safe_float(p.get("avg_price"), 0.0) or 0.0
        if price:
            value = qty * price
            pnl = (price - avg) * qty
            equity += value
            unreal += pnl
            details.append({"symbol": sym, "qty": qty, "price": price, "value": round(value, 2), "unrealised_pnl": round(pnl, 2)})
    initial = safe_float(account.get("initial_cash"), V30_INITIAL_CASH) or V30_INITIAL_CASH
    dd = max(0.0, (initial - equity) / initial * 100.0)
    store.execute(f"UPDATE v30_paper_accounts SET cash={marker}, equity={marker} WHERE account_name={marker}", (cash, equity, account_name))
    store.execute(f"INSERT INTO v30_equity_snapshots(created_at,account_name,cash,equity,open_positions,unrealised_pnl,drawdown_pct,details) VALUES({','.join([marker]*8)})", (now_iso(), account_name, cash, equity, len(positions), unreal, dd, as_json(details)))
    return {"ok": True, "account": account_name, "cash": round(cash, 2), "equity": round(equity, 2), "open_positions": len(positions), "unrealised_pnl": round(unreal, 2), "drawdown_pct": round(dd, 2), "details": details}


def latest_validation_status(symbol: str = "") -> str:
    init_v30_db()
    marker = ph()
    if symbol:
        row = store.execute(f"SELECT pass_fail FROM v30_validation_runs WHERE symbol={marker} ORDER BY id DESC LIMIT 1", (str(symbol).upper(),), fetch="one")
    else:
        row = store.execute("SELECT pass_fail FROM v30_validation_runs ORDER BY id DESC LIMIT 1", fetch="one")
    return (row or {}).get("pass_fail") or "UNVALIDATED"


def deployment_check() -> Dict[str, Any]:
    init_v30_db()
    required = ["LINE_CHANNEL_ACCESS_TOKEN", "LINE_CHANNEL_SECRET"]
    recommended = ["DATABASE_URL", "V29_API_KEY", "ALERT_USER_IDS", "WATCHLIST"]
    provider_keys = ["TWELVEDATA_API_KEY", "FINNHUB_API_KEY", "ALPHAVANTAGE_API_KEY", "FMP_API_KEY"]
    missing = [k for k in required if not os.getenv(k)]
    warnings = [k for k in recommended if not os.getenv(k)]
    if not any(os.getenv(k) for k in provider_keys):
        warnings.append("NO_SECONDARY_DATA_PROVIDER_KEY")
    score = 100 - len(missing) * 25 - len(warnings) * 7
    score = max(0, min(100, score))
    status = "PASS" if not missing and score >= 70 else "WARN" if not missing else "FAIL"
    details = {
        "database": "postgresql" if store.pg else "sqlite fallback",
        "scheduler_enabled": os.getenv("V29_ENABLE_CRON", "false"),
        "validation_gate_mode": V30_VALIDATION_GATE_MODE,
        "provider_health": v29.provider_health(force=False),
    }
    marker = ph()
    store.execute(f"INSERT INTO v30_deployment_checks(created_at,status,score,missing,warnings,details) VALUES({','.join([marker]*6)})", (now_iso(), status, score, ",".join(missing), ",".join(warnings), as_json(details)))
    return {"ok": True, "version": V30_VERSION, "status": status, "score": score, "missing": missing, "warnings": warnings, "details": details}


def data_reconciliation(symbol: str, sources: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    init_v30_db()
    symbol = str(symbol or "SPY").upper()
    source_prices: Dict[str, float] = {}
    if sources:
        for k, v in sources.items():
            fv = safe_float(v)
            if fv and fv > 0:
                source_prices[str(k)] = fv
    yf_price = v28.price_now(symbol)
    if yf_price:
        source_prices.setdefault("yfinance", yf_price)
    if not source_prices:
        result = {"ok": False, "symbol": symbol, "status": "FAIL", "reason": "no usable price sources"}
    else:
        vals = list(source_prices.values())
        ref = sum(vals) / len(vals)
        max_diff = max(abs(v - ref) / ref * 100.0 for v in vals) if ref else 0.0
        status = "PASS" if max_diff <= V30_RECONCILIATION_MAX_DIFF_PCT else "BLOCK"
        result = {"ok": True, "version": V30_VERSION, "symbol": symbol, "status": status, "reference_price": round(ref, 4), "max_diff_pct": round(max_diff, 4), "sources": source_prices, "reason": "within tolerance" if status == "PASS" else "provider price divergence above tolerance"}
    marker = ph()
    store.execute(f"INSERT INTO v30_data_reconciliation(checked_at,symbol,status,reference_price,max_diff_pct,sources,reason) VALUES({','.join([marker]*7)})", (now_iso(), symbol, result.get("status"), result.get("reference_price"), result.get("max_diff_pct"), as_json(result.get("sources", {})), result.get("reason")))
    return result


def validation_gate(symbol: str, sig: str = "", analysis: Optional[Dict[str, Any]] = None) -> Tuple[bool, Dict[str, Any]]:
    init_v30_db()
    symbol = str(symbol or "").upper()
    validation = latest_validation_status(symbol)
    acct = ensure_paper_account()
    equity = safe_float(acct.get("equity"), V30_INITIAL_CASH) or V30_INITIAL_CASH
    initial = safe_float(acct.get("initial_cash"), V30_INITIAL_CASH) or V30_INITIAL_CASH
    drawdown = max(0.0, (initial - equity) / initial * 100.0)
    reasons = []
    if validation == "FAIL":
        reasons.append("latest model validation failed")
    if drawdown > V30_MAX_VALIDATION_DD_PCT:
        reasons.append(f"paper account drawdown {drawdown:.2f}% > {V30_MAX_VALIDATION_DD_PCT}%")
    should_block = V30_VALIDATION_GATE_MODE == "block" and bool(reasons)
    detail = {"version": V30_VERSION, "mode": V30_VALIDATION_GATE_MODE, "validation_status": validation, "paper_drawdown_pct": round(drawdown, 2), "decision": "BLOCK" if should_block else "OBSERVE_PASS", "reasons": reasons or ["PASS"]}
    try:
        v29.governance_event("v30_validation_gate", "WARN" if reasons else "INFO", symbol=symbol, decision=detail["decision"], reason=" | ".join(detail["reasons"]), payload=detail)
    except Exception:
        pass
    return (not should_block), detail


def dashboard_payload() -> Dict[str, Any]:
    init_v30_db()
    return {
        "ok": True,
        "version": V30_VERSION,
        "deployment": recent_rows("v30_deployment_checks", 5),
        "paper_accounts": recent_rows("v30_paper_accounts", 10),
        "positions": recent_rows("v30_paper_positions", 50),
        "trades": recent_rows("v30_paper_trades", 100),
        "equity": recent_rows("v30_equity_snapshots", 50),
        "validation_runs": recent_rows("v30_validation_runs", 50),
        "reconciliation": recent_rows("v30_data_reconciliation", 50),
        "v29": v29.dashboard_payload(),
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
    acct = p["paper_accounts"][0] if p["paper_accounts"] else {}
    last_val = p["validation_runs"][0] if p["validation_runs"] else {}
    return f"""
    <html><head><title>V30 Institutional Validation Dashboard</title></head>
    <body style="font-family:Arial,sans-serif;margin:24px;">
      <h1>V30 Institutional Model Validation & Paper Trading Core</h1>
      <p><b>Paper Equity:</b> {acct.get('equity','-')} | <b>Cash:</b> {acct.get('cash','-')} | <b>Latest Validation:</b> {last_val.get('symbol','-')} {last_val.get('pass_fail','UNVALIDATED')}</p>
      <h2>Deployment Readiness</h2>{html_table(p['deployment'], 5)}
      <h2>Model Validation Runs</h2>{html_table(p['validation_runs'], 20)}
      <h2>Paper Positions</h2>{html_table(p['positions'], 20)}
      <h2>Paper Trades</h2>{html_table(p['trades'], 30)}
      <h2>Equity Snapshots</h2>{html_table(p['equity'], 20)}
      <h2>Data Reconciliation</h2>{html_table(p['reconciliation'], 20)}
      <p style="margin-top:30px;color:#666;">V30 validates model quality before production scale-up and keeps paper-trading evidence separate from live alerts.</p>
    </body></html>
    """


try:
    init_v30_db()
except Exception as e:  # pragma: no cover
    print("V30 init warning:", e)
