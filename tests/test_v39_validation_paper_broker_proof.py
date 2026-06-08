import numpy as np
import pandas as pd

from modules import v39_validation_paper_broker_proof_core as v39
from modules import v38_institutional_free_core as v38


def sample_df(n=420):
    idx = pd.date_range('2024-01-01', periods=n)
    base = pd.Series(np.linspace(100, 160, n) + np.sin(np.arange(n) / 9), index=idx)
    return pd.DataFrame({'Open': base, 'High': base*1.01, 'Low': base*0.99, 'Close': base, 'Volume': 2_000_000 + np.arange(n)*1000}, index=idx)


def patch_data(monkeypatch):
    df = sample_df()
    monkeypatch.setattr(v38, 'fetch_ohlcv', lambda symbol, period='1y', interval='1d': df)
    monkeypatch.setattr(v39, 'fetch_ohlcv', lambda symbol, period='1y', interval='1d': df)
    return df


def test_config_and_broker_check(tmp_path, monkeypatch):
    monkeypatch.setattr(v39, 'CONFIG_FILE', tmp_path/'config.json')
    cfg = v39.load_config()
    assert cfg['ok'] is True
    saved = v39.save_config({'min_confidence_pct': 60})
    assert saved['config']['min_confidence_pct'] == 60
    chk = v39.paper_broker_connection_check('mock')
    assert chk['ok'] is True


def test_paper_order_proof_dry_run(monkeypatch, tmp_path):
    patch_data(monkeypatch)
    monkeypatch.setattr(v39, 'PROOF_FILE', tmp_path/'proof.jsonl')
    monkeypatch.setattr(v39, 'CONFIG_FILE', tmp_path/'config.json')
    monkeypatch.setattr(v39, 'kill_switch_status', lambda *a, **k: {'ok': True, 'active': False, 'decision': 'ALLOW', 'reasons':['pass']})
    res = v39.paper_order_proof('NVDA', qty=1, price=100, dry_run=True)
    assert res['ok'] is True
    assert res['order_result']['status'] == 'dry_run_not_submitted'


def test_forward_dashboard_and_freeze(tmp_path, monkeypatch):
    monkeypatch.setattr(v39, 'DAILY_FILE', tmp_path/'daily.jsonl')
    monkeypatch.setattr(v39, 'CONFIG_FILE', tmp_path/'config.json')
    monkeypatch.setattr(v39, 'kill_switch_status', lambda *a, **k: {'ok': True, 'active': False, 'decision': 'ALLOW', 'reasons':['pass']})
    for _ in range(35):
        v39.record_forward_day(0.2, 1)
    dash = v39.forward_validation_dashboard()
    freeze = v39.trade_freeze_mode()
    assert dash['total_recorded_days'] == 35
    assert dash['rows'][0]['sample_days'] == 30
    assert freeze['ok'] is True


def test_edge_and_full_report(monkeypatch, tmp_path):
    patch_data(monkeypatch)
    monkeypatch.setattr(v39, 'DAILY_FILE', tmp_path/'daily.jsonl')
    monkeypatch.setattr(v39, 'CONFIG_FILE', tmp_path/'config.json')
    monkeypatch.setattr(v39, 'kill_switch_status', lambda *a, **k: {'ok': True, 'active': False, 'decision': 'ALLOW', 'reasons':['pass']})
    for _ in range(90):
        v39.record_forward_day(0.12, 1)
    edge = v39.edge_proof_report(['NVDA','AAPL'], ['SPY'])
    rep = v39.v39_full_validation_report(['NVDA','AAPL'])
    assert edge['ok'] is True
    assert 'benchmark_comparison' in edge
    assert rep['version'] == v39.V39_VERSION
