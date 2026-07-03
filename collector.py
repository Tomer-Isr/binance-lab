"""binance-lab: сборщик рыночных данных с Binance -> Postgres.
Один запуск = тянет последние свечи по парам и апсертит в БД.
Локально: DATABASE_URL=<public_url> python collector.py
На Railway: DATABASE_URL инжектится автоматически, запуск по cron (каждый час).
"""
import os, time, json, urllib.request
import psycopg2
from psycopg2.extras import execute_values

DB = os.environ["DATABASE_URL"]
PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
TFS = {"1h": 720, "1d": 60}          # 1h: ~30 дней истории, 1d: ~60 дней контекста
# data-api.binance.vision — публичный market-data эндпоинт Binance без гео-блокировки
# (обычный api.binance.com отдаёт HTTP 451 с US-адресов, где крутится GitHub Actions)
BASE = "https://data-api.binance.vision/api/v3/klines"

DDL = """
CREATE TABLE IF NOT EXISTS candles (
  symbol     TEXT NOT NULL,
  tf         TEXT NOT NULL,
  open_time  BIGINT NOT NULL,
  o DOUBLE PRECISION, h DOUBLE PRECISION, l DOUBLE PRECISION, c DOUBLE PRECISION,
  volume     DOUBLE PRECISION,
  close_time BIGINT,
  fetched_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (symbol, tf, open_time)
);
"""

def fetch(symbol, interval, limit):
    url = f"{BASE}?symbol={symbol}&interval={interval}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "binance-lab/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)

def main():
    conn = psycopg2.connect(DB); conn.autocommit = True
    cur = conn.cursor()
    cur.execute(DDL)
    for sym in PAIRS:
        for tf, lim in TFS.items():
            kl = fetch(sym, tf, lim)
            rows = [(sym, tf, k[0], float(k[1]), float(k[2]), float(k[3]),
                     float(k[4]), float(k[5]), k[6]) for k in kl]
            execute_values(cur,
                "INSERT INTO candles (symbol,tf,open_time,o,h,l,c,volume,close_time) VALUES %s "
                "ON CONFLICT (symbol,tf,open_time) DO UPDATE SET "
                "c=EXCLUDED.c, h=EXCLUDED.h, l=EXCLUDED.l, volume=EXCLUDED.volume, "
                "close_time=EXCLUDED.close_time, fetched_at=now()",
                rows)
            print(f"  {sym} {tf}: {len(rows)} свечей")
            time.sleep(0.25)
    cur.execute("SELECT COUNT(*) FROM candles")
    total = cur.fetchone()[0]
    cur.execute("SELECT symbol, tf, to_timestamp(MAX(open_time)/1000) FROM candles "
                "WHERE tf='1h' GROUP BY symbol, tf ORDER BY symbol")
    print(f"Всего свечей в базе: {total}")
    for s, tf, ts in cur.fetchall():
        print(f"  {s} {tf} свежайшая: {ts}")
    conn.close()

if __name__ == "__main__":
    main()
