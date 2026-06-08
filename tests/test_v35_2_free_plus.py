import numpy as np
import pandas as pd

from modules import v35_institutional_free_core as c


def sample_df(n=320):
    idx = pd.date_range('2024-01-01', periods=n)
    base = pd.Series(np.linspace(100, 155, n) + np.sin(np.arange(n) / 5), index=idx)
    return pd.DataFrame({
        'Open': base,
        'High': base * 1.01,
        'Low': base * 0.99,
        'Close': base,
        'Volume': 1000000,
    }, index=idx)


def test_data_quality_gate_passes_clean_data():
    res = c.data_quality_gate('TEST', sample_df())
    assert res['ok'] is True
    assert res['score'] >= 90


def test_institutional_decision_blocks_risk_off():
    sig = c.latest_signal('TEST', sample_df())
    dq = c.data_quality_gate('TEST', sample_df())
    dec = c.institutional_decision(sig, dq, {'regime': 'RISK_OFF', 'risk_on': False})
    assert dec['decision'] == 'BLOCK'
    assert 'market_regime_risk_off' in dec['reasons']


def test_portfolio_correlation_report_uses_free_data(monkeypatch):
    df = sample_df()
    monkeypatch.setattr(c, 'fetch_ohlcv', lambda symbol, period='1y', interval='1d': df)
    res = c.portfolio_correlation_report(['AAA','BBB'])
    assert res['ok'] is True
    assert res['high_corr_pairs']


def test_rank_signals_contains_new_gates(monkeypatch):
    df = sample_df()
    monkeypatch.setattr(c, 'fetch_ohlcv', lambda symbol, period='1y', interval='1d': df)
    res = c.rank_signals(['AAA','BBB'])
    assert res['ok'] is True
    assert 'market_regime' in res
    assert 'correlation' in res
    assert 'institutional_gate' in res['rows'][0]
