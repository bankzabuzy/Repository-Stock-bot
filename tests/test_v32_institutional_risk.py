import unittest

from modules import v32_institutional_risk_core as v32


class V32InstitutionalRiskTests(unittest.TestCase):
    def test_position_sizing_caps_risk(self):
        result = v32.position_sizing(equity=100000, entry=100, stop=95, risk_per_trade=0.01, max_position_pct=0.10)
        self.assertTrue(result['ok'])
        self.assertLessEqual(result['risk_pct_equity'], 0.01)
        self.assertLessEqual(result['position_pct_equity'], 0.10)

    def test_pretrade_gate_blocks_missing_stop(self):
        ok, detail = v32.pretrade_risk_gate({'symbol': 'SPY', 'side': 'BUY', 'entry': 100, 'confidence': 90, 'reward_risk': 2})
        self.assertFalse(ok)
        self.assertIn('missing_stop_loss', detail['reasons'])

    def test_backtest_and_walk_forward(self):
        prices = [100, 101, 102, 104, 103, 105, 107, 106, 108, 110, 109, 111, 113, 112, 114, 116, 115, 117, 119, 118, 120, 122, 121, 123]
        signals = ['BUY'] + [0] * (len(prices) - 2) + ['SELL']
        result = v32.backtest_signals(prices, signals, initial_equity=100000)
        self.assertTrue(result['ok'])
        self.assertIn('max_drawdown_pct', result)
        wf = v32.walk_forward_report(prices, signals, folds=3)
        self.assertTrue(wf['ok'])
        self.assertIn(wf['stability_status'], {'PASS', 'WARN'})


if __name__ == '__main__':
    unittest.main()
