class BrokerReconciliation:
    def compare(self, internal_positions, broker_positions):
        diffs = {}
        keys = set(internal_positions) | set(broker_positions)
        for k in keys:
            a = float(internal_positions.get(k, 0))
            b = float(broker_positions.get(k, 0))
            if abs(a-b) > 1e-9:
                diffs[k] = {"internal": a, "broker": b, "difference": a-b}
        return {"ok": len(diffs)==0, "diffs": diffs}
