from phase9_live_fund_operation.storage.models import OrderIntent
from phase9_live_fund_operation.execution.order_engine import OrderEngine

def main():
    engine = OrderEngine(mode="paper", db_path="phase9_smoke_test.db")
    intent = OrderIntent(symbol="AAPL", side="buy", qty=1, strategy="phase9_smoke_test", confidence="B", reason="smoke test")
    result = engine.submit(intent)
    engine.close()
    print(result)

if __name__ == "__main__":
    main()
