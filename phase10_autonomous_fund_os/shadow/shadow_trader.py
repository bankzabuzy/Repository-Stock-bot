from datetime import datetime, timezone
class ShadowTrader:
    def __init__(self):
        self.ledger = []
    def record(self, decision):
        item = dict(decision)
        item["shadow_ts"] = datetime.now(timezone.utc).isoformat()
        item["status"] = "SHADOW_RECORDED"
        self.ledger.append(item)
        return item
