import json, hashlib
from datetime import datetime, timezone

class ImmutableAudit:
    def __init__(self):
        self.chain = []

    def log(self, event_type, payload):
        prev = self.chain[-1]["hash"] if self.chain else "GENESIS"
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "payload": payload,
            "prev_hash": prev
        }
        raw = json.dumps(event, sort_keys=True, ensure_ascii=False, default=str)
        event["hash"] = hashlib.sha256(raw.encode()).hexdigest()
        self.chain.append(event)
        return event

    def verify(self):
        prev = "GENESIS"
        for event in self.chain:
            if event["prev_hash"] != prev:
                return False
            old_hash = event["hash"]
            clone = dict(event)
            clone.pop("hash", None)
            raw = json.dumps(clone, sort_keys=True, ensure_ascii=False, default=str)
            if hashlib.sha256(raw.encode()).hexdigest() != old_hash:
                return False
            prev = old_hash
        return True
