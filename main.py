import os
import yfinance as yf
from flask import Flask, request, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# --- CONFIGURATION ---
DATABASE_URL = os.getenv("DATABASE_URL")
ACCOUNT_EQUITY = float(os.getenv("ACCOUNT_EQUITY", 100000))
RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", 1))
MAX_PORTFOLIO_HEAT_PCT = float(os.getenv("MAX_PORTFOLIO_HEAT_PCT", 6))

def get_db_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# --- RISK ENGINE (Volatility Based) ---
def calculate_dynamic_position(symbol, entry_price):
    ticker = yf.Ticker(symbol.upper())
    hist = ticker.history(period="14d")
    atr = (hist['High'] - hist['Low']).mean()
    stop_loss = entry_price - (2 * atr)
    
    dollar_risk = ACCOUNT_EQUITY * (RISK_PER_TRADE_PCT / 100)
    qty = int(dollar_risk / abs(entry_price - stop_loss))
    return round(stop_loss, 2), max(1, qty), round(atr, 2)

# --- DASHBOARD & ANALYTICS ---
@app.route("/v22/dashboard")
def v22_dashboard():
    # แสดงสถานะความผันผวนของพอร์ต
    symbols = ["NVDA", "AAPL", "MSFT", "AMD", "TSLA"]
    html = "<h1>V22 Professional Dashboard</h1><table border='1'><tr><th>Symbol</th><th>ATR</th><th>Stop (2xATR)</th></tr>"
    for s in symbols:
        t = yf.Ticker(s)
        h = t.history(period="14d")
        atr = (h['High'] - h['Low']).mean()
        stop = float(h['Close'].iloc[-1]) - (2 * atr)
        html += f"<tr><td>{s}</td><td>{atr:.2f}</td><td>{stop:.2f}</td></tr>"
    return html + "</table>"

# --- JOURNALING & EXECUTION ---
@app.route("/v22/journal/open")
def v22_open_trade():
    symbol = request.args.get("symbol")
    entry = float(request.args.get("entry"))
    stop, qty, atr = calculate_dynamic_position(symbol, entry)
    
    # Check Heat
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO trade_journal (symbol, entry_price, stop_price, qty, status) VALUES (%s, %s, %s, %s, 'OPEN')", 
                        (symbol, entry, stop, qty))
        conn.commit()
    return jsonify({"status": "Trade Opened", "qty": qty, "stop": stop})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 3000)))
