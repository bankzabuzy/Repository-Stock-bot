import os
import tempfile
import unittest

fd, path = tempfile.mkstemp(prefix="v30_test_", suffix=".db")
os.close(fd)
os.environ["DB_PATH"] = path
os.environ["V29_REQUIRE_API_KEY"] = "false"

from modules import v30_model_validation_core as v30


class V30ModelValidationTests(unittest.TestCase):
    def test_v30_init_and_deployment_check(self):
        payload = v30.init_v30_db()
        self.assertTrue(payload["ok"])
        check = v30.deployment_check()
        self.assertIn(check["status"], {"PASS", "WARN", "FAIL"})
        self.assertIsInstance(check["score"], int)

    def test_v30_paper_signal_and_mark_to_market(self):
        v30.init_v30_db()
        buy = v30.paper_apply_signal("SPY", "BUY", price=100, account_name="TEST")
        self.assertTrue(buy["ok"])
        self.assertIn(buy["action"], {"BUY", "HOLD"})
        mtm = v30.mark_to_market("TEST", {"SPY": 101})
        self.assertTrue(mtm["ok"])
        sell = v30.paper_apply_signal("SPY", "SELL", price=102, account_name="TEST")
        self.assertTrue(sell["ok"])

    def test_v30_reconciliation_and_gate(self):
        v30.init_v30_db()
        rec = v30.data_reconciliation("SPY", {"a": 100.0, "b": 100.5})
        self.assertIn(rec["status"], {"PASS", "BLOCK", "FAIL"})
        ok, detail = v30.validation_gate("SPY", "BUY", {})
        self.assertIsInstance(ok, bool)
        self.assertIn("decision", detail)


if __name__ == "__main__":
    unittest.main()
