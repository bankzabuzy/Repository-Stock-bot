class MultiSourceFeed:
    def __init__(self, sources=None):
        self.sources = sources or ["US_STOCKS", "THAI_STOCKS", "GOLD", "ETF", "CRYPTO", "FUTURES"]
    def fetch(self, symbols):
        return {s: {"price": 100.0, "volatility": 50.0, "liquidity": 70.0} for s in symbols}
