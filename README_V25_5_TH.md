# V25.5 Trade Quality Prediction Engine

เพิ่มต่อจาก V25.4 โดยไม่ลบระบบเดิม

## สิ่งที่เพิ่ม
- Predicted Win Rate
- Expected Return (R)
- Expected Drawdown (R)
- Historical Similarity
- Trade Quality Score / Grade
- Trade Quality Gate ก่อนส่ง Alert
- บันทึกผลลง PostgreSQL ตาราง `trade_quality_predictions`
- ตาราง Outcome `trade_quality_outcomes` สำหรับบันทึกผล TP/SL จริงภายหลัง

## API ใหม่
- `/v25/trade-quality/NVDA?score=91&flow_score=88&context_score=82&risk_grade=A&side=CALL&strategy=BREAKOUT&rvol=2.1&rsi=64&regime=UPTREND`
- `/v25/trade-quality-gate?symbol=NVDA&score=91&flow_score=88&context_score=82&risk_grade=A`
- `/v25/trade-quality/recent`
- `/v25/trade-quality-dashboard`

## หลักการ
ระบบจะไม่ดูแค่ “มีสัญญาณ” แต่ประเมินก่อนว่า “สัญญาณนี้มีโอกาสทำเงินจริงแค่ไหน” โดยใช้ข้อมูลย้อนหลังเท่าที่มี + Technical Score + Flow Score + Market Context + Risk Grade
