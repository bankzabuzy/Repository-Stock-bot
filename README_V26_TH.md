# V26.0 Professional Execution Intelligence Suite

ต่อจากฐาน V25.5 โดยไม่ลบไฟล์เดิม เพิ่ม 5 Engine หลัก:

## V26.1 Real Options Chain Intelligence
- ใช้ option chain จริงจาก `yfinance` สำหรับ Volume และ Open Interest
- Put/Call Ratio
- Call Wall / Put Wall
- Zero Gamma Proxy
- Flow Score
- หมายเหตุ: Greeks/GEX เป็น proxy เพราะข้อมูลฟรีไม่มี dealer-grade gamma จริง

## V26.2 Liquidity Engine
- VIX
- DXY
- US10Y
- SPY / QQQ context
- Liquidity Score
- Risk Mode: RISK_ON / NEUTRAL / RISK_OFF

## V26.3 Regime Switching AI
- Trend Up / Trend Down / Range Transition
- Volatility Expansion / Compression / Panic
- เปลี่ยน Model Profile ตามสภาพตลาด

## V26.4 Position Management AI
- Dynamic TP/SL
- Trailing Stop
- Scale Out Plan
- Position Sizing ตาม Score/Quality

## V26.5 Portfolio Simulation
- คัดตัวดีที่สุดจากธีมเดียวกัน
- กัน NVDA/AMD/TSM/AVGO ส่งพร้อมกันทั้งหมด
- Sector Exposure Cap
- Portfolio Quality Score

## API ใหม่
- `/v26`
- `/v26/dashboard`
- `/v26/json`
- `/v26/options-chain/NVDA`
- `/v26/liquidity`
- `/v26/spy-ema200`
- `/v26/regime/NVDA?score=91&side=CALL`
- `/v26/position-plan/NVDA?entry=214&side=CALL&score=90&quality_score=86`
- `/v26/portfolio-sim`

## หมายเหตุสำคัญ
V26 ใช้ข้อมูลฟรีเป็นหลัก จึงยังไม่เทียบเท่าข้อมูล dealer gamma/greeks แบบเสียเงินเต็มรูปแบบ แต่เพิ่มระดับความเป็น Execution Intelligence ได้มากกว่าระบบ alert ทั่วไป
