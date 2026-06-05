
# Module: Market Data Handler
# รองรับหุ้นสหรัฐฯ หุ้นไทย ทอง น้ำมัน ออฟชั่น
import yfinance as yf
import pandas as pd

def get_price(symbol, period='1y', interval='1d'):
    data = yf.download(symbol, period=period, interval=interval, auto_adjust=True, progress=False)['Close']
    return data
