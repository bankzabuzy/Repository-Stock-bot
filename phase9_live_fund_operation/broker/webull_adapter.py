import os
from .base import BrokerAdapter

class WebullAdapter(BrokerAdapter):
    """
    Safe placeholder for Webull integration.
    Live orders are blocked unless explicit environment gates are enabled.
    Replace _sdk_place_order with official/approved Webull API client code after API approval.
    """
    def __init__(self):
        self.api_key = os.getenv("WEBULL_API_KEY")
        self.api_secret = os.getenv("WEBULL_API_SECRET")
        self.live_enabled = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"
        self.human_approval_required = os.getenv("HUMAN_APPROVAL_REQUIRED", "true").lower() == "true"

    def connect(self):
        return bool(self.api_key and self.api_secret)

    def account(self):
        if not self.connect():
            return {"equity": 0, "daily_loss_pct": 0, "last_prices": {}, "error": "WEBULL_API_KEY/SECRET not configured"}
        return {"equity": 0, "daily_loss_pct": 0, "last_prices": {}, "status": "connected_placeholder"}

    def positions(self):
        return {}

    def place_order(self, intent):
        if not self.live_enabled:
            raise RuntimeError("LIVE BLOCKED: set LIVE_TRADING_ENABLED=true only after paper/live validation.")
        if self.human_approval_required and not getattr(intent, "approved", False):
            raise RuntimeError("LIVE BLOCKED: human approval required.")
        raise NotImplementedError("Connect approved Webull order endpoint here.")

    def cancel_order(self, order_id):
        if not self.live_enabled:
            return False
        raise NotImplementedError("Connect approved Webull cancel endpoint here.")
