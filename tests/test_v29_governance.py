import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("V29_REQUIRE_API_KEY", "false")
fd, path = tempfile.mkstemp(prefix="v29_test_", suffix=".db")
os.close(fd)
os.environ["DB_PATH"] = path

from modules import v29_governance_core as v29


class V29GovernanceTests(unittest.TestCase):
    def setUp(self):
        v29.init_v29_db()
        v29.set_state("alert_kill_switch", "off")
        v29.set_state("drawdown_circuit_breaker", "on")
        v29.set_state("provider_gate", "warn")

    def test_kill_switch_blocks_alerts(self):
        v29.set_state("alert_kill_switch", "on")
        with patch.object(v29, "provider_health", return_value={"aggregate_score": 100, "status": "OK"}):
            ok, detail = v29.governance_gate("SPY", "BUY", {"score": 90})
        self.assertFalse(ok)
        self.assertIn("kill-switch", " ".join(detail["reasons"]))

    def test_feedback_loop_handles_no_trades(self):
        result = v29.feedback_loop("GLOBAL")
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "LEARN_ONLY")

    def test_scheduler_run_once_returns_payload(self):
        with patch.object(v29.v28, "run_outcome_scheduler", return_value={"ok": True, "checked": 0, "closed": 0}), \
             patch.object(v29, "provider_health", return_value={"ok": True, "aggregate_score": 100, "status": "OK", "providers": []}):
            result = v29.scheduler_run_once()
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "OK")

    def test_api_key_validation(self):
        old_req = v29.V29_REQUIRE_API_KEY
        old_key = v29.V29_API_KEY
        try:
            v29.V29_REQUIRE_API_KEY = True
            v29.V29_API_KEY = "secret"
            ok, _ = v29.require_api_key({"X-API-Key": "secret"})
            self.assertTrue(ok)
            ok, _ = v29.require_api_key({"X-API-Key": "wrong"})
            self.assertFalse(ok)
        finally:
            v29.V29_REQUIRE_API_KEY = old_req
            v29.V29_API_KEY = old_key


if __name__ == "__main__":
    unittest.main()
