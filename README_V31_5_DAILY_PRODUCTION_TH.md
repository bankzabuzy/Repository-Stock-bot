# V31.5 Daily Production Patch

ปรับระบบสำหรับใช้งานจริงทุกวัน:

- Yahoo Finance เป็นแหล่งข้อมูลหลักสำหรับหุ้น US/ETF และหุ้นไทย .BK
- TwelveData ใช้เป็น Backup เท่านั้น ลดปัญหา API credits หมดรายนาที
- Finnhub ใช้สำหรับข่าว/บริบท เมื่อใส่ FINNHUB_API_KEY ใน Railway Variables
- Auto Scan ค่าเริ่มต้นทุก 15 นาที: AUTO_SIGNAL_SCAN_INTERVAL_SECONDS=900
- Auto Scan ค่าเริ่มต้นไม่สแกนหุ้นไทย: AUTO_SCAN_INCLUDE_THAI=false
- รายชื่อ Auto Scan ค่าเริ่มต้น: GOLD,NVDA,AAPL,TSLA,QQQ,SPY,AMD,META

Railway Variables ที่แนะนำ:

FINNHUB_API_KEY=<key จริงจาก Finnhub>
AUTO_SIGNAL_SCAN_INTERVAL_SECONDS=900
AUTO_SCAN_INCLUDE_THAI=false
USE_YAHOO_FIRST=true
USE_TWELVEDATA_BACKUP=true

ทดสอบหลัง Deploy:
/status
/scan-now
/dashboard
/api/signals
/analyze/NVDA
/analyze/SCB.BK
/gold-test
