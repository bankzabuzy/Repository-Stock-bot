import numpy as np
import pandas as pd

from modules import v40_adaptive_multi_agent_core as v40
from modules import v39_validation_paper_broker_proof_core as v39
from modules import v38_institutional_free_core as v38


def sample_df(n=420):
    idx = pd.date_range('2024-01-01', periods=n)
    base = pd.Series(np.linspace(100, 170, n) + np.sin(np.arange(n) / 8), index=idx)
    return pd.DataFrame({'Open': base, 'High': base*1.012, 'Low': base*0.988, 'Close': base, 'Volume': 3000000 + np.arange(n)*1000}, index=idx)


def patch_data(monkeypatch, tmp_path):
    df = sample_df()
    monkeypatch.setattr(v40, 'fetch_ohlcv', lambda symbol, period='1y', interval='1d': df)
    monkeypatch.setattr(v38, 'fetch_ohlcv', lambda symbol, period='1y', interval='1d': df)
    monkeypatch.setattr(v39, 'DAILY_FILE', tmp_path/'daily.jsonl')
    monkeypatch.setattr(v39, 'CONFIG_FILE', tmp_path/'config.json')
    monkeypatch.setattr(v40, 'TRADE_MEMORY_FILE', tmp_path/'memory.jsonl')
    monkeypatch.setattr(v40, 'trade_freeze_mode', lambda ctx=None: {'ok': True, 'freeze_active': False, 'decision':'ALLOW', 'reasons':['pass']})
    return df


def test_adaptive_agents_and_cro(monkeypatch, tmp_path):
    patch_data(monkeypatch, tmp_path)
    ens = v40.adaptive_agent_ensemble('NVDA', {'market_regime':'risk_on', 'fear_greed':60})
    cro = v40.chief_risk_officer_ai('NVDA', ens, {'trades_today':0, 'risk_per_trade_pct':1, 'daily_pnl_pct':0})
    assert ens['ok'] is True
    assert len(ens['agents']) == 5
    assert cro['action'] in {'APPROVE','VETO'}


def test_pyramid_news_memory(monkeypatch, tmp_path):
    patch_data(monkeypatch, tmp_path)
    tp = v40.pyramid_tp_engine(100, 'BUY', atr=2)
    news = v40.news_context_layer('NVDA', {'events':['FOMC tonight']})
    rec = v40.record_trade_memory('NVDA', 'trend_breakout', 1.2, 45)
    mem = v40.trade_memory_engine('NVDA')
    assert tp['tp_plan'][0]['close_pct'] == 25
    assert news['decision'] == 'REDUCE_SIZE'
    assert rec['ok'] is True
    assert mem['sample_trades'] == 1


def test_v40_pretrade_and_report(monkeypatch, tmp_path):
    patch_data(monkeypatch, tmp_path)
    pre = v40.v40_pre_trade_pipeline('NVDA', {'market_regime':'risk_on', 'fear_greed':65, 'trades_today':0, 'risk_per_trade_pct':1, 'daily_pnl_pct':0})
    rep = v40.v40_full_report(['NVDA','AAPL'], {'market_regime':'risk_on'})
    assert pre['ok'] is True
    assert pre['version'] == v40.V40_VERSION
    assert 'pyramid_tp' in pre
    assert rep['summary']['symbols'] == 2
