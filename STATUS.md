# Статус binance-lab

## 05.10.2026 — сбор свечей выключен
- Workflow `collect-candles` (каждый час) → `disabled_manually` по решению Томера: отчёт выключен с 03.08, данные никто не смотрит. Накопленное не тронуто; вернуть — `gh workflow enable collect-candles -R Tomer-Isr/binance-lab`.
