# V26.7 Market Breadth + Sector Rotation Intelligence

ต่อจากฐาน V26.6 โดยไม่ลบระบบเดิม

## เพิ่มใหม่
- Market Breadth Engine
- Sector Rotation Engine
- Money Flow Engine
- Relative Strength Ranking
- Weak Market Suppression
- Best-of-Theme Selection
- Sector Boost / Sector Penalty
- ตาราง PostgreSQL/SQLite ใหม่:
  - `market_breadth`
  - `sector_rotation`
  - `money_flow`
  - `relative_strength`
  - `suppressed_signals`

## API ใหม่
- `/v26/breadth`
- `/v26/sector-rotation`
- `/v26/money-flow`
- `/v26/relative-strength`
- `/v26/suppression/NVDA?score=90&side=CALL`
- `/v26/best-of-theme?symbols=NVDA,AMD,AVGO,TSM`
- `/v26/suppressed-signals`
- `/v26/market-intelligence-dashboard`

## Logic สำคัญ
ก่อนส่ง Alert ระบบจะเช็กเพิ่ม:
- Breadth < 40: Block/Reduce CALL Alert
- Sector อ่อน: ลดคะแนน
- Relative Strength ต่ำ: ลดคะแนน
- หุ้นธีมเดียวกัน เช่น NVDA/AMD/AVGO/TSM: เลือกตัวดีที่สุดตัวเดียว

## หมายเหตุ
ข้อมูลใช้แหล่งฟรีผ่าน Yahoo Finance/yfinance จึงเป็น market intelligence proxy ไม่ใช่ข้อมูล institutional paid feed
