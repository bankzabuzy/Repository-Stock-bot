from dataclasses import asdict
class FillMonitor:
    def __init__(self):
        self.partial_fills = {}
    def update(self, report):
        remaining = max(float(report.requested_qty) - float(report.filled_qty), 0.0)
        if remaining > 0:
            self.partial_fills[report.order_id] = remaining
            return {"status": "PARTIAL", "remaining_qty": remaining}
        self.partial_fills.pop(report.order_id, None)
        return {"status": report.status, "remaining_qty": 0.0}
