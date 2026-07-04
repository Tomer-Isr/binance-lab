"""binance-lab: ежедневный разбор рынка из базы (без торговли).
Читает свечи из Postgres, считает тренд/импульс/волатильность/RSI по каждой паре,
выдаёт человекочитаемый вердикт: где импульс на покупку, где на осторожность.
Это ОПИСАНИЕ состояния рынка, НЕ предсказание и НЕ гарантия.
"""
import os, statistics, datetime
import psycopg2

DB = os.environ["DATABASE_URL"]
PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]

# Таблица снимков вердиктов — один снимок в день на пару (для динамики "как менялись сигналы")
DDL_VERDICTS = """
CREATE TABLE IF NOT EXISTS verdicts (
  snapshot_date DATE NOT NULL,
  symbol TEXT NOT NULL,
  price DOUBLE PRECISION,
  ch24 DOUBLE PRECISION, ch7 DOUBLE PRECISION, ch30 DOUBLE PRECISION,
  rsi DOUBLE PRECISION, pos DOUBLE PRECISION, vol DOUBLE PRECISION,
  trend TEXT, label TEXT, notes TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (snapshot_date, symbol)
);
"""

def sma(v, n):
    return sum(v[-n:]) / n if len(v) >= n else None

def rsi(closes, n=14):
    if len(closes) < n + 1:
        return None
    deltas = [closes[i+1] - closes[i] for i in range(len(closes)-1)][-n:]
    gains = sum(d for d in deltas if d > 0) / n
    losses = -sum(d for d in deltas if d < 0) / n
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100 - 100 / (1 + rs)

def verdict(price, s7, s30, r, pos, ch7):
    # тренд по средним
    if price > s7 > s30:
        trend = "растёт ↑"
    elif price < s7 < s30:
        trend = "падает ↓"
    else:
        trend = "боковик →"
    notes = []
    if r is not None and r >= 70:
        notes.append("перекуплен (RSI≥70) — рискованно догонять")
    elif r is not None and r <= 30:
        notes.append("перепродан (RSI≤30) — возможен отскок")
    if pos is not None and pos >= 85:
        notes.append("у верха 30-дн диапазона")
    elif pos is not None and pos <= 15:
        notes.append("у дна 30-дн диапазона")
    # грубый ярлык
    if trend == "растёт ↑" and (r is None or r < 70):
        label = "🟢 импульс вверх, не перегрет"
    elif trend == "растёт ↑":
        label = "🟡 растёт, но перегрет"
    elif trend == "падает ↓" and (r is not None and r <= 30):
        label = "🟡 падает, но перепродан"
    elif trend == "падает ↓":
        label = "🔴 нисходящий тренд"
    else:
        label = "⚪ без чёткого направления"
    return trend, label, "; ".join(notes) if notes else "—"

conn = psycopg2.connect(DB); cur = conn.cursor()
cur.execute(DDL_VERDICTS); conn.commit()
print("=" * 78)
print("РАЗБОР РЫНКА — состояние пар к USDT (данные из нашей базы)")
print("=" * 78)
results = []
for sym in PAIRS:
    cur.execute("SELECT c FROM candles WHERE symbol=%s AND tf='1h' ORDER BY open_time", (sym,))
    h = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT c FROM candles WHERE symbol=%s AND tf='1d' ORDER BY open_time", (sym,))
    d = [r[0] for r in cur.fetchall()]
    if not h or len(d) < 31:
        continue
    price = h[-1]
    ch24 = (h[-1]/h[-25]-1)*100 if len(h) >= 25 else 0
    ch7 = (d[-1]/d[-8]-1)*100
    ch30 = (d[-1]/d[-31]-1)*100
    s7, s30 = sma(d, 7), sma(d, 30)
    rets = [(d[i+1]/d[i]-1) for i in range(len(d)-1)][-30:]
    vol = statistics.pstdev(rets)*100
    r = rsi(d, 14)
    lo, hi = min(d[-30:]), max(d[-30:])
    pos = (price-lo)/(hi-lo)*100 if hi > lo else 50
    tr, label, notes = verdict(price, s7, s30, r, pos, ch7)
    coin = sym.replace("USDT", "")
    results.append((coin, price, ch24, ch7, ch30, vol, r, pos, tr, label, notes))

# сортируем по 7-дн импульсу (кто сильнее растёт — выше)
results.sort(key=lambda x: x[3], reverse=True)
for coin, price, ch24, ch7, ch30, vol, r, pos, tr, label, notes in results:
    print(f"\n### {coin}/USDT — {label}")
    print(f"  Цена: ${price:,.2f}")
    print(f"  Изменение:  сутки {ch24:+.1f}%  |  неделя {ch7:+.1f}%  |  месяц {ch30:+.1f}%")
    print(f"  Тренд: {tr}   RSI(день): {r:.0f}   Положение в мес. диапазоне: {pos:.0f}%")
    print(f"  Волатильность (дневная): {vol:.1f}%")
    print(f"  Заметки: {notes}")

print("\n" + "=" * 78)
print("КРАТКИЙ ИТОГ (по 7-дн импульсу, сверху — сильнее)")
for coin, *_, label, _ in results:
    print(f"  {coin:5} — {label}")
print("=" * 78)

# сохраняем снимок вердиктов на сегодня (один на пару в день; повторный запуск обновляет)
today = datetime.date.today()
for coin, price, ch24, ch7, ch30, vol, r, pos, tr, label, notes in results:
    cur.execute(
        """INSERT INTO verdicts
           (snapshot_date,symbol,price,ch24,ch7,ch30,rsi,pos,vol,trend,label,notes)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (snapshot_date,symbol) DO UPDATE SET
             price=EXCLUDED.price, ch24=EXCLUDED.ch24, ch7=EXCLUDED.ch7, ch30=EXCLUDED.ch30,
             rsi=EXCLUDED.rsi, pos=EXCLUDED.pos, vol=EXCLUDED.vol, trend=EXCLUDED.trend,
             label=EXCLUDED.label, notes=EXCLUDED.notes, created_at=now()""",
        (today, coin + "USDT", price, ch24, ch7, ch30, r, pos, vol, tr, label, notes))
conn.commit()
print(f"\n💾 Снимок вердиктов сохранён в базу за {today} ({len(results)} пар).")
conn.close()
