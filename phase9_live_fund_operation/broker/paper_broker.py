import uuid
from .base import BrokerAdapter
from ..storage.models import ExecutionReport

class PaperBroker(BrokerAdapter):
    def __init__(self, starting_equity=100000.0, prices=None):
        self.equity = starting_equity
        self.prices = prices or {"AAPL": 190, "NVDA": 120, "TSM": 170, "QQQ": 450, "GLD": 220, "XAUUSD": 2350}
        self._positions = {}
    def connect(self): return True
    def account(self):
        return {"equity": self.equity, "daily_loss_pct": 0.0, "last_prices": self.prices}
    def positions(self): return self._positions
    def place_order(self, intent):
        px = intent.limit_price or self.prices.get(intent.symbol.upper(), 100.0)
        oid = "PAPER-" + uuid.uuid4().hex[:12]
        signed = intent.qty if intent.side.lower()=="buy" else -intent.qty
        self._positions[intent.symbol.upper()] = self._positions.get(intent.symbol.upper(), 0) + signed
        return ExecutionReport(order_id=oid, symbol=intent.symbol.upper(), side=intent.side, requested_qty=intent.qty,
                               filled_qty=intent.qty, avg_price=float(px), status="FILLED", broker="paper",
                               message="paper fill simulated")
    def cancel_order(self, order_id): return True
