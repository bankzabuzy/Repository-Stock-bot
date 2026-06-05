# V31.7 Confidence + Thai Gold/Oil Fix

แก้ไขหลัก:
- เพิ่มความมั่นใจ (%) ให้ซื้อไม้ 1-3 และโอกาสถึงเป้าให้ TP1-TP3
- เพิ่ม Position Size Suggestion ตามความมั่นใจของไม้
- ทองไทยแสดงเฉพาะราคาสมาคมค้าทองคำ และเพิ่มแผนเข้า/ออกทองไทย 3 ไม้กลับมา
- ตัด XAUUSD/US gold technical ออกจากรายงานทองคำ
- ราคาน้ำมันเปลี่ยนเป็น Live-first: ไม่ใช้ราคาน้ำมัน hard-coded เป็นราคาปัจจุบัน
- เปิด ENABLE_THAI_OIL_FETCH เป็นค่าเริ่มต้น true
- ถ้าดึงราคาน้ำมันสดไม่ได้ ระบบจะแจ้งว่าดึงไม่สำเร็จ ไม่เดาราคาเอง
- แก้ TH_TZ ให้ fallback เป็น UTC+7 ป้องกัน name 'TH_TZ' is not defined
- เพิ่ม ETF score guard ลดคะแนนเกินจริงเมื่อ RSI สูงหรือ timeframe mixed
