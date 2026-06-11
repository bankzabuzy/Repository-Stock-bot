from dataclasses import dataclass
from datetime import datetime

@dataclass
class TaxLot:
    symbol: str
    side: str
    qty: float
    price: float
    fee: float = 0.0
    tax_hint: str = "review_required"
    created_at: str = datetime.utcnow().isoformat()
