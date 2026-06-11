class PnLEngine:
    def mark_to_market(self, positions, prices):
        total = 0.0
        by_symbol = {}
        for sym, qty in positions.items():
            value = float(qty) * float(prices.get(sym, 0))
            by_symbol[sym] = value
            total += value
        return {"gross_market_value": total, "by_symbol": by_symbol}
