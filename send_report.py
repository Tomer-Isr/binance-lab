"""binance-lab: собирает свежий разбор из таблицы вердиктов и шлёт в Telegram.
Запуск после analysis.py (который кладёт свежий снимок в verdicts).
env: DATABASE_URL, TG_TOKEN, TG_CHAT

🔇 РАССЫЛКА ОТКЛЮЧЕНА 2026-08-03 по просьбе Томера: ежедневный отчёт приходил,
но не читался («не вникаю, просто смахиваю») — а непрочитанное уведомление хуже,
чем никакого: оно тренирует смахивать всё подряд, включая важное.
Данные и разбор при этом продолжают копиться (analysis.py + outcomes.py),
таблица `verdicts` растёт — вернуть рассылку = снять флаг ниже.
"""
import os, json, urllib.request, urllib.parse
import sys

import psycopg2

SEND_TELEGRAM = os.environ.get("SEND_TELEGRAM") == "1"
if not SEND_TELEGRAM:
    print("🔇 рассылка в Telegram отключена (SEND_TELEGRAM≠1) — данные уже собраны")
    sys.exit(0)

import palantir_signal
palantir_signal.install_excepthook(component="send_report")

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
# накопленная обратная связь (её собирает outcomes.py): что было ПОСЛЕ сигнала.
# Показываем только ярлыки, по которым уже есть хоть какая-то выборка.
cur.execute("SELECT label, count(*), avg(fwd7) FROM verdicts WHERE fwd7 IS NOT NULL "
            "GROUP BY label HAVING count(*) >= 10 ORDER BY avg(fwd7) DESC")
outcomes = cur.fetchall()
cur.execute("SELECT count(*), avg(fwd7) FROM verdicts WHERE fwd7 IS NOT NULL")
bench_n, bench_avg = cur.fetchone()
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
    if outcomes:
        lines.append("")
        lines.append("<b>Что было после сигнала</b> — среднее изменение за 7 дней:")
        for label, n, avg7 in outcomes:
            lines.append(f"  {label} — {avg7:+.1f}% <i>(n={n})</i>")
        lines.append(f"  <i>любой день без разбора — {bench_avg:+.1f}% (n={bench_n})</i>")
        lines.append("<i>Ярлык чего-то стоит, только если устойчиво лучше последней строки.</i>")
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
