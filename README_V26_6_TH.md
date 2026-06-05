# V26.6 Trade DNA + Conviction Engine

ต่อจาก V26.0 โดยไม่ลบระบบเดิม

## เพิ่มใหม่
- Trade DNA Engine
- DNA Statistics
- Historical Similarity
- Predicted Win Rate
- Expected Return
- Expected Drawdown
- Conviction Score / Grade
- Conviction Gate ก่อนส่ง Alert
- Dashboard: `/v26/conviction-dashboard`

## API
- `/v26/dna/NVDA`
- `/v26/conviction?symbol=NVDA&score=90&flow_score=85&context_score=80&rvol=2.1&rsi=61&regime=UPTREND`
- `/v26/conviction-gate?symbol=NVDA&score=90&flow_score=85&context_score=80`
- `/v26/dna-stats`
- `/v26/conviction-history`

## Tables
- `trade_dna_patterns`
- `dna_statistics`
- `conviction_history`
