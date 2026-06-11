class ShadowLearningLoop:
    def update(self, weights, realized):
        updated = dict(weights)
        for sym, w in list(updated.items()):
            r = float(realized.get(sym, 0))
            if r > 0:
                updated[sym] = w * 1.03
            elif r < 0:
                updated[sym] = w * 0.92
        total = sum(updated.values()) or 1.0
        return {k: round(v/total, 4) for k, v in updated.items()}
