import os, json, urllib.request

class LineAlert:
    def __init__(self, token_env="LINE_CHANNEL_ACCESS_TOKEN"):
        self.token = os.getenv(token_env)
    def format_trade_alert(self, payload):
        if isinstance(payload, dict):
            return "PHASE9 TRADE ALERT\n" + "\n".join(f"{k}: {v}" for k,v in payload.items())
        return str(payload)
    def send(self, message):
        if not self.token:
            return {"sent": False, "reason": "LINE token not configured", "message": message}
        # LINE Messaging API endpoint placeholder; user must configure destination/channel flow.
        return {"sent": False, "reason": "LINE destination not configured in safe template", "message": message}
