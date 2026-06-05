"""Free V34 paper-trading CLI.

Usage:
  python v34_paper_cli.py
  python v34_paper_cli.py payload.json

The optional JSON payload uses the same shape as /v34/decision-pack.
"""
from __future__ import annotations

import json
import sys

from modules.v34_free_paper_trading_core import v34_decision_pack


DEFAULT_PAYLOAD = {
    "prices": {
        "QQQ": [100, 101, 103, 104, 106, 108, 107, 110],
        "SPY": [100, 100.5, 101, 100.7, 102, 103, 102.5, 104],
    },
    "signals": {
        "QQQ": ["BUY", "HOLD", "HOLD", "HOLD", "SELL", "HOLD", "BUY", "HOLD"],
        "SPY": ["HOLD", "BUY", "HOLD", "SELL", "HOLD", "HOLD", "HOLD", "HOLD"],
    },
    "initial_cash": 100000,
    "weights": {"QQQ": 0.30, "SPY": 0.20},
    "fee_bps": 1,
    "slippage_bps": 2,
    "max_drawdown_limit_pct": -12,
    "hard_daily_loss_pct": -2,
}


def load_payload(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    payload = load_payload(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PAYLOAD
    result = v34_decision_pack(payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
