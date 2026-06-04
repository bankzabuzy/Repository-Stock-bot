# V31 Alpha Research & Performance Attribution Core

เวอร์ชันนี้ต่อจาก V30 โดยไม่ตัดฟีเจอร์เดิม จุดประสงค์คือพิสูจน์ว่า Signal Component ไหนสร้างกำไรจริง และควรให้น้ำหนักเท่าไร ก่อนนำไปใช้เงินจริงหรือใช้ระดับกองทุน

## สิ่งที่เพิ่มใน V31

1. **Signal Component Attribution Engine**
   - เก็บ component ของแต่ละสัญญาณ เช่น confidence, EMA trend, volume, RSI, reward/risk, data quality
   - ผูก component กับผลลัพธ์จริงเป็น R-multiple
   - คำนวณค่าเฉลี่ยผลตอบแทน, hit rate, correlation, alpha score

2. **Adaptive Component Weight Recommendation**
   - สรุปว่าน้ำหนักควรไปอยู่ที่ component ไหน
   - component ที่ไม่มี alpha จะถูกลดน้ำหนักหรือให้เป็น 0

3. **Monte Carlo Risk Engine**
   - ใช้ return_r จริงมาสุ่มลำดับผลลัพธ์
   - ประเมิน expected return, p05/p95, worst drawdown, risk of ruin

4. **Regime Attribution**
   - แยกผลลัพธ์ตาม regime เช่น BULL, BEAR, HIGH_VOL, SIDEWAY
   - ใช้ดูว่า strategy ทำเงินในตลาดแบบไหน และควรปิดในตลาดแบบไหน

5. **Portfolio Candidate Optimizer**
   - เลือก signal ที่ดีที่สุดจากหลายตัว
   - จำกัดการกระจุกตัวในกลุ่มเดียวกัน เช่น SEMIS, MEGA_TECH

6. **V31 Alpha Gate**
   - เพิ่ม gate เข้า `should_send_alert_final()` แบบ observe เป็นค่าเริ่มต้น
   - ถ้าต้องการให้ block สัญญาณจริง ให้ตั้ง `V31_ALPHA_GATE_MODE=block`

## Routes หลัก

- `/v31/health`
- `/v31/sync-v28`
- `/v31/components/record`
- `/v31/attribution`
- `/v31/weights`
- `/v31/monte-carlo`
- `/v31/regime-attribution`
- `/v31/optimizer`
- `/v31/alpha-gate`
- `/v31/dashboard`
- `/v31/dashboard.json`
- `/v31/table/v31_signal_components`
- `/v31/table/v31_weight_recommendations`
- `/v31/table/v31_monte_carlo_runs`

## Environment Variables ใหม่

```env
V31_MIN_OBSERVATIONS=10
V31_WEIGHT_LOOKBACK=500
V31_MONTE_CARLO_RUNS=5000
V31_MONTE_CARLO_TRADES=100
V31_RISK_OF_RUIN_DD_R=-10.0
V31_MAX_SAME_GROUP=2
V31_MIN_ALPHA_SCORE=0.0
V31_ALPHA_GATE_MODE=observe
```

## วิธีใช้งานจริงที่แนะนำ

### 1. Sync ผลลัพธ์เดิมจาก V28

```bash
curl -H "X-API-Key: YOUR_KEY" "https://YOUR_APP/v31/sync-v28?limit=1000"
```

### 2. คำนวณ attribution

```bash
curl -H "X-API-Key: YOUR_KEY" "https://YOUR_APP/v31/attribution?lookback=500&min_observations=10"
```

### 3. คำนวณน้ำหนักใหม่

```bash
curl -H "X-API-Key: YOUR_KEY" "https://YOUR_APP/v31/weights?lookback=500&min_observations=10"
```

### 4. Run Monte Carlo

```bash
curl -H "X-API-Key: YOUR_KEY" "https://YOUR_APP/v31/monte-carlo?simulations=5000&trades_per_run=100&ruin_dd_r=-10"
```

### 5. เปิด Dashboard

```text
https://YOUR_APP/v31/dashboard
```

## Production Notes

- ค่าเริ่มต้นของ V31 gate เป็น `observe` เพื่อไม่ให้ระบบบล็อกสัญญาณทันทีโดยไม่มีข้อมูลพอ
- หลังมีข้อมูล outcome อย่างน้อย 100-300 trades ค่อยพิจารณา `V31_ALPHA_GATE_MODE=block`
- ถ้า attribution แจ้ง `INSUFFICIENT_DATA` ห้ามสรุปว่า component นั้นดีหรือไม่ดี ต้องเก็บ forward test เพิ่ม
- ถ้า Monte Carlo `risk_of_ruin_pct` สูงกว่า 10% ควรลด position size หรือปิด strategy นั้นก่อนใช้เงินจริง

## ตรวจสอบแล้ว

- `python -m py_compile main.py modules/*.py` ผ่าน
- `python -m unittest discover -s tests -v` ผ่าน 10 tests
- ZIP ถูก clean แล้ว ไม่รวม `__pycache__`, `.pyc`, `.db`, `.sqlite`
