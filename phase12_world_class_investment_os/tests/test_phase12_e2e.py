from phase12_world_class_investment_os.ops.phase12_pipeline import Phase12Pipeline

def test_phase12_end_to_end_runs():
    pipe = Phase12Pipeline()
    result = pipe.run(
        symbols=["AAPL", "NVDA", "GLD"],
        macro_input={"cpi_yoy": 3.2, "policy_rate": 5.0},
        sentiment_input={"retail_euphoria": 50, "fear_index": 40, "news_sentiment": 60},
        account={"drawdown_pct": 0.0, "daily_loss_pct": 0.0},
        mode="shadow"
    )
    assert result["version"] == "V1200"
    assert result["audit_verified"] is True
    assert "line_message" in result
    assert result["portfolio"]["selected_symbols"]
