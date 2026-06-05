
# Module: Paper Trader / Mock Broker
from .v35_trading_engine import Portfolio, Trade
from .v35_risk_control import check_drawdown

class PaperTrader:
    def __init__(self):
        self.portfolio = Portfolio()

    def execute_trade(self, symbol, entry, qty, stop, take_profit):
        trade = Trade(symbol, entry, qty, stop, take_profit)
        if check_drawdown(self.portfolio):
            self.portfolio.open_trade(trade)
            return True
        return False
