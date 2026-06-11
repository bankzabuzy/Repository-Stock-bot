class ResultLearner:
    def update_weights(self, strategy_weights, realized_results):
        updated = dict(strategy_weights)
        for k, v in list(updated.items()):
            perf = float(realized_results.get(k, 0))
            if perf < 0:
                updated[k] = max(0.0, v * 0.90)
            elif perf > 0:
                updated[k] = v * 1.05
        total = sum(updated.values()) or 1
        return {k: round(v/total, 4) for k, v in updated.items()}
