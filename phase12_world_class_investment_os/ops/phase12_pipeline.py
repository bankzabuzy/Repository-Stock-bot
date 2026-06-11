import json
from pathlib import Path
from phase12_world_class_investment_os.data.market_data_router import MarketDataRouter
from phase12_world_class_investment_os.macro.macro_overlay import MacroOverlay
from phase12_world_class_investment_os.behavioral.crowd_psychology import CrowdPsychology
from phase12_world_class_investment_os.alpha.alpha_discovery_plus import AlphaDiscoveryPlus
from phase12_world_class_investment_os.portfolio.portfolio_constructor import PortfolioConstructor
from phase12_world_class_investment_os.risk.world_class_risk_gate import WorldClassRiskGate
from phase12_world_class_investment_os.xai.explainability import ExplainabilityEngine
from phase12_world_class_investment_os.execution.user_friendly_signal import UserFriendlySignal
from phase12_world_class_investment_os.alerts.line_message_builder import LineMessageBuilder
from phase12_world_class_investment_os.dashboard.dashboard_snapshot import DashboardSnapshot
from phase12_world_class_investment_os.governance.immutable_audit import ImmutableAudit

class Phase12Pipeline:
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = Path(__file__).resolve().parents[1] / "config" / "phase12_config.json"
        self.config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        self.data = MarketDataRouter()
        self.macro = MacroOverlay()
        self.behavior = CrowdPsychology()
        self.alpha = AlphaDiscoveryPlus()
        self.portfolio = PortfolioConstructor()
        self.risk = WorldClassRiskGate(self.config)
        self.xai = ExplainabilityEngine()
        self.signal = UserFriendlySignal()
        self.line = LineMessageBuilder()
        self.dashboard = DashboardSnapshot()
        self.audit = ImmutableAudit()

    def run(self, symbols, macro_input, sentiment_input, account, mode="shadow"):
        snapshot = self.data.fetch_snapshot(symbols)
        macro_view = self.macro.analyze(macro_input)
        crowd_view = self.behavior.evaluate(sentiment_input)
        alpha_scores = self.alpha.score(snapshot, macro_view, crowd_view)
        portfolio = self.portfolio.construct(alpha_scores, snapshot)
        risk = self.risk.check(portfolio, snapshot, account, crowd_view)
        decision = {
            "mode": mode,
            "market_regime": macro_view.get("macro_regime"),
            "macro_regime": macro_view.get("macro_regime"),
            "selected_symbols": portfolio["selected_symbols"],
            "target_weights": portfolio["target_weights"],
            "alpha_scores": alpha_scores,
            "risk": risk
        }
        explanation = self.xai.explain({**decision, "risk_blocks": risk.get("blocks", [])})
        signal_report = self.signal.build(portfolio, alpha_scores, explanation, risk)
        line_message = self.line.build(signal_report)
        dash = self.dashboard.build({**decision, "explanation": explanation})
        audit_event = self.audit.log("phase12_decision", {
            "snapshot": snapshot, "macro": macro_view, "crowd": crowd_view,
            "portfolio": portfolio, "risk": risk, "signal": signal_report
        })
        return {
            "version": "V1200",
            "mode": mode,
            "snapshot": snapshot,
            "macro": macro_view,
            "crowd": crowd_view,
            "alpha_scores": alpha_scores,
            "portfolio": portfolio,
            "risk": risk,
            "explanation": explanation,
            "signal_report": signal_report,
            "line_message": line_message,
            "dashboard": dash,
            "audit_hash": audit_event["hash"],
            "audit_verified": self.audit.verify()
        }
