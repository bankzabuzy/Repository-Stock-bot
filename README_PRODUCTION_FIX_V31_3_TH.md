# V31.3 Production Fix

แก้ไขหลัก:
- เปิด /status ให้ใช้งานได้
- เพิ่ม /scan-now สำหรับสแกนและบันทึก signal ทันที
- เพิ่ม /seed-signal สำหรับสร้างข้อมูลทดสอบลงตาราง signals
- เปิด Auto Signal Scan ตอนรันบน Railway/Gunicorn ไม่ต้องรอ if __name__ == "__main__"
- แก้ให้ราคาทองไทยใช้ Gold Traders Association เป็นค่าเริ่มต้นก่อน แล้ว fallback เป็นค่าประมาณเฉพาะตอนดึงไม่สำเร็จ
- ไม่บังคับส่ง LINE alert ถ้าไม่ได้ตั้ง ALERT_USER_IDS

ทดสอบหลัง Deploy:
1. /health ต้องขึ้น OK
2. /status ต้องเห็น signals_count
3. /scan-now ต้องได้ JSON results และมีข้อมูลถูกบันทึก
4. /api/signals ต้องไม่เป็น [] หลัง /scan-now
5. /dashboard ต้องมีแถวข้อมูล
6. /gold-test ต้องมี thai_gold และ source จาก GoldTraders ถ้าดึงสมาคมสำเร็จ

Environment แนะนำ:
AUTO_SIGNAL_SCAN_ENABLED=true
AUTO_SIGNAL_SCAN_ON_STARTUP=true
AUTO_SIGNAL_SCAN_INTERVAL_SECONDS=900
AUTO_SIGNAL_SCAN_SYMBOLS=GOLD,NVDA,AAPL,TSLA,QQQ,SPY,AMD,META
ENABLE_GOLDTRADERS_FETCH=true
ENABLE_YFINANCE_FALLBACK=true
