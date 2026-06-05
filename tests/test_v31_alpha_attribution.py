import os
import tempfile
import unittest

os.environ['DB_PATH'] = tempfile.NamedTemporaryFile(delete=False).name
os.environ['V29_REQUIRE_API_KEY'] = 'false'

from modules import v31_alpha_attribution_core as v31


class V31AlphaAttributionTests(unittest.TestCase):
    def setUp(self):
        # Use a fresh SQLite file for every test to avoid cross-test leakage.
        db_file = tempfile.NamedTemporaryFile(delete=False).name
        os.environ['DB_PATH'] = db_file
        v31.v29.DB_PATH = db_file
        v31.v29.store = v31.v29.Store()
        v31.store = v31.v29.store
        v31.init_v31_db()

    def seed_components(self):
        samples = [
            ('NVDA', 'BUY', {'confidence': 0.90, 'ema_trend': 0.80, 'volume': 0.70, 'risk_reward': 0.75}, 1.2, 'BULL'),
            ('AAPL', 'BUY', {'confidence': 0.85, 'ema_trend': 0.70, 'volume': 0.40, 'risk_reward': 0.60}, 0.6, 'BULL'),
            ('TSLA', 'BUY', {'confidence': 0.50, 'ema_trend': 0.30, 'volume': 0.20, 'risk_reward': 0.30}, -0.8, 'HIGH_VOL'),
            ('MSFT', 'BUY', {'confidence': 0.88, 'ema_trend': 0.75, 'volume': 0.65, 'risk_reward': 0.72}, 0.9, 'BULL'),
            ('AMD', 'BUY', {'confidence': 0.45, 'ema_trend': 0.25, 'volume': 0.25, 'risk_reward': 0.30}, -0.5, 'HIGH_VOL'),
            ('QQQ', 'BUY', {'confidence': 0.82, 'ema_trend': 0.77, 'volume': 0.55, 'risk_reward': 0.68}, 0.7, 'BULL'),
        ]
        for idx, (sym, side, comps, ret, regime) in enumerate(samples):
            v31.record_signal_components(sym, side, comps, return_r=ret, outcome='CLOSED', regime=regime, strategy_key='TEST', source_signal_id=f't{idx}')

    def test_v31_attribution_and_weights(self):
        self.seed_components()
        attr = v31.component_attribution(lookback=100, min_observations=3)
        self.assertTrue(attr['ok'])
        self.assertGreaterEqual(len(attr['components']), 4)
        weights = v31.recommend_weights(lookback=100, min_observations=3)
        self.assertTrue(weights['ok'])
        self.assertGreaterEqual(len(weights['recommendations']), 1)
        self.assertGreater(sum(w['recommended_weight'] for w in weights['recommendations']), 0.99)

    def test_v31_monte_carlo_and_regime(self):
        self.seed_components()
        mc = v31.monte_carlo_risk(returns=[1.0, 0.8, -0.4, 1.2, -0.6, 0.5], simulations=200, trades_per_run=20)
        self.assertTrue(mc['ok'])
        self.assertIn('risk_of_ruin_pct', mc)
        regimes = v31.regime_attribution(lookback=100)
        self.assertTrue(regimes['ok'])
        self.assertGreaterEqual(regimes['total_regimes'], 1)

    def test_v31_optimizer_and_gate(self):
        self.seed_components()
        v31.recommend_weights(lookback=100, min_observations=3)
        result = v31.optimize_portfolio_candidates([
            {'symbol': 'NVDA', 'group': 'SEMIS', 'confidence': 92, 'reward_risk': 3, 'components': {'confidence': .92, 'ema_trend': .8, 'volume': .7, 'risk_reward': .75}},
            {'symbol': 'AMD', 'group': 'SEMIS', 'confidence': 75, 'reward_risk': 2, 'components': {'confidence': .75, 'ema_trend': .65, 'volume': .5, 'risk_reward': .55}},
            {'symbol': 'AAPL', 'group': 'MEGA_TECH', 'confidence': 80, 'reward_risk': 2.5, 'components': {'confidence': .8, 'ema_trend': .7, 'volume': .4, 'risk_reward': .6}},
        ], max_selected=2, max_same_group=1)
        self.assertTrue(result['ok'])
        self.assertEqual(len(result['selected']), 2)
        ok, detail = v31.alpha_gate({'symbol': 'NVDA', 'confidence': 90, 'reward_risk': 3, 'components': {'confidence': .9, 'ema_trend': .8}})
        self.assertIsInstance(ok, bool)
        self.assertIn('alpha_score', detail)


if __name__ == '__main__':
    unittest.main()
