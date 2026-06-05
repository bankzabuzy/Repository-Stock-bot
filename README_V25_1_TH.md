# V25.1 Market Context AI

ต่อจากฐาน V24.0/V23.x เดิม โดยไม่ลบ `main.py` เดิม

เพิ่ม:
- ตรวจ FOMC วันนี้หรือไม่
- ตรวจ Earnings ของสัญลักษณ์ เช่น NVDA ประกาศงบใกล้หรือไม่
- ตรวจ VIX > 25 แล้วลดคะแนน CALL / High-beta
- ตรวจ SPY อยู่เหนือ/ใต้ EMA200
- สร้าง Market Context Score และ Adjusted Score
- บันทึก Snapshot ลงฐานข้อมูล

Endpoints:
- `/v25`
- `/v25/dashboard`
- `/v25/context`
- `/v25/context/NVDA`
- `/v25/adjust-score?symbol=NVDA&score=91&side=CALL`
- `/v25/health`

Environment ที่ใช้เพิ่มได้:
- `V25_VIX_HIGH=25`
- `V25_FOMC_DATES=2026-06-17,2026-07-29`
- `V25_EARNINGS_BLOCK_DAYS=1`
- `V25_EARNINGS_CAUTION_DAYS=3`
- `V25_CONTEXT_STRICT=true`
