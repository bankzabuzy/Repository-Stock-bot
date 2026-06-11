class SafetyGate:
    def check_env(self, env_vars):
        return all(env_vars.values())
