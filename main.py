V21.5 Auto Journal + Outcome Database + Strategy Performance Database

Install:
1) Copy main.py to GitHub over your current main.py
2) Commit
3) Railway redeploys

Test routes:
/v21-5/status
/v21-5
/v21-5/journal
/v21-5/outcomes
/v21-5/strategy-db
/v21-5/equity
/v21-5/backfill
/v21-5/auto-journal?limit=5
/v21-5/journal/open/NVDA?side=CALL&entry=212&stop=205&target=225&strategy=MOMENTUM&qty=1
/v21-5/journal/close/1?exit=220
/v21-5/api/snapshot

Important:
- /v21-5/backfill imports already closed V21 trades into the V21.5 outcome database.
- /v21-5/auto-journal logs research candidates only; it does not place trades.
