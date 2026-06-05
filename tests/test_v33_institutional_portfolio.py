import unittest

from modules import v33_institutional_portfolio_core as v33


class V33InstitutionalPortfolioTests(unittest.TestCase):
    def test_relative_strength_ranks_leader_above_laggard(self):
        benchmark = [100 + i for i in range(140)]
        leader = [100 + i * 1.8 for i in range(140)]
        laggard = [100 + i * 0.4 for i in range(140)]
        result = v33.relative_strength_ranking({"LEAD": leader, "LAG": laggard}, benchmark, lookbacks=(20, 60, 120))
        self.assertTrue(result["ok"])
        self.assertEqual(result["rankings"][0]["symbol"], "LEAD")
        self.assertGreater(result["rankings"][0]["rs_score"], result["rankings"][1]["rs_score"])

    def test_drawdown_control_blocks_on_daily_loss(self):
        result = v33.drawdown_control([100000, 101000, 99000], daily_loss_pct=-0.03)
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "BLOCK_NEW_TRADES")
        self.assertEqual(result["risk_multiplier"], 0.0)

    def test_portfolio_allocation_respects_cash_and_caps(self):
        candidates = [
            {"symbol": "QQQ", "score": 82, "probability": 68, "rs_score": 78, "annual_volatility_pct": 18, "max_drawdown_pct": -8},
            {"symbol": "NVDA", "score": 70, "probability": 62, "rs_score": 72, "annual_volatility_pct": 35, "max_drawdown_pct": -18},
            {"symbol": "WEAK", "score": 45, "probability": 49, "rs_score": 30},
        ]
        result = v33.portfolio_allocation(candidates, total_equity=100000, max_weight=0.4, cash_floor=0.15)
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["cash_weight"], 0.15)
        self.assertTrue(all(x["weight"] <= 0.4 for x in result["allocations"]))
        self.assertNotIn("WEAK", [x["symbol"] for x in result["allocations"]])

    def test_walk_forward_validation_returns_verdict(self):
        prices = [100 + i * 0.8 + (i % 3) for i in range(80)]
        signals = ["BUY"] + [0] * 78 + ["SELL"]
        result = v33.walk_forward_validation({"QQQ": prices}, {"QQQ": signals}, folds=4)
        self.assertTrue(result["ok"])
        self.assertIn(result["deploy_verdict"], {"PASS", "WARN"})
        self.assertEqual(result["symbols_tested"], 1)

    def test_decision_pack_runs_complete(self):
        benchmark = [100 + i for i in range(140)]
        qqq = [100 + i * 1.5 for i in range(140)]
        payload = {
            "assets": {"QQQ": qqq},
            "benchmark": benchmark,
            "candidates": [{"symbol": "QQQ", "score": 82, "probability": 68, "max_drawdown_pct": -8}],
            "equity_curve": [100000, 102000, 101000, 103000],
            "total_equity": 100000,
        }
        result = v33.institutional_decision_pack(payload)
        self.assertTrue(result["ok"])
        self.assertTrue(result["relative_strength"]["ok"])
        self.assertTrue(result["portfolio_allocation"]["ok"])


if __name__ == '__main__':
    unittest.main()
