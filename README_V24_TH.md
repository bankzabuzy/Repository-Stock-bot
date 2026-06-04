# V24 Professional Quant Platform

ต่อจากฐานเดิมโดยไม่ลบระบบหลักใน main.py

เพิ่ม:
- Walk Forward Test
- Monte Carlo Simulation
- Expectancy
- Sharpe Ratio
- Profit Factor
- Kelly Position Sizing
- Auto Portfolio Allocation
- V24 Dashboard และ API

## URL ทดสอบ
- `/v24`
- `/v24/dashboard`
- `/v24/json`
- `/v24/monte-carlo`
- `/v24/walk-forward`
- `/v24/expectancy`
- `/v24/portfolio/allocation-preview`
- `/v24/outcome/add?symbol=NVDA&strategy=VWAP&side=CALL&entry=214&tp1=216&tp2=218&sl=212&outcome=TP1&r_multiple=1.2&score=91&risk_grade=A`

## หมายเหตุ
ถ้ายังไม่มี outcome อย่างน้อย 5 รายการ Monte Carlo จะยังไม่ทำงาน และถ้ายังไม่มี 20 รายการ Walk Forward จะยังไม่ทำงาน
