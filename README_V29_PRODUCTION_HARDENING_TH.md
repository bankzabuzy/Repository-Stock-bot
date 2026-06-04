# V29 Production Hardening & Governance Core

ต่อยอดจาก V28 Fund Validation Core โดยเพิ่มชั้น production governance สำหรับใช้งานจริงให้เสถียรกว่าเดิม โดยไม่ลบฟีเจอร์เดิมของ V7-V28

## สิ่งที่เพิ่มใน V29

1. PostgreSQL Migration Layer
- รองรับ `DATABASE_URL` สำหรับ PostgreSQL
- มี `/v29/migrate` สำหรับ migrate ข้อมูล V28 จาก SQLite ไป PostgreSQL แบบ best-effort
- ถ้าไม่มี `DATABASE_URL` ระบบ fallback เป็น SQLite ผ่าน `DB_PATH`

2. Real Cron Scheduler
- `/v29/scheduler/run` สำหรับรัน outcome + provider health + feedback loop แบบ manual
- `/v29/scheduler/start` สำหรับเริ่ม background scheduler
- ตั้ง `V29_ENABLE_CRON=true` เพื่อให้ scheduler start ตอน boot
- ตั้ง `V29_CRON_INTERVAL_SECONDS=900` เป็นค่าเริ่มต้น 15 นาที

3. Full Test Suite
- เพิ่ม `tests/test_v29_governance.py`
- ทดสอบ kill-switch, feedback loop, scheduler, API key validation
- รันด้วยคำสั่ง:

```bash
python -m unittest tests/test_v29_governance.py -v
```

4. API Key Protection
- route ที่เปลี่ยนสถานะระบบหรือรัน scheduler/migration ต้องใช้ API key
- ใช้ header ได้ 2 แบบ:

```bash
X-API-Key: your_key
Authorization: Bearer your_key
```

- ตั้งค่า env:

```bash
V29_API_KEY=your_secure_key
V29_REQUIRE_API_KEY=true
```

5. Alert Kill-switch
- เปิดปิดได้จาก route:

```bash
/v29/kill-switch/on
/v29/kill-switch/off
```

- เมื่อเปิด kill-switch ระบบ governance gate จะ block alert ก่อนส่ง LINE

6. Drawdown Circuit Breaker
- ใช้ผลลัพธ์จาก `v28_open_signals` ที่ปิดแล้ว
- ค่า default:

```bash
V29_MAX_DRAWDOWN_R=-6.0
V29_MAX_LOSS_STREAK=4
```

- ถ้า drawdown หรือ loss streak เกินเกณฑ์ ระบบ block alert ใหม่

7. Data Provider Health Monitor
- `/v29/provider-health`
- ตรวจ yfinance และ HTTP market endpoint
- ใช้กับ governance gate ได้ผ่าน `V29_PROVIDER_GATE`

```bash
V29_PROVIDER_GATE=warn   # default
V29_PROVIDER_GATE=block  # block alert ถ้า provider health ต่ำ
V29_PROVIDER_GATE=off
```

8. Strategy Performance Feedback Loop
- `/v29/feedback`
- อ่าน closed outcomes จาก V28
- สรุป win rate, expectancy R, total R, max drawdown, loss streak
- ให้ action เช่น `LEARN_ONLY`, `NORMAL`, `REDUCE`, `REDUCE_OR_PAUSE`, `ALLOW_NORMAL_OR_SCALE`

9. V29 Dashboard
- `/v29/dashboard`
- `/v29/dashboard.json`
- แยกข้อมูล governance/compliance ออกจาก V28 signal dashboard

## Route สำคัญ

- `/v29/health`
- `/v29/dashboard`
- `/v29/dashboard.json`
- `/v29/provider-health`
- `/v29/governance-gate?symbol=SPY&sig=BUY&score=90`
- `/v29/scheduler/run`
- `/v29/scheduler/start`
- `/v29/feedback`
- `/v29/state`
- `/v29/kill-switch/on`
- `/v29/kill-switch/off`
- `/v29/migrate`
- `/v29/events`
- `/v29/scheduler-runs`

## ENV ที่แนะนำสำหรับ Production

```bash
DATABASE_URL=postgresql://...
ADMIN_TOKEN=your_admin_token
V29_API_KEY=your_admin_token
V29_REQUIRE_API_KEY=true
V29_ENABLE_CRON=true
V29_CRON_INTERVAL_SECONDS=900
V29_MAX_DAILY_ALERTS=30
V29_MAX_DAILY_SYMBOL_ALERTS=3
V29_MAX_DRAWDOWN_R=-6.0
V29_MAX_LOSS_STREAK=4
V29_PROVIDER_GATE=warn
ENABLE_AUTO_ALERTS=true
ALERT_USER_IDS=your_line_user_id
```

## หมายเหตุความจริง

V29 ทำให้ระบบแข็งแรงขึ้นระดับ production governance แต่ยังไม่ควรเรียกว่า fund execution system เต็มรูปแบบจนกว่าจะมี:
- broker/execution audit จริง
- slippage/commission model จริง
- position sizing ตาม AUM จริง
- compliance approval workflow
- monitoring ภายนอก เช่น UptimeRobot/Prometheus/Sentry
