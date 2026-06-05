# V33 Institutional Portfolio Core

เพิ่มโมดูลระดับพอร์ตที่ควรมี ก่อนเรียกระบบว่าใกล้เคียงกองทุน:

1. Relative Strength Ranking  
   เปรียบเทียบสินทรัพย์กับ benchmark เช่น NVDA เทียบ QQQ, หุ้นไทยเทียบ SET/SET50

2. Portfolio Allocation  
   จัดน้ำหนักตาม score + probability + relative strength พร้อมหักโทษ volatility/drawdown และมี cash floor/max weight

3. Drawdown Control  
   ถ้า equity curve เสียหายเกินเกณฑ์ จะลดขนาดไม้หรือ block ไม้ใหม่อัตโนมัติ

4. Walk-Forward Validation  
   ทดสอบสัญญาณแบบแบ่งช่วงเวลา เพื่อลดความเสี่ยง overfit จาก backtest ช่วงเดียว

## API ใหม่

- `GET /v33/health`
- `POST /v33/relative-strength`
- `POST /v33/portfolio-allocation`
- `POST /v33/drawdown-control`
- `POST /v33/walk-forward-validation`
- `POST /v33/decision-pack`

> หมายเหตุ: ระบบนี้เป็น research/risk engine ไม่ใช่คำแนะนำลงทุนและไม่รับประกันกำไร ต้อง paper trade และตรวจ live slippage ก่อนใช้เงินจริง
