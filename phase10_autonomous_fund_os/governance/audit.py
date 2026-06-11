import json
from datetime import datetime, timezone
class AuditTrail:
    def __init__(self):
        self.events = []
    def log(self, event_type, payload):
        event = {"ts": datetime.now(timezone.utc).isoformat(), "event_type": event_type, "payload": payload}
        self.events.append(event)
        return event
    def export_json(self):
        return json.dumps(self.events, ensure_ascii=False, indent=2, default=str)
