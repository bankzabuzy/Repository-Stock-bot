class HumanApprovalGate:
    def require(self, decision):
        decision = dict(decision)
        decision["requires_human_approval"] = True
        decision["approved"] = bool(decision.get("approved", False))
        if not decision["approved"]:
            decision["execution_status"] = "BLOCKED_PENDING_HUMAN_APPROVAL"
        return decision
