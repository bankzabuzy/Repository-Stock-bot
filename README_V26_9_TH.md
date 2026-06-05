# V26.9 Adaptive Weight Engine

เพิ่มระบบปรับน้ำหนักคะแนนจากผลลัพธ์จริงในฐานข้อมูล แทนการใช้ค่าน้ำหนักคงที่

## Factors ที่ปรับน้ำหนัก
- RSI
- RVOL
- Option Flow
- News Sentiment
- Market Breadth
- Sector Rotation

## หลักการ
ระบบจะดูผลลัพธ์ย้อนหลัง เช่น Win Rate, Avg Return R, Drawdown R แล้วค่อยปรับน้ำหนักของแต่ละปัจจัย

ตัวอย่าง:
- ถ้า RVOL สูงแล้วชนะบ่อย → เพิ่มน้ำหนัก RVOL
- ถ้า RSI สูงแล้วโดน SL บ่อย → ลดน้ำหนัก RSI
- ถ้า Sector Rotation หนุนแล้ว Expected Return ดี → เพิ่มน้ำหนัก Sector Rotation

## ไฟล์ที่เพิ่ม
- `modules/v26_adaptive_weight_engine.py`
- `modules/v26_adaptive_weight_routes_snippet.py`

## API/Route ที่ควรเชื่อมต่อใน main.py
สามารถเชื่อมต่อภายหลัง:
- `/v26/adaptive-weights`
- `/v26/adaptive-score`
- `/v26/adaptive-learn`

## หมายเหตุ
เวอร์ชันนี้เป็น engine foundation ที่ต่อยอดจาก V26.8 โดยไม่ลบระบบเดิม
