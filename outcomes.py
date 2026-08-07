"""binance-lab: обратная связь по вердиктам — что цена сделала ПОСЛЕ сигнала.

Каждый снимок в `verdicts` дозаполняется фактом: изменение цены через 1, 3 и 7 дней
после того, как ярлык был выставлен. Запускается после analysis.py — заполняет всё,
что уже «дозрело» (прошло N дней и в базе есть свечи).

Смысл: без этого ярлыки 🟢/🔴 никто никогда не проверит. Накопится 2-3 месяца —
станет видно, отличается ли «импульс вверх» от «просто держать», или это украшение.
"""
import os, datetime, statistics, collections

import db
import palantir_signal
palantir_signal.install_excepthook(component="outcomes")

DB = os.environ["DATABASE_URL"]
HORIZONS = (1, 3, 7)          # дней после снимка
TOLERANCE_H = 6               # насколько свежей должна быть найденная свеча

DDL = """
ALTER TABLE verdicts ADD COLUMN IF NOT EXISTS fwd1 DOUBLE PRECISION;
ALTER TABLE verdicts ADD COLUMN IF NOT EXISTS fwd3 DOUBLE PRECISION;
ALTER TABLE verdicts ADD COLUMN IF NOT EXISTS fwd7 DOUBLE PRECISION;
"""


def price_at(cur, symbol, moment):
    """Цена по часовым свечам на указанный момент. None — если свечей ещё/уже нет."""
    target = int(moment.timestamp() * 1000)
    cur.execute(
        "SELECT open_time, c FROM candles WHERE symbol=%s AND tf='1h' AND open_time<=%s "
        "ORDER BY open_time DESC LIMIT 1", (symbol, target))
    row = cur.fetchone()
    if not row:
        return None
    # свеча старше допуска = в базе просто нет данных на этот момент (дырка или
    # снимок уехал за пределы 60-дневного окна часовых свечей)
    if target - row[0] > TOLERANCE_H * 3600 * 1000:
        return None
    return row[1]


conn = db.connect(DB)
cur = conn.cursor()
cur.execute(DDL)
conn.commit()

cur.execute("SELECT snapshot_date, symbol, price, created_at FROM verdicts "
            "WHERE fwd1 IS NULL OR fwd3 IS NULL OR fwd7 IS NULL "
            "ORDER BY snapshot_date, symbol")
pending = cur.fetchall()

filled = 0
for snap_date, symbol, price, created_at in pending:
    updates = {}
    for k in HORIZONS:
        later = price_at(cur, symbol, created_at + datetime.timedelta(days=k))
        if later is not None and price:
            updates[f"fwd{k}"] = (later / price - 1) * 100
    if not updates:
        continue
    sets = ", ".join(f"{col}=%s" for col in updates)
    cur.execute(f"UPDATE verdicts SET {sets} WHERE snapshot_date=%s AND symbol=%s",
                (*updates.values(), snap_date, symbol))
    filled += len(updates)
conn.commit()
print(f"📌 Обратная связь: дозаполнено {filled} значений по {len(pending)} незакрытым вердиктам.")

# накопленная сводка: отличается ли ярлык от «просто держать»
cur.execute("SELECT label, fwd1, fwd3, fwd7 FROM verdicts WHERE fwd7 IS NOT NULL")
rows = cur.fetchall()
if rows:
    by_label = collections.defaultdict(list)
    for label, f1, f3, f7 in rows:
        by_label[label].append((f1, f3, f7))

    def avg(vals, idx):
        got = [v[idx] for v in vals if v[idx] is not None]
        return statistics.mean(got) if got else 0.0

    print(f"\n📈 Как отрабатывали ярлыки (снимков с известным результатом: {len(rows)})")
    print(f"{'ярлык':<34} {'N':>4} {'+1д':>8} {'+3д':>8} {'+7д':>8}")
    for label in sorted(by_label, key=lambda x: -avg(by_label[x], 2)):
        v = by_label[label]
        print(f"{label:<34} {len(v):>4} {avg(v,0):>+7.2f}% {avg(v,1):>+7.2f}% {avg(v,2):>+7.2f}%")
    allv = [x for v in by_label.values() for x in v]
    print(f"{'— все снимки (бенчмарк)':<34} {len(allv):>4} "
          f"{avg(allv,0):>+7.2f}% {avg(allv,1):>+7.2f}% {avg(allv,2):>+7.2f}%")
    print("\nЯрлык имеет смысл только если он заметно и устойчиво лучше строки-бенчмарка.")
conn.close()
