# V25.4 Correlation Matrix + Theme Selection

ต่อจาก V25.3 โดยไม่ลบระบบเดิม

## เพิ่มใหม่
- Correlation Matrix: NVDA/AMD/AVGO/TSM และหุ้นธีมเดียวกัน
- Best-of-Theme Selection: เลือกส่งตัวดีที่สุดตัวเดียวในกลุ่มเดียวกัน
- Sector/Theme Exposure Cap
- Redundant Alert Suppression กันส่งหุ้นสัมพันธ์สูงซ้ำหลายตัว
- Portfolio Quality Score
- Signal Candidate Log
- Correlation Decision Log

## API
- `/v25/correlation/build?symbols=NVDA,AMD,AVGO,TSM`
- `/v25/correlation/NVDA/AMD`
- `/v25/theme-select?candidates=NVDA:91:88:A:CALL,AMD:88:82:B:CALL,AVGO:86:80:B:CALL,TSM:84:78:B:CALL`
- `/v25/alert-portfolio-gate?...`
- `/v25/correlation-matrix`
- `/v25/correlation-dashboard`

## แนวคิดทำเงินได้จริงที่เพิ่ม
ระบบไม่ส่งทุกตัวที่คะแนนดี แต่ถามก่อนว่า:
- เป็นธีมเดียวกันหรือไม่
- Correlation สูงหรือไม่
- วันนี้ถือ exposure ซ้ำเกินไปหรือไม่
- ตัวไหนมีคุณภาพสูงสุดในกลุ่ม

ตัวอย่าง: NVDA, AMD, TSM, AVGO เป็น Semiconductor เหมือนกัน ระบบจะพยายามเลือกตัวที่ดีที่สุดเพียงตัวเดียว
เพื่อลด Overtrading และลดการใช้ LINE quota
