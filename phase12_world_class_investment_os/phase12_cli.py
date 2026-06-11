from phase12_world_class_investment_os.ops.phase12_pipeline import Phase12Pipeline

def main():
    
pipe = Phase12Pipeline()
from .market.live_price_fetcher import LivePriceFetcher
fetcher = LivePriceFetcher(symbols=["GLD","NVDA","TSM","QQQ","AAPL","PTT.BK"])
live_prices = fetcher.fetch()
print("=== Live Prices ===")
for sym, d in live_prices.items():
    print(f"{sym} | Close: {d['close']} ({d['change_close_pct']}%) | Pre-market: {d['pre_market']} ({d['change_premarket_pct']}%)")

    result = pipe.run(
        symbols=["AAPL", "NVDA", "TSM", "QQQ", "GLD", "PTT.BK"],
        macro_input={"cpi_yoy": 3.4, "policy_rate": 5.25, "usd_strength": 62},
        sentiment_input={"retail_euphoria": 72, "fear_index": 45, "news_sentiment": 58},
        account={"drawdown_pct": 0.01, "daily_loss_pct": 0.0},
        mode="shadow"
    )
    print(result["line_message"])
    print("AUDIT_VERIFIED:", result["audit_verified"])

if __name__ == "__main__":
    main()
