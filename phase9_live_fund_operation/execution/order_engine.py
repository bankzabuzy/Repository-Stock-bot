import json, time
from pathlib import Path
from dataclasses import asdict
from ..broker.paper_broker import PaperBroker
from ..broker.webull_adapter import WebullAdapter
from ..risk.risk_gate import RiskGate
from ..storage.db import FundDB
from ..storage.models import OrderIntent

class OrderEngine:
    def __init__(self, config_path=None, mode=None, db_path="phase9_fund_ops.db"):
        if config_path is None:
            config_path = Path(__file__).resolve().parents[1] / "config" / "phase9_config.json"
        self.config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        self.mode = mode or self.config.get("mode_default", "paper")
        self.db = FundDB(db_path)
        self.risk = RiskGate(self.config)
        self.broker = PaperBroker() if self.mode == "paper" else WebullAdapter()

    def submit(self, intent: OrderIntent):
        if not self.broker.connect():
            raise RuntimeError(f"Broker connection failed in mode={self.mode}")
        account = self.broker.account()
        ok, reasons, intent_hash = self.risk.validate(intent, account, {})
        self.db.log("risk_check", {"ok": ok, "reasons": reasons, "intent": asdict(intent)})
        if not ok:
            return {"accepted": False, "reasons": reasons, "intent_hash": intent_hash}
        report = self.broker.place_order(intent)
        self.db.log("order_report", asdict(report))
        return {"accepted": True, "report": asdict(report), "intent_hash": intent_hash}

    def close(self):
        self.db.close()
