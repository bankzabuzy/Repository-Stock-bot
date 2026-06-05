# V25.2 Earnings Intelligence Engine

ต่อจาก V25.1 โดยไม่ลบระบบเดิม

## เพิ่มใหม่
- Earnings Calendar Engine
- Earnings Risk Scoring
- Earnings Guard ก่อนส่ง Alert
- Position Size Reduction เมื่อใกล้วันงบ
- Block Signal เมื่อ Earnings ใกล้เกินกำหนด
- บันทึก `earnings_events` และ `earnings_blocked_signals` ลงฐานข้อมูล
- API และ Dashboard ใหม่

## Routes
- `/v25/earnings`
- `/v25/earnings/NVDA`
- `/v25/earnings-calendar`
- `/v25/earnings-risk?symbol=NVDA&score=91&side=CALL`
- `/v25/earnings-dashboard?symbol=NVDA`

## Environment Variables
- `V25_EARNINGS_BLOCK_DAYS=1`
- `V25_EARNINGS_CAUTION_DAYS=5`
- `V25_EARNINGS_LOOKAHEAD_DAYS=21`
- `V25_EARNINGS_REDUCE_SIZE_PCT=50`
- `V25_EARNINGS_STRICT_BLOCK=true`

## หมายเหตุ
ถ้ามี `FINNHUB_API_KEY` จะใช้ Finnhub ก่อน ถ้าไม่มีจะ fallback ไป Yahoo Finance ผ่าน yfinance
