# V27.1 Integration Phase

ฐาน: ใช้ ZIP ล่าสุดที่มี V27/V26 modules เป็นฐาน และเพิ่มการเชื่อม workflow จริง

## เป้าหมาย
ให้ทุก Alert ผ่าน workflow นี้ก่อนส่ง LINE:

Data Quality
→ Capital Protection
→ Conviction Gate
→ Adaptive Weight
→ Forward Test 30 วัน
→ ส่ง LINE หรือ Block พร้อมเหตุผล

## ไฟล์ใหม่
- `modules/v27_integration_pipeline.py`
- `modules/v27_integration_routes_snippet.py`

## Route ใหม่
- `GET /v27/integration/health`
- `GET /v27/integration/pipeline` ทดสอบด้วย demo signal
- `POST /v27/integration/pipeline` ทดสอบ signal จริง

## การทำงาน
ระบบจะตรวจ:
- ข้อมูลราคา/indicator เพี้ยนหรือไม่
- วันนี้ส่ง Alert เกิน limit หรือยัง
- แพ้ติดกัน/ขาดทุนเกิน limit หรือไม่
- Breadth/VIX เสี่ยงเกินไปหรือไม่
- Conviction/Score ผ่านเกณฑ์หรือไม่
- Adaptive Score ผ่านหรือไม่
- บันทึก Forward Test record

## Patch main.py
main.py patched: integration routes registered after app creation

## หมายเหตุสำคัญ
เวอร์ชันนี้เป็น Integration Layer ให้โมดูลที่เคยเพิ่มมาเริ่มทำงานร่วมกันจริง
แต่การส่ง LINE จริงยังควรเชื่อมกับ function push/reply เดิมของโปรเจกต์คุณในจุดส่ง Alert หลัก
