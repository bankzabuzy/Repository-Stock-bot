
# Module: Risk Control
def check_drawdown(portfolio, max_dd=0.1):
    equity = portfolio.cash + sum([p.entry*p.qty for p in portfolio.positions])
    initial = 100000
    drawdown = (initial - equity)/initial
    if drawdown >= max_dd:
        return False  # trigger kill switch
    return True
