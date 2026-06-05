
# Module: Trading Engine
from .v35_market_data import get_price

class Trade:
    def __init__(self, symbol, entry, qty, stop, take_profit):
        self.symbol = symbol
        self.entry = entry
        self.qty = qty
        self.stop = stop
        self.take_profit = take_profit
        self.status = 'OPEN'
        self.pnl = 0.0

class Portfolio:
    def __init__(self, cash=100000):
        self.cash = cash
        self.positions = []
        self.history = []

    def open_trade(self, trade):
        if self.cash >= trade.entry*trade.qty:
            self.cash -= trade.entry*trade.qty
            self.positions.append(trade)
            self.history.append({'action':'OPEN','trade':trade})
            return True
        return False
