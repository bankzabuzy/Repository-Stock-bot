IMPORTOS
IMPORTHMAC
IMPORTHASHLIB
IMPORTBASE64
IMPORTTIME
IMPORTTHREADING
IMPORTSTATISTICS
FROMDATETIMEIMPORTDATETIME,TIMEDELTA

IMPORTREQUESTS
FROMFLASKIMPORTFLASK,REQUEST,ABORT

APP=FLASK(__NAME__)

LINE_CHANNEL_ACCESS_TOKEN=OS.GETENV("LINE_CHANNEL_ACCESS_TOKEN","")
LINE_CHANNEL_SECRET=OS.GETENV("LINE_CHANNEL_SECRET","")
TWELVEDATA_API_KEY=OS.GETENV("TWELVEDATA_API_KEY","")
FINNHUB_API_KEY=OS.GETENV("FINNHUB_API_KEY","")
PORT=INT(OS.GETENV("PORT","3000"))

WATCHLIST=[
X.STRIP().UPPER()
FORXINOS.GETENV("WATCHLIST","NVDA,AAPL,TSLA,QQQ,SPY,GOLD,AOT,PTT,SCB").SPLIT(",")
IFX.STRIP()
]

ALLOWED_USERS=[
X.STRIP()
FORXINOS.GETENV("ALLOWED_USERS","").SPLIT(",")
IFX.STRIP()
]

ALERT_USER_IDS=[
X.STRIP()
FORXINOS.GETENV("ALERT_USER_IDS","").SPLIT(",")
IFX.STRIP()
]

ENABLE_AUTO_ALERTS=OS.GETENV("ENABLE_AUTO_ALERTS","TRUE").LOWER()=="TRUE"
ALERT_EVERY_MINUTES=INT(OS.GETENV("ALERT_EVERY_MINUTES","360"))
LAST_ALERTS={}

THAI_SYMBOL_MAP={
"SCB":("SCB","SET","THB"),
"AOT":("AOT","SET","THB"),
"PTT":("PTT","SET","THB"),
"CPALL":("CPALL","SET","THB"),
"KBANK":("KBANK","SET","THB"),
"BBL":("BBL","SET","THB"),
"DELTA":("DELTA","SET","THB"),
"ADVANC":("ADVANC","SET","THB"),
"TRUE":("TRUE","SET","THB"),
"BDMS":("BDMS","SET","THB"),
"MINT":("MINT","SET","THB"),
"PTTEP":("PTTEP","SET","THB"),
"GULF":("GULF","SET","THB"),
"CPAXT":("CPAXT","SET","THB"),
"BEM":("BEM","SET","THB"),
"KTB":("KTB","SET","THB"),
"KTC":("KTC","SET","THB"),
"OR":("OR","SET","THB"),
}

GOLD_WORDS={"GOLD","ทอง","ทองคำ","XAUUSD","XAU/USD"}
US_INDEX_SYMBOLS={
"SPX":"SPY",
"NASDAQ":"QQQ",
"NDX":"QQQ",
"DOW":"DIA",
"RUSSELL":"IWM",
}


DEFNOW_TEXT():
RETURN(DATETIME.UTCNOW()+TIMEDELTA(HOURS=7)).STRFTIME("%D/%M/%Y%H:%M")


DEFSAFE_FLOAT(VALUE,DEFAULT=NONE):
TRY:
RETURNFLOAT(VALUE)
EXCEPTEXCEPTION:
RETURNDEFAULT


DEFFMT_NUM(VALUE,DECIMALS=2):
IFVALUEISNONE:
RETURN"N/A"
TRY:
RETURNF"{FLOAT(VALUE):,.{DECIMALS}F}"
EXCEPTEXCEPTION:
RETURN"N/A"


DEFNORMALIZE_ASSET(USER_TEXT):
RAW=USER_TEXT.STRIP()
KEY=RAW.UPPER().REPLACE("","")

IFRAWINGOLD_WORDSORKEYINGOLD_WORDS:
RETURN{
"DISPLAY":"ทองคำ/XAUUSD",
"SYMBOL":"XAU/USD",
"EXCHANGE":NONE,
"CURRENCY":"USD",
"ASSET_TYPE":"GOLD",
"NEWS_SYMBOL":"XAU",
}

IFKEYINUS_INDEX_SYMBOLS:
KEY=US_INDEX_SYMBOLS[KEY]

IFKEY.ENDSWITH(".BK"):
KEY=KEY.REPLACE(".BK","")

