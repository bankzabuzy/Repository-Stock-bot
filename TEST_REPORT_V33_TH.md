# Test Report V33

วันที่ตรวจ: 2026-06-05

## สิ่งที่เพิ่ม

- `modules/v33_institutional_portfolio_core.py`
- `modules/v33_institutional_portfolio_routes.py`
- `tests/test_v33_institutional_portfolio.py`
- `README_V33_INSTITUTIONAL_PORTFOLIO_TH.md`
- Register route V33 ใน `main.py`

## คำสั่งที่รันผ่าน

```bash
python -m compileall -q .
python -m unittest discover -v
```

## ผลลัพธ์

- Compile ผ่าน
- Unit tests ผ่านทั้งหมด 18/18

## ข้อจำกัดของ sandbox ตอนตรวจ

Environment นี้ไม่มี package `flask` และ `yfinance` ติดตั้ง จึงไม่ได้ import `main.py` แบบ full Flask runtime ใน sandbox ได้โดยตรง แต่ `requirements.txt` มี dependency ที่ต้องใช้สำหรับ deployment แล้ว:

```text
flask
requests
gunicorn
yfinance
beautifulsoup4
psycopg2-binary
```

## คำสั่งแนะนำก่อน deploy จริง

```bash
pip install -r requirements.txt
python -m unittest discover -v
gunicorn main:app
```

## Hard Rule ก่อนใช้เงินจริง

ระบบนี้ผ่านระดับ code/unit test แต่ยังไม่ใช่หลักฐานว่าทำกำไรจริง ต้อง paper trade, monitor slippage, live data delay, broker rejection, และ kill-switch ก่อนใช้เงินจริง
