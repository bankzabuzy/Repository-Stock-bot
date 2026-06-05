# V31.1 Alert Session Control Patch

แพตช์นี้ต่อจาก V31 Alpha Research & Performance Attribution Core โดยเน้นแก้จุดสำคัญเรื่องการแจ้งเตือนอัตโนมัติ

## สถานะค่าเริ่มต้น

- `ENABLE_THAI_STOCK_ALERTS=false` ปิด auto alert หุ้นไทยเป็นค่าเริ่มต้น
- `ENABLE_US_STOCK_ALERTS=true` เปิด auto alert หุ้นสหรัฐ
- `ENABLE_US_SESSION_ONLY=true` ให้หุ้นสหรัฐแจ้งเตือนเฉพาะช่วงตลาดเปิด
- `ENABLE_US_REGULAR_SESSION_ONLY=true` บล็อก premarket/after-hours เป็นค่าเริ่มต้น
- `USE_US_EXCHANGE_TIME=true` ใช้เวลา New York Exchange เพื่อรองรับ DST และ session ข้ามวันตามเวลาไทย

## ตัวแปรที่ควรตั้งบน Railway/Render

```env
ENABLE_AUTO_ALERTS=true
ENABLE_THAI_STOCK_ALERTS=false
ENABLE_US_STOCK_ALERTS=true
ENABLE_US_SESSION_ONLY=true
ENABLE_US_REGULAR_SESSION_ONLY=true
USE_US_EXCHANGE_TIME=true
US_ALLOW_PREMARKET_ALERTS=false
```

## Route ตรวจสอบ

- `/watchlist-status` ดูว่า scan list มีหุ้นไทยหลุดเข้ามาหรือไม่
- `/market-hours-status` ดูสถานะ market guard และเวลาตลาด

## สิ่งที่แก้

1. ตัดหุ้นไทยออกจาก auto scan list เมื่อ `ENABLE_THAI_STOCK_ALERTS=false`
2. บล็อกหุ้นไทยที่ risk/market gate แม้หลุดเข้ามาจาก WATCHLIST เดิม
3. หุ้นสหรัฐใช้เวลา `America/New_York` แทนการเช็ค weekday ไทยแบบเดิม
4. ปิด premarket/after-hours เป็นค่าเริ่มต้น
5. Audit log บันทึก `market_open` จาก market gate จริง ไม่ใส่ `True` ตายตัว

