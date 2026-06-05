# V34 Free Paper Trading + Broker + Kill Switch + Monitoring

เพิ่มชั้นใช้งานจริงแบบฟรี 100% ก่อนเชื่อมเงินจริง:

## สิ่งที่เพิ่ม

1. **Paper Trading Engine**
   - จำลองพอร์ต, เงินสด, position, P&L, equity curve
   - รองรับ fee/slippage เพื่อไม่ให้ backtest สวยหลอกตัวเอง

2. **Mock Broker Layer**
   - `MockBroker` สำหรับส่งคำสั่งจำลอง BUY/SELL
   - ไม่ต้องใช้ broker API เสียเงิน
   - เหมาะสำหรับ forward test / paper mode

3. **Kill Switch**
   - หยุดเปิดออร์เดอร์ใหม่เมื่อ daily loss หรือ drawdown เกินกำหนด
   - ลดความเสี่ยงเมื่อ drawdown เริ่มเข้าโซนอันตราย
   - ตรวจ consecutive loss streak

4. **Monitoring**
   - Equity, cash, exposure, positions
   - Win rate, profit factor, realized P&L
   - Alerts: drawdown สูง, exposure สูง, broker blocked, orders rejected

## API Routes

- `GET /v34/health`
- `POST /v34/paper-trade`
- `POST /v34/kill-switch`
- `POST /v34/mock-broker/order`
- `POST /v34/monitoring`
- `POST /v34/decision-pack`

## ตัวอย่าง payload /v34/decision-pack

```json
{
  "prices": {"QQQ": [100, 101, 103, 105]},
  "signals": {"QQQ": ["BUY", "HOLD", "SELL", "HOLD"]},
  "initial_cash": 100000,
  "weights": {"QQQ": 0.30},
  "fee_bps": 1,
  "slippage_bps": 2,
  "max_drawdown_limit_pct": -12,
  "hard_daily_loss_pct": -2
}
```

## ข้อจำกัดที่ต้องรู้

V34 ยังเป็น paper trading เท่านั้น ไม่ส่งคำสั่งเงินจริง นี่เป็นข้อดีสำหรับโหมดฟรีและปลอดภัยกว่า ก่อนใช้เงินจริงต้องทดสอบ forward 30-90 วันและต้องมี broker adapter แยกต่างหาก
