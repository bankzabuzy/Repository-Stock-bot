# V35.3 FREE ALPHA STACK

เวอร์ชันนี้ต่อยอดจาก V35.2 โดยเพิ่ม 5 โมดูลสำคัญสำหรับ Research / Paper Trading แบบฟรี 100%

## เพิ่มใหม่

1. Portfolio Optimizer
- จัดน้ำหนักพอร์ตอัตโนมัติด้วย score + ensemble + momentum + inverse volatility
- จำกัดน้ำหนักต่อสินทรัพย์ และปรับ cap ให้ feasible เมื่อมีสัญลักษณ์น้อย
- API: `/v35/portfolio-optimizer?symbols=NVDA,META,SPY,QQQ`

2. Position Sizing Engine
- ใช้ risk budget + half Kelly + volatility target + max cap
- API: `POST /v35/position-sizing`

3. Ensemble Signal
- รวม Trend, Momentum, Mean Reversion, Volume
- API: `/v35/ensemble?symbols=NVDA,META,SPY`

4. Monte Carlo Stress Test
- จำลอง 100–10,000 รอบ แบบ bootstrap จากผลตอบแทนจริง
- API: `/v35/monte-carlo?symbols=NVDA,SPY&simulations=2000`

5. Trade Journal AI
- รับข้อมูล trade แล้วสรุป win/loss, PnL, จุดอ่อนราย symbol และคำแนะนำลดความเสี่ยง
- API: `POST /v35/trade-journal`

## API รวม

- `/v35/health`
- `/v35/dashboard`
- `/v35/ranking`
- `/v35/alpha-stack`
- `/v35/portfolio-optimizer`
- `/v35/ensemble`
- `/v35/position-sizing`
- `/v35/monte-carlo`
- `/v35/trade-journal`
- `/v35/backtest`
- `/v35/walk-forward`
- `/v35/risk-gate`

## การตรวจสอบ

- Unit tests ผ่าน 34/34
- Route smoke test ผ่านเมื่อเปิด `DISABLE_YFINANCE=true` สำหรับสภาพแวดล้อม offline
- ระบบยังเป็น Research / Paper Trading ไม่ใช่คำแนะนำการลงทุนหรือระบบส่งคำสั่งเงินจริง

## หมายเหตุการใช้งานจริง

ตั้งค่า watchlist และรัน forward test 30–90 วันก่อนใช้เงินจริงทุกครั้ง

เป้าหมายก่อนเงินจริง:
- Win Rate > 50%
- Profit Factor > 1.5
- Sharpe > 1.5
- Max Drawdown < 15%
- Expectancy เป็นบวก
- Forward Test 90 วันมีกำไร
