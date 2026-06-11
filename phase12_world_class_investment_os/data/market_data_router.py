class MarketDataRouter:
    """
    Offline-safe deterministic market data router.
    Replace adapters with approved APIs for production.
    """
    def __init__(self):
        self.default_prices = {
            "AAPL": 190.0, "NVDA": 120.0, "TSM": 170.0, "QQQ": 450.0,
            "GLD": 220.0, "XAUUSD": 2350.0, "PTT.BK": 35.0, "CPALL.BK": 58.0
        }

    def fetch_snapshot(self, symbols):
        out = {}
        for sym in symbols:
            px = float(self.default_prices.get(sym.upper(), 100.0))
            out[sym.upper()] = {
                "price": px,
                "volume_score": 75.0 if px >= 50 else 62.0,
                "liquidity_score": 80.0 if px >= 50 else 65.0,
                "volatility_score": 45.0 if sym.upper() in {"GLD", "XAUUSD"} else 55.0,
                "trend_score": 68.0 if sym.upper() in {"NVDA", "TSM", "QQQ"} else 55.0,
                "asset_class": self.asset_class(sym)
            }
        return out

    def asset_class(self, symbol):
        s = symbol.upper()
        if s.endswith(".BK"):
            return "THAI_STOCKS"
        if s in {"GLD", "XAUUSD"}:
            return "GOLD"
        if s in {"QQQ", "SPY", "TLT"}:
            return "ETF"
        return "US_STOCKS"