IFKEY.ENDSWITH(".SET"):
KEY=KEY.REPLACE(".SET","")

IFKEYINTHAI_SYMBOL_MAP:
SYMBOL,EXCHANGE,CURRENCY=THAI_SYMBOL_MAP[KEY]
RETURN{
"DISPLAY":F"{SYMBOL}.SET",
"SYMBOL":SYMBOL,
"EXCHANGE":EXCHANGE,
"CURRENCY":CURRENCY,
"ASSET_TYPE":"THAI_STOCK",
"NEWS_SYMBOL":SYMBOL,
}

RETURN{
"DISPLAY":KEY,
"SYMBOL":KEY,
"EXCHANGE":NONE,
"CURRENCY":"USD",
"ASSET_TYPE":"US_STOCK",
"NEWS_SYMBOL":KEY,
}


DEFTD_PARAMS(ASSET,INTERVAL=NONE,OUTPUTSIZE=NONE):
PARAMS={
"SYMBOL":ASSET["SYMBOL"],
"APIKEY":TWELVEDATA_API_KEY,
}

IFINTERVAL:
PARAMS["INTERVAL"]=INTERVAL

IFOUTPUTSIZE:
PARAMS["OUTPUTSIZE"]=OUTPUTSIZE

IFASSET["ASSET_TYPE"]=="THAI_STOCK":
PARAMS["EXCHANGE"]="SET"
ELIFASSET.GET("EXCHANGE"):
PARAMS["EXCHANGE"]=ASSET["EXCHANGE"]

RETURNPARAMS
def td_get_quote(asset):
    if not TWELVEDATA_API_KEY:
        raise RuntimeError("ยังไม่ได้ตั้งค่า TWELVEDATA_API_KEY")

    url = "https://api.twelvedata.com/quote"
    r = requests.get(url, params=td_params(asset), timeout=20)
    data = r.json()

    if data.get("status") == "error" or "close" not in data:
        msg = data.get("message", "")
        raise RuntimeError(
            f"ไม่พบข้อมูลจาก Twelve Data สำหรับ {asset['display']}\n"
            f"สาเหตุที่เป็นไปได้: symbol ไม่รองรับ / API package ไม่ครอบคลุม / ตลาดปิด / key ผิด\n"
            f"รายละเอียด: {msg}"
        )

    return data


def td_get_series(asset, interval="15min", outputsize=160):
    url = "https://api.twelvedata.com/time_series"
    r = requests.get(
        url,
        params=td_params(asset, interval=interval, outputsize=outputsize),
        timeout=20,
    )
    data = r.json()

    if data.get("status") == "error" or "values" not in data:
        return [], [], [], [], []

    values = list(reversed(data["values"]))
    closes, highs, lows, opens, volumes = [], [], [], [], []

    for v in values:
        close = safe_float(v.get("close"))
        high = safe_float(v.get("high"))
        low = safe_float(v.get("low"))
        open_ = safe_float(v.get("open"))
        volume = safe_float(v.get("volume"), 0)

        if close is not None and high is not None and low is not None and open_ is not None:
            closes.append(close)
            highs.append(high)
            lows.append(low)
            opens.append(open_)
            volumes.append(volume or 0)

    return closes, highs, lows, opens, volumes


def sma(values, period):
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema(values, period):
    if len(values) < period:
        return None

    k = 2 / (period + 1)
    result = values[0]

    for price in values[1:]:
        result = price * k + result * (1 - k)

    return result


