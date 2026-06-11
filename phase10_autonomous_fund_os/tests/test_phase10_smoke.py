from phase10_autonomous_fund_os.brain.autonomous_fund_os import AutonomousFundOS

def test_phase10_decision_runs():
    osys = AutonomousFundOS()
    result = osys.decide(
        features={"volatility_score": 50, "trend_score": 70, "liquidity_score": 80, "macro_score": 60},
        alpha_scores={"momentum": 80, "trend": 70},
        account={"drawdown_pct": 0.0, "daily_loss_pct": 0.0},
        target_mode="shadow"
    )
    assert result["phase"] == "V1000_PHASE10"
    assert result["status"] == "SHADOW_RECORDED"
