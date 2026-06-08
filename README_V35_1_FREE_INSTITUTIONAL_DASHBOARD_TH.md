# V35.1 Free Institutional Dashboard Upgrade

เพิ่มต่อจากฐานเดิมแบบฟรี 100% สำหรับ Research / Paper Trading:

## สิ่งที่เพิ่ม
- เชื่อม V35 เข้ากับ Flask dashboard จริง: `/v35/dashboard`
- Signal Ranking: `/v35/ranking`
- Backtest แยกสินทรัพย์: `/v35/backtest`
- Forward Test watchlist: `/v35/forward-test`
- Risk Gate ก่อน BUY/SELL: `/v35/risk-gate`
- Performance Report: win rate, max drawdown, profit factor, Sharpe, return, trade count

## ตัวอย่าง URL
```text
/v35/dashboard?symbols=META,AMD,SPY,QQQ,TSLA,AAPL,NVDA,GC=F
/v35/ranking?symbols=META,AMD,SPY,QQQ,TSLA,AAPL,NVDA,GC=F
/v35/backtest?symbols=META,AMD,SPY,QQQ,TSLA,AAPL,NVDA,GC=F&period=2y
/v35/forward-test?symbols=META,AMD,SPY,QQQ,TSLA,AAPL,NVDA,GC=F
```

## สถานะการใช้งาน
ระบบนี้ยังเป็น Research / Paper Trading เท่านั้น ไม่ใช่คำสั่งซื้อขายเงินจริง และข้อมูลฟรีจาก yfinance อาจล่าช้า/ขาดช่วงได้ ต้อง Forward Test 30-90 วันก่อนใช้เงินจริง