def calc_rsi(values, period=14):
    if len(values) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(-period, 0):
        diff = values[i] - values[i - 1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_atr(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return None

    true_ranges = []

    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return None

    return sum(true_ranges[-period:]) / period


def analyze_signal(asset, quote, closes, highs, lows, opens, volumes):
    price = safe_float(quote.get("close"))
    previous_close = safe_float(quote.get("previous_close"))
    change = safe_float(quote.get("change"))
    percent_change = safe_float(quote.get("percent_change"))

    ema6 = ema(closes, 6)
    ema12 = ema(closes, 12)
    ema50 = ema(closes, 50)
    rsi = calc_rsi(closes)
    atr = calc_atr(highs, lows, closes)

    score = 50
    reasons = []

    if price and ema6 and ema12:
        if price > ema6 > ema12:
            score += 15
            reasons.append("ราคาอยู่เหนือ EMA6 และ EMA12")
        elif price < ema6 < ema12:
            score -= 15
            reasons.append("ราคาอยู่ใต้ EMA6 และ EMA12")

    if ema12 and ema50:
        if ema12 > ema50:
            score += 10
            reasons.append("แนวโน้มกลางยังเป็นบวก")
        elif ema12 < ema50:
            score -= 10
            reasons.append("แนวโน้มกลางยังเป็นลบ")

    if rsi is not None:
        if rsi >= 70:
            score -= 8
            reasons.append("RSI สูง ระวังพักตัว")
        elif rsi <= 30:
            score += 8
            reasons.append("RSI ต่ำ มีโอกาสรีบาวด์")
        elif 45 <= rsi <= 60:
            score += 5
            reasons.append("RSI อยู่ในโซนสมดุล")

    if percent_change is not None:
        if percent_change > 1:
            score += 8
            reasons.append("โมเมนตัมวันล่าสุดเป็นบวก")
        elif percent_change < -1:
            score -= 8
            reasons.append("โมเมนตัมวันล่าสุดเป็นลบ")

    score = max(0, min(100, score))

    if score >= 70:
        bias = "BULLISH / ฝั่งซื้อได้เปรียบ"
    elif score <= 40:
        bias = "BEARISH / ฝั่งขายได้เปรียบ"
    else:
        bias = "NEUTRAL / รอดูจังหวะ"

    if price and atr:
        support = price - atr
        resistance = price + atr
        stop_loss = price - atr * 1.2
        take_profit = price + atr * 1.8
    else:
        support = resistance = stop_loss = take_profit = None

    return {
        "price": price,
        "previous_close": previous_close,
        "change": change,
        "percent_change": percent_change,
        "ema6": ema6,
        "ema12": ema12,
        "ema50": ema50,
        "rsi": rsi,
        "atr": atr,
        "score": score,
        "bias": bias,
        "support": support,
        "resistance": resistance,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "reasons": reasons,
    }


def fetch_news(asset):
    if not FINNHUB_API_KEY:
        return "ยังไม่ได้ตั้งค่า FINNHUB_API_KEY จึงยังไม่ดึงข่าว", 0

    if asset["asset_type"] == "THAI_STOCK":
        return "ข่าวหุ้นไทยยังไม่ได้เชื่อม API ข่าวเฉพาะ SET", 0

    if asset["asset_type"] == "GOLD":
        return "ทองคำควรดูร่วมกับ USD, Bond Yield, เงินเฟ้อ, FED และดอลลาร์สหรัฐ", 0

    try:
        today = datetime.utcnow().date()
        week_ago = today - timedelta(days=7)

        url = "https://finnhub.io/api/v1/company-news"
        r = requests.get(
            url,
            params={
                "symbol": asset["news_symbol"],
                "from": week_ago.isoformat(),
                "to": today.isoformat(),
                "token": FINNHUB_API_KEY,
            },
            timeout=20,
        )

        items = r.json()
        if not isinstance(items, list) or not items:
            return "ไม่พบข่าวล่าสุดจาก Finnhub", 0

        headlines = []
        for item in items[:3]:
            headline = item.get("headline")
            if headline:
                headlines.append(f"- {headline}")

        return "\n".join(headlines) if headlines else "ไม่มีหัวข้อข่าวสำคัญ", len(headlines)

    except Exception as e:
        return f"ดึงข่าวไม่สำเร็จ: {e}", 0


def build_asset_report(user_text):
    asset = normalize_asset(user_text)
    quote = td_get_quote(asset)
    closes, highs, lows, opens, volumes = td_get_series(asset)
    analysis = analyze_signal(asset, quote, closes, highs, lows, opens, volumes)
    news_text, news_count = fetch_news(asset)

    currency = asset["currency"]
    price_label = "$" if currency == "USD" else "฿"

    reasons = analysis["reasons"][:5]
    if not reasons:
        reasons = ["ข้อมูลเทคนิคยังไม่พอ ให้ดูเป็นข้อมูลราคาเบื้องต้น"]

    text = f"""📊 วิเคราะห์ {asset['display']}
เวลาไทย: {now_text()}

ราคา: {price_label}{fmt_num(analysis['price'])}
เปลี่ยนแปลง: {fmt_num(analysis['change'])} ({fmt_num(analysis['percent_change'])}%)

AI Score: {analysis['score']}/100
มุมมอง: {analysis['bias']}

📈 Technical
EMA6: {fmt_num(analysis['ema6'])}
EMA12: {fmt_num(analysis['ema12'])}
EMA50: {fmt_num(analysis['ema50'])}
RSI14: {fmt_num(analysis['rsi'])}
ATR14: {fmt_num(analysis['atr'])}

🎯 โซนราคา
แนวรับประมาณ: {price_label}{fmt_num(analysis['support'])}
แนวต้านประมาณ: {price_label}{fmt_num(analysis['resistance'])}
Stop loss เชิงระบบ: {price_label}{fmt_num(analysis['stop_loss'])}
Take profit เชิงระบบ: {price_label}{fmt_num(analysis['take_profit'])}

เหตุผลหลัก:
{chr(10).join("- " + r for r in reasons)}

📰 ข่าว/บริบท:
{news_text}

หมายเหตุ: ไม่ใช่คำแนะนำการลงทุน ใช้เพื่อช่วยคัดกรองเท่านั้น"""
    return text
def line_reply(reply_token, text):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("LINE_CHANNEL_ACCESS_TOKEN is missing")
        return

    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text[:4900]}],
    }

    requests.post(url, headers=headers, json=payload, timeout=20)


