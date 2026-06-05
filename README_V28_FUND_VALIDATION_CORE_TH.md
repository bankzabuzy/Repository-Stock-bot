# Repository Stock Bot — V28 Fund Validation Core

เวอร์ชันนี้ต่อจาก V27.7 โดยไม่ลบฟีเจอร์เดิม และเพิ่มชั้นตรวจสอบระดับกองทุนก่อนส่งสัญญาณ/ติดตามผลจริง

## สิ่งที่เพิ่มใน V28

### 1) Real Audit DB ทุกสัญญาณ
เพิ่มตาราง `v28_signal_audit` เพื่อบันทึกการตัดสินใจของระบบทุกครั้งที่เจอสัญญาณจริง ได้แก่
- symbol / asset type / side
- decision: PASS, FAIL, SENT
- reason ที่ผ่านหรือถูก block
- score, confidence, trend, rvol, regime
- entry, stop loss, TP1/TP2/TP3
- portfolio gate result
- raw payload และ decision hash ป้องกันข้อมูลซ้ำ

Route:
- `GET /v28/audit`
- `POST /v28/audit`

### 2) Real Outcome Scheduler
เพิ่มตาราง:
- `v28_open_signals`
- `v28_signal_outcomes`

เมื่อสัญญาณผ่านและส่ง LINE ระบบจะสร้าง open signal สำหรับติดตามผล TP/SL ต่อได้

Route:
- `GET /v28/open-signals`
- `GET /v28/outcomes`
- `GET /v28/outcome/run`

หมายเหตุ: Scheduler เป็น on-demand route พร้อมใช้งานกับ cron ภายนอก เช่น Railway Cron, Render Cron, GitHub Actions หรือ cron-job.org

### 3) Portfolio Risk Engine จริง
เพิ่ม `evaluate_portfolio_risk()` และ `portfolio_gate()` เพื่อคุมความเสี่ยงก่อนส่งสัญญาณ โดยตรวจ:
- total heat R
- symbol duplicate heat
- theme heat
- correlation กับ position เปิดอยู่
- portfolio VaR แบบ conservative proxy
- beta เทียบ SPY

ENV ที่ตั้งค่าได้:
- `V28_MAX_TOTAL_HEAT_R` default `6.0`
- `V28_MAX_SYMBOL_HEAT_R` default `1.25`
- `V28_MAX_THEME_HEAT_R` default `2.5`
- `V28_MAX_CORRELATION` default `0.80`
- `V28_MAX_PORTFOLIO_VAR_R` default `3.5`

Route:
- `GET /v28/risk?symbol=NVDA`
- `POST /v28/risk`
- `GET /v28/portfolio-gate?symbol=NVDA&sig=BUY&price=100`

### 4) Walk-forward Backtest Report
เพิ่ม walk-forward engine สำหรับตรวจสอบกลยุทธ์แบบแบ่ง train/test window โดยใช้ข้อมูลราคา yfinance

Route:
- `GET /v28/walk-forward?symbol=SPY&period=2y&interval=1d`
- `GET /v28/walk-forward-runs`

Metric ที่บันทึก:
- trades
- win rate
- expectancy R
- total return R
- max drawdown R
- profit factor
- PASS/FAIL

### 5) Fund Dashboard แยกหมวด
เพิ่ม dashboard แยก 4 ส่วน:
- Signal
- Risk
- Performance
- Compliance

Route:
- `GET /v28/fund-dashboard`
- `GET /v28/fund-dashboard.json`
- `GET /v28/health`

## จุดที่แก้จาก V27.7

- V27.7 เดิมมีหลาย route เป็น preview/mock; V28 เพิ่มฐานข้อมูลจริงและ route ที่บันทึกข้อมูลจริง
- auto alert loop ถูก hook ให้บันทึก audit เมื่อ signal ผ่าน/ไม่ผ่าน และเมื่อส่ง LINE สำเร็จ
- เพิ่ม portfolio risk gate เข้า `should_send_alert_final()` โดยไม่ลบ gate เดิมของ V26.7/V27
- เพิ่ม fallback หาก import yfinance ไม่สำเร็จ เพื่อไม่ให้แอปล่มตอน import ในบาง environment
- เพิ่มการสร้าง TP/SL เชิง validation หาก legacy analysis ไม่มีแผน TP/SL เพื่อให้ outcome tracking ทำงานได้

## ข้อจำกัดที่ยังต้องรู้ตรง ๆ

ระบบนี้ยังไม่ใช่ production fund execution แบบสมบูรณ์ เพราะยังไม่มี:
- broker execution integration
- immutable external audit store
- user permission/admin role เต็มรูปแบบ
- managed PostgreSQL migration สำหรับ V28 tables
- compliance approval workflow

แต่เวอร์ชันนี้พร้อมสำหรับ forward test จริง 30–90 วัน และใช้เป็น Fund Validation Lab ได้ดีกว่า V27.7 ชัดเจน
