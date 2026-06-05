# V27.0 Stability + Forward Test + Capital Protection

ต่อจากฐาน V26.9 โดยเพิ่มระบบที่สำคัญสำหรับการใช้งานจริงระยะยาว

## เพิ่มใหม่
- Forward Test Engine
- Real Alert Outcome Tracker
- Data Quality Guard
- Capital Protection Layer

## ไฟล์ใหม่
- modules/v27_forward_test_engine.py
- modules/v27_outcome_tracker.py
- modules/v27_data_quality_guard.py
- modules/v27_capital_protection.py
- modules/v27_stability_routes_snippet.py

## Route ที่เตรียมไว้
- POST /v27/forward-test/create
- POST /v27/outcome/check
- POST /v27/data-quality
- POST /v27/capital-protection
- POST /v27/position-multiplier

## จุดประสงค์
ระบบนี้ไม่ได้เพิ่ม Indicator แต่เพิ่มชั้นควบคุมความจริง:
- ทดสอบสัญญาณจริง 30-90 วัน
- ตรวจ TP/SL หลัง Alert
- กันข้อมูลเพี้ยน
- หยุดส่งเมื่อพอร์ต/ตลาดเสี่ยงเกินไป
