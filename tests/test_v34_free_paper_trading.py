import os
import tempfile
import unittest

from modules import v34_free_paper_trading_core as v34


class V34FreePaperTradingTests(unittest.TestCase):
    def test_mock_broker_buy_and_sell_realizes_pnl(self):
        broker = v34.MockBroker(initial_cash=10000, fee_bps=0, slippage_bps=0)
        buy = broker.place_order("QQQ", "BUY", notional=5000, price=100)
        self.assertTrue(buy["ok"])
        self.assertAlmostEqual(broker.snapshot()["positions"]["QQQ"], 50)
        sell = broker.place_order("QQQ", "SELL", quantity=50, price=110)
        self.assertTrue(sell["ok"])
        self.assertAlmostEqual(broker.snapshot()["realized_pnl"], 500)

    def test_kill_switch_blocks_on_drawdown(self):
        result = v34.evaluate_kill_switch([100000, 102000, 85000], daily_loss_pct=-0.10, max_drawdown_limit_pct=-12)
        self.assertTrue(result["ok"])
        self.assertTrue(result["kill_active"])
        self.assertEqual(result["risk_multiplier"], 0.0)

    def test_paper_trade_from_signals_runs_and_monitors(self):
        prices = {
            "QQQ": [100, 102, 104, 106, 108, 110],
            "SPY": [100, 99, 101, 102, 103, 104],
        }
        signals = {
            "QQQ": ["BUY", "HOLD", "HOLD", "SELL", "HOLD", "HOLD"],
            "SPY": ["HOLD", "BUY", "HOLD", "HOLD", "SELL", "HOLD"],
        }
        result = v34.paper_trade_from_signals(prices, signals, initial_cash=100000, allocation_weights={"QQQ": 0.3, "SPY": 0.2}, fee_bps=0, slippage_bps=0)
        self.assertTrue(result["ok"])
        self.assertGreater(len(result["trades"]), 0)
        self.assertTrue(result["monitoring"]["ok"])
        self.assertIn("trade_stats", result["monitoring"])

    def test_monitoring_report_flags_exposure(self):
        snapshot = {"cash": 0, "equity": 10000, "positions": {"QQQ": 100}, "last_prices": {"QQQ": 100}, "blocked": False}
        report = v34.monitoring_report(snapshot, [10000, 9900, 10100], [])
        self.assertTrue(report["ok"])
        self.assertIn("EXPOSURE_TOO_HIGH", report["alerts"])

    def test_save_outputs(self):
        trades = [{"timestamp": "t", "symbol": "QQQ", "side": "BUY", "quantity": 1, "price": 100}]
        with tempfile.TemporaryDirectory() as d:
            csv_result = v34.save_trades_csv(trades, os.path.join(d, "trades.csv"))
            json_result = v34.save_monitoring_json({"ok": True}, os.path.join(d, "monitor.json"))
            self.assertTrue(csv_result["ok"])
            self.assertTrue(json_result["ok"])
            self.assertTrue(os.path.exists(csv_result["path"]))
            self.assertTrue(os.path.exists(json_result["path"]))

    def test_decision_pack(self):
        payload = {
            "prices": {"QQQ": [100, 101, 103, 105]},
            "signals": {"QQQ": ["BUY", "HOLD", "SELL", "HOLD"]},
            "initial_cash": 10000,
            "weights": {"QQQ": 0.5},
        }
        result = v34.v34_decision_pack(payload)
        self.assertTrue(result["ok"])
        self.assertTrue(result["paper_trading"]["ok"])


if __name__ == '__main__':
    unittest.main()