def line_push(user_id, text):
    if not LINE_CHANNEL_ACCESS_TOKEN or not user_id:
        return

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": text[:4900]}],
    }

    requests.post(url, headers=headers, json=payload, timeout=20)


def verify_line_signature(body, signature):
    if not LINE_CHANNEL_SECRET:
        return True

    digest = hmac.new(
        LINE_CHANNEL_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()

    valid_signature = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(valid_signature, signature or "")


def help_text():
    return """พิมพ์ชื่อสินทรัพย์ที่ต้องการวิเคราะห์ เช่น

NVDA
AAPL
TSLA
QQQ
SPY
SCB
AOT
PTT
ทองคำ
GOLD

คำสั่งพิเศษ:
watchlist = ดูรายการเฝ้าดู
help = วิธีใช้งาน"""


def handle_message(user_id, text):
    clean = text.strip()

    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return "User นี้ยังไม่ได้รับอนุญาตให้ใช้งานระบบ"

    lower = clean.lower()

    if lower in {"help", "วิธีใช้", "เมนู"}:
        return help_text()

    if lower == "watchlist":
        return "รายการเฝ้าดู:\n" + "\n".join(f"- {x}" for x in WATCHLIST)

    try:
        return build_asset_report(clean)
    except Exception as e:
        return (
            "ระบบยังอ่านคำสั่งนี้ไม่ได้ครับ\n"
            "ลองพิมพ์ เช่น NVDA, AAPL, SCB, AOT, ทองคำ, GOLD\n\n"
            f"Error: {e}"
        )


@app.route("/", methods=["GET"])
def home():
    return {
        "status": "ok",
        "service": "AI Market LINE Bot",
        "time_th": now_text(),
        "watchlist": WATCHLIST,
    }


@app.route("/health", methods=["GET"])
def health():
    return "OK", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_data()
    signature = request.headers.get("X-Line-Signature", "")

    if not verify_line_signature(body, signature):
        abort(400)

    payload = request.get_json(silent=True) or {}

    for event in payload.get("events", []):
        event_type = event.get("type")
        reply_token = event.get("replyToken")
        source = event.get("source", {})
        user_id = source.get("userId", "")

        if event_type != "message":
            continue

        message = event.get("message", {})
        if message.get("type") != "text":
            line_reply(reply_token, "ตอนนี้รองรับเฉพาะข้อความเท่านั้นครับ")
            continue

        user_text = message.get("text", "")
        response_text = handle_message(user_id, user_text)
        line_reply(reply_token, response_text)

    return "OK", 200


def auto_alert_loop():
    while True:
        try:
            if ENABLE_AUTO_ALERTS and ALERT_USER_IDS:
                for symbol in WATCHLIST:
                    try:
                        report = build_asset_report(symbol)
                        header = f"🔔 Auto Alert: {symbol}\n\n"
                        for user_id in ALERT_USER_IDS:
                            line_push(user_id, header + report)
                        time.sleep(3)
                    except Exception as e:
                        print(f"Auto alert error for {symbol}: {e}")

            time.sleep(ALERT_EVERY_MINUTES * 60)

        except Exception as e:
            print(f"Auto alert loop error: {e}")
            time.sleep(60)


if __name__ == "__main__":
    if ENABLE_AUTO_ALERTS and ALERT_USER_IDS:
        t = threading.Thread(target=auto_alert_loop, daemon=True)
        t.start()

    app.run(host="0.0.0.0", port=PORT)
