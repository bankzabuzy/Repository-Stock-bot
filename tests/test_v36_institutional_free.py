import numpy as np
import pandas as pd

from modules import v36_institutional_free_core as v36


def sample_df(n=360):
    idx = pd.date_range('2024-01-01', periods=n)
    base = pd.Series(np.linspace(100, 165, n) + np.sin(np.arange(n) / 6), index=idx)
    return pd.DataFrame({'Open': base, 'High': base*1.012, 'Low': base*0.988, 'Close': base, 'Volume': 1000000 + np.arange(n)*100}, index=idx)


def test_execution_simulator_partial_and_cost():
    res = v36.execution_simulator({'symbol':'AAA','side':'BUY','qty':100,'price':100}, sample_df())
    assert res['ok'] is True
    assert res['estimated_fill_price'] > 100
    assert res['filled_qty'] > 0


def test_heat_and_factor_exposure():
    positions=[{'symbol':'NVDA','qty':10,'price':100,'stop_loss':95},{'symbol':'AMD','qty':10,'price':50,'stop_loss':45}]
    heat=v36.portfolio_heat(positions, 10000)
    fx=v36.factor_exposure(positions, 10000)
    assert heat['ok'] is True
    assert fx['rows'][0]['factor'] == 'TECH_GROWTH'


def test_dynamic_stop_engine(monkeypatch):
    monkeypatch.setattr(v36, 'fetch_ohlcv', lambda symbol, period='1y', interval='1d': sample_df())
    res=v36.dynamic_stop_engine('AAA')
    assert res['ok'] is True
    assert res['recommended_stop'] < res['price']


def test_strategy_meta_decay(monkeypatch):
    monkeypatch.setattr(v36, 'fetch_ohlcv', lambda symbol, period='1y', interval='1d': sample_df())
    rot=v36.strategy_rotation(['AAA','BBB'])
    meta=v36.meta_ai_filter({'signal':'BUY','score':80}, {'ok':True,'profit_factor':1.6,'sharpe':1.2,'max_drawdown_pct':-10}, {'pass':True}, {'pass':True})
    decay=v36.alpha_decay_detector([{'ok':True,'symbol':'AAA','sharpe':1.6,'profit_factor':1.7,'max_drawdown_pct':-8,'trades':10}])
    assert rot['ok'] is True
    assert meta['decision'] == 'ALLOW'
    assert decay['rows'][0]['status'] == 'HEALTHY'


def test_attribution_allocation_healing_report(monkeypatch):
    df=sample_df()
    monkeypatch.setattr(v36, 'fetch_ohlcv', lambda symbol, period='1y', interval='1d': df)
    attr=v36.portfolio_attribution([{'symbol':'AAA','pnl':100,'strategy':'trend'},{'symbol':'BBB','pnl':-20,'strategy':'momentum'}])
    alloc=v36.capital_allocation_engine(['AAA','BBB'], 100000)
    heal=v36.self_healing_monitor(['AAA','BBB'])
    assert attr['total_pnl'] == 80
    assert any(r['symbol']=='CASH' for r in alloc['rows'])
    assert heal['status'] == 'OK'


def test_v36_full_report(monkeypatch):
    df=sample_df(420)
    monkeypatch.setattr(v36, 'fetch_ohlcv', lambda symbol, period='1y', interval='1d': df)
    res=v36.v36_institutional_report(['AAA','BBB'], account_equity=100000)
    assert res['ok'] is True
    assert 'capital_allocation' in res
    assert 'readiness' in res
