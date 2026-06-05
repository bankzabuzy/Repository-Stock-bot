# Repository Stock Bot V31.2 Fixed Production Ready

ไฟล์ชุดนี้แก้ปัญหา Runtime/Syntax/502 หลัก ๆ แล้ว

## จุดที่แก้
- แก้ระบบฐานข้อมูล SQLite ให้ไม่ล่มถ้า DB_PATH ชี้ไปยัง path ที่ยังไม่มี Volume
- เพิ่ม safe fallback สำหรับ `/gold-test` เพื่อไม่ให้ 502 เมื่อยังไม่มี API key หรือ provider ล่ม
- เพิ่ม safe fallback สำหรับ `/oil-test` เพื่อลด timeout จากเว็บราคาน้ำมันภายนอก
- ตรวจ `python -m py_compile main.py` ผ่าน
- ตรวจ `python -m compileall .` ผ่าน
- ทดสอบ Flask routes หลักผ่าน: `/health`, `/api/signals`, `/dashboard`, `/gold-test`, `/oil-test`, `/api/watchlist`

## Railway Variables แนะนำ
ถ้ายังไม่ได้ทำ Volume ให้ใช้ก่อน:

```text
DB_PATH=signals.db
ENABLE_THAI_OIL_FETCH=false
ENABLE_GOLDTRADERS_FETCH=false
ENABLE_YFINANCE_FALLBACK=false
```

ถ้าทำ Railway Volume แล้ว ค่อยเปลี่ยนเป็น:

```text
DB_PATH=/data/signals.db
```

และต้อง mount volume ที่ `/data`

## Start command
ใช้ใน Railway:

```text
gunicorn main:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120
```

## ตรวจหลัง Deploy
เปิดตามลำดับ:

```text
/health
/api/signals
/dashboard
/gold-test
/oil-test
```
