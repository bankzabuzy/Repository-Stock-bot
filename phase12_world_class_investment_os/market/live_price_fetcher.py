import yfinance as yf

class LivePriceFetcher:
    def __init__(self, symbols=None):
        self.symbols = symbols or []

    def fetch(self):
        results = {}
        for s in self.symbols:
            ticker = yf.Ticker(s)
            data = ticker.history(period="2d")
            if data.empty or len(data) < 2:
                continue
            prev_close = data['Close'][-2]
            close = data['Close'][-1]
            premarket = close  # placeholder for pre-market
            change_close = (close - prev_close)/prev_close*100
            change_premarket = (premarket - prev_close)/prev_close*100
            results[s] = {
                "close": round(close,2),
                "pre_market": round(premarket,2),
                "change_close_pct": round(change_close,2),
                "change_premarket_pct": round(change_premarket,2)
            }
        return results
