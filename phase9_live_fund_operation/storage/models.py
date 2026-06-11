from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

@dataclass
class OrderIntent:
    symbol: str
    side: str
    qty: float
    order_type: str = "market"
    limit_price: Optional[float] = None
    strategy: str = "unknown"
    confidence: str = "B"
    asset_class: str = "US_STOCKS"
    reason: str = ""
    approved: bool = False
    created_at: str = datetime.utcnow().isoformat()

    def key(self) -> str:
        price = "" if self.limit_price is None else f"{self.limit_price:.4f}"
        return f"{self.symbol.upper()}|{self.side.upper()}|{self.qty}|{self.order_type}|{price}|{self.strategy}"

@dataclass
class ExecutionReport:
    order_id: str
    symbol: str
    side: str
    requested_qty: float
    filled_qty: float
    avg_price: float
    status: str
    broker: str = "paper"
    message: str = ""
    ts: str = datetime.utcnow().isoformat()
