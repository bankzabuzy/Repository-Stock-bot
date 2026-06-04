# V30 Institutional Model Validation & Paper Trading Core

ต่อยอดจาก V29 Production Hardening & Governance Core โดยเพิ่มชั้นพิสูจน์คุณภาพโมเดลและ Paper Trading ก่อนใช้งานจริงระดับ production/fund workflow

## สิ่งที่เพิ่มใน V30

1. **Institutional Model Validation Engine**
   - Walk-forward validation พร้อม friction จริงระดับพื้นฐาน
   - คิด slippage และ commission
   - วัด win rate, expectancy R, profit factor, max drawdown, Sharpe, Sortino
   - บันทึกผลลง `v30_validation_runs`

2. **Paper Trading Core**
   - บัญชีจำลอง `v30_paper_accounts`
   - เปิด/ปิดสถานะจำลอง `v30_paper_positions`
   - บันทึกคำสั่งซื้อขาย `v30_paper_trades`
   - mark-to-market และ equity snapshot `v30_equity_snapshots`

3. **Deployment Check**
   - ตรวจ ENV สำคัญ เช่น LINE token, DATABASE_URL, API key, watchlist, provider keys
   - บันทึกลง `v30_deployment_checks`

4. **Data Reconciliation**
   - ตรวจความต่างของราคาจากหลายแหล่ง
   - ถ้าราคาเพี้ยนเกิน threshold ให้ขึ้นสถานะ BLOCK
   - บันทึกลง `v30_data_reconciliation`

5. **V30 Validation Gate**
   - เชื่อมกับ `should_send_alert_final()`
   - ค่าเริ่มต้นเป็น `observe` เพื่อไม่บล็อกสัญญาณเดิมทันที
   - ถ้าต้องการให้บล็อกจริง ตั้ง `V30_VALIDATION_GATE_MODE=block`

6. **แก้จุดเดิม**
   - ย้าย `app.run()` ไปท้ายไฟล์ เพื่อให้ route/gate ที่ append หลัง V13 โหลดครบก่อน Flask start เมื่อรันด้วย `python main.py`
   - แก้ `Store.execute()` ของ V29 ให้ปิด connection จริง ลด ResourceWarning
   - เพิ่ม test suite ของ V30

## Route หลัก

- `/v30/health`
- `/v30/deployment-check`
- `/v30/validate?symbol=SPY`
- `/v30/paper/signal?symbol=SPY&side=BUY&price=100`
- `/v30/paper/mark-to-market`
- `/v30/reconcile?symbol=SPY`
- `/v30/validation-gate?symbol=SPY&sig=BUY`
- `/v30/dashboard`
- `/v30/dashboard.json`
- `/v30/table/<table>`

## ENV แนะนำ

```bash
V30_INITIAL_CASH=100000
V30_RISK_PER_TRADE_PCT=1.0
V30_MAX_POSITION_PCT=20.0
V30_SLIPPAGE_BPS=8
V30_COMMISSION_BPS=2
V30_MIN_VALIDATION_TRADES=20
V30_MIN_EXPECTANCY_R=0.05
V30_MIN_PROFIT_FACTOR=1.10
V30_MAX_VALIDATION_DD_PCT=18
V30_VALIDATION_GATE_MODE=observe
V30_RECONCILIATION_MAX_DIFF_PCT=1.0
```

## การทดสอบใน sandbox

ผ่านคำสั่ง:

```bash
python3 -m py_compile main.py modules/v29_governance_core.py modules/v30_model_validation_core.py modules/v30_model_validation_routes.py
python3 -m unittest discover -s tests -v
```

ผลทดสอบ: V29 + V30 รวม 7 tests ผ่าน

## หมายเหตุสำคัญ

Sandbox นี้ไม่มี Flask/yfinance จึงยังไม่ได้รัน Flask server เต็มรูปแบบในเครื่องทดสอบนี้ แต่ syntax และ unit tests ของ core ผ่านแล้ว หลัง deploy บน Railway/Render ที่ติดตั้ง `requirements.txt` แล้ว ให้ทดสอบ `/v30/deployment-check` และ `/v30/dashboard` อีกครั้ง
