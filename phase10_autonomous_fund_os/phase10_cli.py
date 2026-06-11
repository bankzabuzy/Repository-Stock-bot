from phase10_autonomous_fund_os.brain.autonomous_fund_os import AutonomousFundOS

def main():
    osys = AutonomousFundOS()
    result = osys.decide(
        features={"volatility_score": 42, "trend_score": 78, "liquidity_score": 82, "macro_score": 65},
        alpha_scores={"momentum": 88, "ai_theme": 80, "semiconductor_theme": 76, "trend": 70},
        account={"drawdown_pct": 0.01, "daily_loss_pct": 0.0},
        user_context={"too_many_trades_today": 0},
        target_mode="shadow"
    )
    print(result)

if __name__ == "__main__":
    main()
