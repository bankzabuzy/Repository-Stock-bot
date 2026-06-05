# REVIEW AND UPGRADE V32 — Institutional Risk & Backtest Core

## ตรวจแล้ว
- `python -m compileall -q .` ผ่าน
- ก่อนแก้ `python -m unittest discover -v` ไม่เจอเทสต์ 0 รายการ เพราะโฟลเดอร์ `tests` ยังไม่เป็น package
- หลังแก้ เพิ่ม `tests/__init__.py` แล้ว `python -m unittest discover -v` ผ่าน 13/13 tests

## สิ่งที่เพิ่ม
1. `modules/v32_institutional_risk_core.py`
   - position sizing ตาม equity, stop distance, max exposure
   - pre-trade risk gate: confidence, stop-loss, reward/risk, portfolio heat, daily loss breaker
   - backtest engine: fee, slippage, stop-loss, take-profit, next-bar execution
   - walk-forward report เพื่อลดความเสี่ยง overfitting

2. `modules/v32_institutional_risk_routes.py`
   - `/v32/health`
   - `/v32/position-size`
   - `/v32/pretrade-gate`
   - `/v32/backtest`
   - `/v32/walk-forward`

3. `main.py`
   - register V32 routes

4. `tests/test_v32_institutional_risk.py`
   - ทดสอบ position sizing
   - ทดสอบ pretrade gate
   - ทดสอบ backtest และ walk-forward

## ข้อจำกัดที่ยังต้องรู้
ระบบนี้ยังไม่ใช่เครื่องพิมพ์เงิน ต้องมีข้อมูลจริงย้อนหลังคุณภาพสูง, survivorship-bias-free universe, slippage ตาม asset จริง, broker execution, monitoring และ kill switch ที่ enforce จริงก่อนใช้เงินทุนขนาดใหญ่

## คำสั่งทดสอบ
```bash
pip install -r requirements.txt
python -m compileall -q .
python -m unittest discover -v
```
