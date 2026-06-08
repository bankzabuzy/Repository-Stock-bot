import numpy as np
import pandas as pd

from modules import v35_institutional_free_core as c


def sample_df(n=360):
    idx = pd.date_range('2024-01-01', periods=n)
    base = pd.Series(np.linspace(100, 165, n) + np.sin(np.arange(n) / 6), index=idx)
    return pd.DataFrame({
        'Open': base,
        'High': base * 1.012,
        'Low': base * 0.988,
        'Close': base,
        'Volume': 1000000 + np.arange(n) * 100,
    }, index=idx)


def test_ensemble_signal_votes(monkeypatch):
    df = sample_df()
    res = c.ensemble_signal('AAA', df)
    assert res['signal'] in {'BUY', 'HOLD', 'SELL'}
    assert 'trend' in res['votes']
    assert res['ensemble_score'] >= 0


def test_position_sizing_engine_uses_risk_and_kelly():
    sig = c.latest_signal('AAA', sample_df())
    perf = {'win_rate_pct': 55, 'profit_factor': 1.6}
    res = c.position_sizing_engine(sig, perf, account_equity=100000)
    assert res['ok'] is True
    assert res['suggested_notional'] > 0
    assert res['position_pct'] <= 20.0


def test_portfolio_optimizer_returns_weights(monkeypatch):
    df = sample_df()
    monkeypatch.setattr(c, 'fetch_ohlcv', lambda symbol, period='1y', interval='1d': df)
    res = c.portfolio_optimizer(['AAA', 'BBB', 'CCC'])
    assert res['ok'] is True
    assert len(res['rows']) == 3
    assert abs(sum(r['weight_pct'] for r in res['rows']) - 100) < 0.2


def test_monte_carlo_stress_test(monkeypatch):
    df = sample_df()
    monkeypatch.setattr(c, 'fetch_ohlcv', lambda symbol, period='2y', interval='1d': df)
    res = c.monte_carlo_stress_test('AAA', simulations=200, horizon_days=30)
    assert res['ok'] is True
    assert res['simulations'] == 200
    assert 'probability_loss_pct' in res


def test_trade_journal_ai_summary():
    trades = [
        {'symbol': 'AAA', 'entry': 100, 'exit': 110, 'qty': 2},
        {'symbol': 'BBB', 'entry': 50, 'exit': 45, 'qty': 1},
    ]
    res = c.trade_journal_ai(trades)
    assert res['ok'] is True
    assert res['trades'] == 2
    assert res['total_pnl'] == 15


def test_alpha_stack_report_contains_all_blocks(monkeypatch):
    df = sample_df()
    monkeypatch.setattr(c, 'fetch_ohlcv', lambda symbol, period='1y', interval='1d': df)
    res = c.alpha_stack_report(['AAA', 'BBB'])
    assert res['ok'] is True
    assert 'portfolio_optimizer' in res
    assert 'position_sizing' in res['ranking']['rows'][0]
