# V31.2 Import-Fix Production Package

แพ็กนี้แก้ปัญหา Railway ที่ขึ้น `No module named modules` และ `cannot import name ...` จากโมดูล V26-V31 โดยจัดโครงสร้างให้ถูกต้องดังนี้:

```
Repository-Stock-bot/
├── main.py
├── requirements.txt
├── runtime.txt
├── Procfile
├── modules/
│   ├── __init__.py
│   ├── v26_adaptive_weight_engine.py
│   ├── v27_full_institutional.py
│   ├── v28_fund_validation_core.py
│   ├── v29_governance_core.py
│   ├── v30_model_validation_core.py
│   └── v31_alpha_attribution_core.py
└── tests/
```

## วิธีอัปโหลดขึ้น GitHub ที่ถูกต้อง

ให้แตก ZIP แล้วอัปโหลด/Push ทั้งโปรเจกต์ ไม่ใช่คัดลอกเฉพาะ `main.py` และไม่ใช่ลากไฟล์ใน `modules` ไปไว้ที่ root

ตำแหน่งที่ถูกต้องคือ:

- `modules/v28_fund_validation_core.py`
- `modules/v29_governance_core.py`
- `modules/v30_model_validation_core.py`
- `modules/v31_alpha_attribution_core.py`

## Railway Variables ที่แนะนำ

```env
MISE_PYTHON_GITHUB_ATTESTATIONS=false
ENABLE_AUTO_ALERTS=true
ENABLE_THAI_STOCK_ALERTS=false
ENABLE_US_STOCK_ALERTS=true
ENABLE_US_SESSION_ONLY=true
ENABLE_US_REGULAR_SESSION_ONLY=true
USE_US_EXCHANGE_TIME=true
US_ALLOW_PREMARKET_ALERTS=false
SCAN_THAI_MARKET=false
```

## ตรวจหลัง Deploy

เปิด route เหล่านี้:

- `/v28/health`
- `/v29/health`
- `/v30/health`
- `/v31/health`

ถ้าเปิดได้ แปลว่า V28-V31 โหลดสำเร็จ
