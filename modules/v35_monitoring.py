
# Module: Monitoring / Alerts
import datetime

def log_trade(trade):
    print(f'[{datetime.datetime.now()}] Trade {trade.symbol} {trade.status} Entry:{trade.entry} Qty:{trade.qty}')
