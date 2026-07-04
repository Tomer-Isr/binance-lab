"""binance-lab: собирает свежий разбор из таблицы вердиктов и шлёт в Telegram.
Запуск после analysis.py (который кладёт свежий снимок в verdicts).
env: DATABASE_URL, TG_TOKEN, TG_CHAT
"""
import os, json, urllib.request, urllib.parse
import psycopg2

DB = os.environ["DATABASE_URL"]
TOKEN = os.environ["TG_TOKEN"]
CHAT = os.environ["TG_CHAT"]

conn = psycopg2.connect(DB); cur = conn.cursor()
# последний снимок + вчерашний label для показа динамики
cur.execute("SELECT max(snapshot_date) FROM verdicts")
last = cur.fetchone()[0]
cur.execute(
    "SELECT symbol,price,ch7,ch30,rsi,label,notes FROM verdicts "
    "WHERE snapshot_date=%s ORDER BY ch7 DESC", (last,))
rows = cur.fetchall()

# вчерашние ярлыки (если есть) для стрелок динамики
cur.execute("SELECT symbol,label FROM verdicts WHERE snapshot_date=%s - INTERVAL '1 day'", (last,))
prev = {s: l for s, l in cur.fetchall()}
# день N наблюдений — сколько дней уже копится история
cur.execute("SELECT count(DISTINCT snapshot_date) FROM verdicts")
day_n = cur.fetchone()[0]
conn.close()

lines = [f"📊 <b>Разбор рынка</b> — {last} · день {day_n} наблюдений",
         "<i>пары к USDT, сортировка по недельному импульсу</i>", ""]
for symbol, price, ch7, ch30, rsi, label, notes in rows:
    coin = symbol.replace("USDT", "")
    changed = ""
    if coin + "USDT" in prev and prev[coin + "USDT"] != label:
        changed = "  🔄 <i>изменилось со вчера</i>"
    lines.append(f"<b>{coin}</b> — {label}{changed}")
    lines.append(f"  ${price:,.2f} · неделя {ch7:+.1f}% · месяц {ch30:+.1f}% · RSI {rsi:.0f}")
    if notes and notes != "—":
        lines.append(f"  <i>{notes}</i>")
    lines.append("")
# раз в неделю — итог и напоминание, чтобы проект не забывался
if day_n and day_n % 7 == 0 and rows:
    best, worst = rows[0], rows[-1]
    lines.append(f"📅 <b>Итог недели (день {day_n})</b>")
    lines.append(f"Сильнейший — {best[0].replace('USDT','')} ({best[2]:+.1f}% за 7д), "
                 f"слабейший — {worst[0].replace('USDT','')} ({worst[2]:+.1f}%).")
    lines.append("Хочешь перейти к следующему этапу (виртуальная торговля на бумаге) — "
                 "открой Claude Code и скажи: «продолжим binance-lab».")
    lines.append("")
lines.append("<i>Это описание состояния рынка, не гарантия. Реальными деньгами пока не торгуем.</i>")
msg = "\n".join(lines)

data = urllib.parse.urlencode({
    "chat_id": CHAT, "text": msg, "parse_mode": "HTML", "disable_web_page_preview": "true"
}).encode()
req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=data)
r = json.load(urllib.request.urlopen(req, timeout=20))
print("✅ отправлено в Telegram" if r.get("ok") else "❌ ошибка: " + json.dumps(r, ensure_ascii=False))
