from phase9_live_fund_operation.storage.models import OrderIntent
from phase9_live_fund_operation.execution.order_engine import OrderEngine

def test_paper_order_runs():
    engine = OrderEngine(mode="paper", db_path=":memory:")
    result = engine.submit(OrderIntent(symbol="AAPL", side="buy", qty=1, strategy="test"))
    assert result["accepted"] is True
    assert result["report"]["status"] == "FILLED"
    engine.close()
