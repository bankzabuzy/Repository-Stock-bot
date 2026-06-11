import json
from pathlib import Path
from ..market.market_state import MarketAnalyzer
from ..behavior.behavior_guard import BehaviorGuard
from ..strategy.strategy_selector import StrategySelector
from ..risk.autonomous_risk_controller import AutonomousRiskController
from ..shadow.shadow_trader import ShadowTrader
from ..approval.human_approval import HumanApprovalGate
from ..learning.result_learner import ResultLearner
from ..governance.audit import AuditTrail
from ..governance.kill_switch import KillSwitch

class AutonomousFundOS:
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = Path(__file__).resolve().parents[1] / "config" / "phase10_config.json"
        self.config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        self.market = MarketAnalyzer()
        self.behavior = BehaviorGuard()
        self.selector = StrategySelector()
        self.risk = AutonomousRiskController(self.config)
        self.shadow = ShadowTrader()
        self.approval = HumanApprovalGate()
        self.learner = ResultLearner()
        self.audit = AuditTrail()
        self.kill_switch = KillSwitch(enabled=self.config.get("governance", {}).get("kill_switch_default", True))

    def decide(self, features, alpha_scores, account, user_context=None, target_mode="shadow"):
        user_context = user_context or {}
        market_state = self.market.analyze(features)
        behavior = self.behavior.evaluate(user_context)
        selection = self.selector.select(market_state, alpha_scores)
        decision = {
            "phase": "V1000_PHASE10",
            "market_regime": market_state.regime,
            "risk_score": market_state.risk_score,
            "selected_strategies": selection["selected"],
            "strategy_weights": selection["weights"],
            "confidence": self._confidence(market_state, behavior),
            "target_mode": target_mode,
            "liquidity_score": market_state.liquidity_score,
            "notes": "No profit guarantee. Human approval required for live execution."
        }
        risk = self.risk.check(decision, account)
        decision["risk_allowed"] = risk["allowed"]
        decision["risk_blocks"] = risk["blocks"]
        decision["behavior_guard"] = behavior
        if target_mode == "live":
            decision = self.approval.require(decision)
        shadow_record = self.shadow.record(decision)
        self.audit.log("decision", shadow_record)
        return shadow_record

    def _confidence(self, market_state, behavior):
        if not behavior["ok"]:
            return "B"
        if market_state.risk_score >= 75 and market_state.liquidity_score >= 70:
            return "A"
        if market_state.risk_score >= 55:
            return "B"
        return "C"
