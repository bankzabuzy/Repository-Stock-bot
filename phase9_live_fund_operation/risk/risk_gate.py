import hashlib, time
from dataclasses import asdict
from typing import Dict, List, Tuple

class RiskGate:
    def __init__(self, config: Dict):
        self.config = config or {}
        risk = self.config.get("risk", {})
        self.max_order_pct_equity = risk.get("max_order_pct_equity", 0.04)
        self.max_portfolio_heat = risk.get("max_portfolio_heat", 0.12)
        self.max_symbol_exposure = risk.get("max_symbol_exposure", 0.08)
        self.max_sector_exposure = risk.get("max_sector_exposure", 0.25)
        self.max_daily_loss_pct = risk.get("max_daily_loss_pct", 0.02)
        self.duplicate_window_seconds = risk.get("duplicate_window_seconds", 900)
        self._recent = {}

    def _hash_intent(self, intent) -> str:
        key = intent.key() if hasattr(intent, "key") else str(intent)
        return hashlib.sha256(key.encode()).hexdigest()

    def validate(self, intent, account: Dict, portfolio: Dict=None) -> Tuple[bool, List[str], str]:
        portfolio = portfolio or {}
        reasons = []
        equity = float(account.get("equity", 0) or 0)
        price = float(account.get("last_prices", {}).get(intent.symbol, intent.limit_price or 0) or 0)
        if equity <= 0:
            reasons.append("BLOCK: account equity missing or zero")
        if intent.qty <= 0:
            reasons.append("BLOCK: qty must be positive")
        if intent.side.lower() not in {"buy", "sell"}:
            reasons.append("BLOCK: side must be buy/sell")
        order_value = price * float(intent.qty)
        if equity > 0 and order_value / equity > self.max_order_pct_equity:
            reasons.append(f"BLOCK: order size {order_value/equity:.2%} exceeds {self.max_order_pct_equity:.2%}")
        symbol_exposure = float(portfolio.get("symbol_exposure", {}).get(intent.symbol, 0))
        if symbol_exposure > self.max_symbol_exposure:
            reasons.append(f"BLOCK: symbol exposure exceeds {self.max_symbol_exposure:.2%}")
        daily_loss = abs(float(account.get("daily_loss_pct", 0) or 0))
        if daily_loss >= self.max_daily_loss_pct:
            reasons.append(f"BLOCK: daily loss {daily_loss:.2%} exceeds {self.max_daily_loss_pct:.2%}")

        h = self._hash_intent(intent)
        now = time.time()
        old = self._recent.get(h)
        if old and now - old < self.duplicate_window_seconds:
            reasons.append("BLOCK: duplicate order protection")
        if not reasons:
            self._recent[h] = now
        return (len(reasons) == 0), reasons, h
