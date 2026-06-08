import numpy as np
import pandas as pd

from modules import v38_institutional_free_core as v38


def sample_df(n=420):
    idx = pd.date_range('2024-01-01', periods=n)
    base = pd.Series(np.linspace(100, 170, n) + np.sin(np.arange(n) / 8), index=idx)
    return pd.DataFrame({'Open': base, 'High': base*1.012, 'Low': base*0.988, 'Close': base, 'Volume': 1000000 + np.arange(n)*100}, index=idx)


def patch_data(monkeypatch):
    df = sample_df()
    monkeypatch.setattr(v38, 'fetch_ohlcv', lambda symbol, period='1y', interval='1d': df)
    return df


def test_explainable_confidence_governance():
    sig = {'symbol':'NVDA','signal':'BUY','score':82,'price':100}
    gov = v38.governance_layer({'trades_today':1,'risk_per_trade_pct':1,'daily_pnl_pct':0})
    xai = v38.explainable_ai_engine(sig, {'governance': gov, 'event_filter': {'decision':'ALLOW'}, 'liquidity': {'decision':'ALLOW'}})
    conf = v38.confidence_score(sig, {'governance': gov})
    assert xai['ok'] is True
    assert conf['confidence_pct'] >= 50
    assert gov['decision'] == 'ALLOW'


def test_data_liquidity_benchmark(monkeypatch):
    patch_data(monkeypatch)
    data = v38.multi_source_data_validation('NVDA')
    liq = v38.liquidity_filter('NVDA', intended_notional=10000)
    bench = v38.benchmark_comparison(['NVDA','AAPL'], ['SPY','QQQ'])
    assert data['ok'] is True
    assert liq['ok'] is True
    assert bench['ok'] is True


def test_exposure_beta_stress(monkeypatch):
    patch_data(monkeypatch)
    positions = [{'symbol':'NVDA','qty':10,'price':100},{'symbol':'SPY','qty':5,'price':500}]
    exp = v38.exposure_manager(positions, 100000)
    beta = v38.beta_control(positions, account_equity=100000)
    stress = v38.scenario_stress_test(positions, 100000)
    assert exp['ok'] is True
    assert beta['ok'] is True
    assert stress['worst_case']['pnl_pct'] <= 0


def test_ai_health_and_pretrade(monkeypatch, tmp_path):
    patch_data(monkeypatch)
    # avoid persistent kill switch interference from other tests
    import modules.v37_live_safety_broker_ready_core as v37
    monkeypatch.setattr(v37, 'KILL_FILE', tmp_path/'kill.json')
    monkeypatch.setattr(v38, 'kill_switch_status', lambda *a, **k: {'ok': True, 'active': False, 'decision': 'ALLOW'})
    health = v38.ai_health_score({'sharpe':1.6,'profit_factor':1.7,'win_rate_pct':55,'max_drawdown_pct':-8})
    pre = v38.v38_pre_trade_pipeline('NVDA', positions=[], context={'trades_today':0,'risk_per_trade_pct':1,'daily_pnl_pct':0}, dry_run=True)
    assert health['status'] == 'HEALTHY'
    assert pre['ok'] is True


def test_v38_report(monkeypatch, tmp_path):
    patch_data(monkeypatch)
    import modules.v37_live_safety_broker_ready_core as v37
    monkeypatch.setattr(v37, 'KILL_FILE', tmp_path/'kill.json')
    rep = v38.v38_institutional_report(['NVDA','AAPL','SPY'])
    assert rep['ok'] is True
    assert rep['version'] == v38.V38_VERSION
    assert 'exposure_manager' in rep
