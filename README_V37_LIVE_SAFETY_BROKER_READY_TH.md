# V37 Live Safety & Broker Ready ฟรี 100%

ต่อยอดจาก V36 โดยไม่ลบระบบเดิม เพิ่มชั้นความปลอดภัยก่อนใช้งานกับ Paper Broker / Dry-run

## โมดูลที่เพิ่ม
1. Broker Adapter Layer: Mock Broker + Alpaca Paper แบบ optional ผ่าน ENV
2. OMS: submit/cancel/history, dry-run เป็นค่าเริ่มต้น
3. Kill Switch: หยุด order เมื่อ drawdown/loss streak/manual stop
4. Capital Protection Mode: ลด risk หรือพักเทรดเมื่อ performance แย่
5. News/Event Risk Filter: calendar ฟรีแบบ offline ผ่าน `V37_EVENT_DATES`
6. Live Slippage Monitor
7. Model Drift Detector
8. Audit Log JSONL
9. Health Check Dashboard
10. Recovery Manager

## Route สำคัญ
- `/v37/dashboard`
- `/v37/report`
- `/v37/readiness`
- `/v37/pre-trade?symbol=SPY&dry_run=true`
- `/v37/oms/submit` POST
- `/v37/kill-switch`
- `/v37/health-dashboard`

## ความปลอดภัย
ค่าเริ่มต้นคือ `V37_DRY_RUN=true` และ `V37_BROKER=mock` จึงไม่ส่ง order จริง

หากต้องการใช้ Alpaca Paper:
```
ALPACA_API_KEY=xxx
ALPACA_SECRET_KEY=xxx
ALPACA_BASE_URL=https://paper-api.alpaca.markets
V37_BROKER=alpaca
V37_DRY_RUN=false
```

## หมายเหตุ
ระบบนี้ยังไม่ใช่คำแนะนำการลงทุน และต้อง Forward Test/Paper Broker อย่างน้อย 90 วันก่อนเงินจริง
