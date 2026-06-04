# V25.3 Option Flow Intelligence

ต่อจากฐาน V25.2 Earnings Intelligence โดยไม่ลบระบบเดิม

## เพิ่มใหม่
- Put/Call Ratio Engine
- Open Interest Engine
- OI Magnet Level
- Unusual Volume Proxy
- Option Flow Score 0-100
- Alert Filter: Technical Score + Flow Score + Risk Grade + Market Context
- Dashboard สำหรับ Option Flow
- ตาราง PostgreSQL/SQLite:
  - option_flow
  - option_oi
  - option_unusual_volume
  - option_flow_alert_filter

## API
- `/v25/flow`
- `/v25/flow/NVDA?score=88&side=CALL`
- `/v25/oi`
- `/v25/unusual-volume`
- `/v25/flow-score?symbol=NVDA&score=88&side=CALL`
- `/v25/flow-alert?symbol=NVDA&technical_score=88&side=CALL&risk_grade=A`
- `/v25/flow-dashboard`

## หมายเหตุ
ใช้ yfinance option-chain snapshot เป็นแหล่งฟรี ดังนั้น Unusual Volume เป็น proxy จาก current volume เทียบกับ OI/median chain volume ไม่ใช่ historical paid option-flow data
