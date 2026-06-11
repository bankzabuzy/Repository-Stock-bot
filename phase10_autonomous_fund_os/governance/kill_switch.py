class KillSwitch:
    def __init__(self, enabled=True):
        self.enabled = enabled
    def allow_execution(self):
        return not self.enabled
    def disable_trading(self):
        self.enabled = True
    def enable_shadow_only(self):
        self.enabled = True
        return "SHADOW_ONLY"
