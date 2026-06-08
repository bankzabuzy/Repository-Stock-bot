import numpy as np
import pandas as pd

from modules import v37_live_safety_broker_ready_core as v37


def sample_df(n=420):
    idx = pd.date_range('2024-01-01', periods=n)
    base = pd.Series(np.linspace(100, 170, n) + np.sin(np.arange(n) / 8), index=idx)
    return pd.DataFrame({'Open': base, 'High': base*1.012, 'Low': base*0.988, 'Close': base, 'Volume': 1000000 + np.arange(n)*100}, index=idx)


def test_broker_mock_and_oms_dry_run():
    acct = v37.get_broker('mock').account()
    res = v37.oms_submit_order({'symbol':'AAA','side':'BUY','qty':10,'price':100}, dry_run=True)
    assert acct['ok'] is True
    assert res['ok'] is True
    assert res['status'] == 'dry_run_simulated'


def test_kill_switch_and_capital_protection(tmp_path, monkeypatch):
    monkeypatch.setattr(v37, 'KILL_FILE', tmp_path/'kill.json')
    assert v37.kill_switch_status(today_pnl_pct=-6)['active'] is True
    assert v37.set_kill_switch(True, 'unit_test')['active'] is True
    assert v37.kill_switch_status()['active'] is True
    cp = v37.capital_protection_mode({'max_drawdown_pct':-16,'profit_factor':1.0,'consecutive_losses':5})
    assert cp['mode'] == 'PAUSE'


def test_event_slippage_drift(monkeypatch):
    monkeypatch.setenv('V37_EVENT_DATES','2026-06-06:FOMC')
    ev = v37.news_event_risk_filter('SPY','2026-06-06')
    sl = v37.live_slippage_monitor(100, 100.2, 'BUY')
    dr = v37.model_drift_detector({'sharpe':0.5,'profit_factor':0.8,'win_rate_pct':40,'max_drawdown_pct':-20})
    assert ev['decision'] == 'BLOCK_NEW_TRADES'
    assert sl['status'] == 'OK'
    assert dr['status'] == 'DRIFT_RISK'


def test_health_recovery_and_readiness(monkeypatch, tmp_path):
    monkeypatch.setattr(v37, 'fetch_ohlcv', lambda symbol, period='1y', interval='1d': sample_df())
    monkeypatch.setattr(v37, 'KILL_FILE', tmp_path/'kill.json')
    h = v37.health_check_dashboard(['AAA','BBB'])
    r = v37.recovery_manager(['AAA','BBB'])
    ready = v37.live_readiness_score(['AAA','BBB'])
    assert h['ok'] is True
    assert r['ok'] is True
    assert 'live_safety_score_pct' in ready


def test_pre_trade_pipeline_blocks_or_simulates(monkeypatch, tmp_path):
    df = sample_df()
    monkeypatch.setattr(v37, 'fetch_ohlcv', lambda symbol, period='1y', interval='1d': df)
    monkeypatch.setattr(v37, 'KILL_FILE', tmp_path/'kill.json')
    res = v37.v37_pre_trade_pipeline('AAA', dry_run=True)
    assert res['ok'] is True
    assert res['decision'] in {'BLOCK','ORDER_SIMULATED_OR_SENT','ALLOW_BUT_ZERO_QTY'}


def test_v37_report(monkeypatch, tmp_path):
    df = sample_df()
    monkeypatch.setattr(v37, 'fetch_ohlcv', lambda symbol, period='1y', interval='1d': df)
    monkeypatch.setattr(v37, 'KILL_FILE', tmp_path/'kill.json')
    rep = v37.v37_live_safety_report(['AAA','BBB'])
    assert rep['ok'] is True
    assert rep['version'] == v37.V37_VERSION
    assert 'live_readiness' in rep
