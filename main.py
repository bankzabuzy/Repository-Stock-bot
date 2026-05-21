import yfinance as yf
import requests
import schedule
import time
import json
import pytz
from datetime import datetime

LINE_TOKEN = "0JZHbJ2b/Vu71Ex3Xe2T5a2PDVk1iu5rEe+p4r0icSE1lbFZxoBUbxIDFqUxEp5CTsu6o2Iku9ECQcAzir4V+b PFE+5KBZJ1WsNJPWto8wkYXwrnHXYhBToIVXzAIbg8ZxoWWnPvyk99S7VLuZY98gdB04t89/1O/w1cDnyilFU="
LINE_USER_ID = "U4eaab8ca41c138c8b8a9c18768ee2d31"

US_STOCKS = ["NVDA", "AAPL", "TSLA"]
TH_STOCKS = ["PTT.BK", "ADVANC.BK", "AOT.BK", "CPALL.BK", "SCB.BK"]
TH = pytz.timezone("Asia/Bangkok")

def get_stock_data(symbol):
    tk = yf.Ticker(symbol)
    df = tk.history(period="3mo")
    df['SMA20'] = df['Close'].rolling(20).mean()
    df['EMA20'] = df['Close'].ewm(span=20).mean()
    delta = df['Close'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    return {
        "symbol": symbol,
        "price": float(latest['Close']),
        "change_pct": float((latest['Close']-prev['Close'])/prev['Close']*100),
        "rsi": float(latest['RSI']),
        "sma20": float(latest['SMA20']),
        "ema20": float(latest['EMA20']),
    }

def analyze_signal(data):
    signals = []
    score = 0
    if data['price'] > data['sma20']:
        signals.append("SMA: OK"); score += 1
    else:
        signals.append("SMA: ต่ำกว่าเส้น"); score -= 1
    if data['price'] > data['ema20']:
        signals.append("EMA: OK"); score += 1
    else:
        signals.append("EMA: ต่ำกว่าเส้น"); score -= 1
    rsi = data['rsi']
    if rsi < 30:
        signals.append(f"RSI: Oversold {rsi:.1f}"); score += 2
    elif rsi > 70:
        signals.append(f"RSI: Overbought {rsi:.1f}"); score -= 2
    else:
        signals.append(f"RSI: ปกติ {rsi:.1f}"); score += 1
    verdict = "แนะนำซื้อ" if score >= 3 else "ระวัง/ขาย" if score <= -2 else "ถือสังเกต"
    return signals, verdict

def send_line(msg):
    url = "https://api.line.me/v2/bot/message/push"
    payload = json.dumps({
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": msg}]
    }).encode("utf-8")
    req = requests.Request("POST", url,
        headers={
            "Authorization": f"Bearer {LINE_TOKEN}",
            "Content-Type": "application/json; charset=utf-8"
        },
        data=payload
    )
    prepared = req.prepare()
    s = requests.Session()
    r = s.send(prepared)
    print(f"Response: {r.status_code}")
    return r.status_code

def send_report(stocks, label):
    now = datetime.now(TH).strftime("%d/%m/%Y %H:%M")
    print(f"[{now}] ส่งรายงาน{label}...")
    for symbol in stocks:
        try:
            data = get_stock_data(symbol)
            signals, verdict = analyze_signal(data)
            sign = "+" if data['change_pct'] > 0 else ""
            currency = "บาท" if ".BK" in symbol else "$"
            msg = "\n".join([
                f"[{symbol}] หุ้น{label}",
                f"ราคา: {data['price']:.2f} {currency}",
                f"เปลี่ยนแปลง: {sign}{data['change_pct']:.2f}%",
                "",
                "TECHNICAL",
                f"- {signals[0]}",
                f"- {signals[1]}",
                f"- {signals[2]}",
                "",
                f"สรุป: {verdict}",
                now
            ])
            send_line(msg)
            time.sleep(1)
        except Exception as e:
            print(f"Error {symbol}: {e}")

def us_report():
    send_report(US_S
