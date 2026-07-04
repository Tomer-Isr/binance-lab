# План binance-lab

Статус на 2026-07-04: **Этапы 1 и «Анализ» работают на автомате: свечи собираются ежечасно, разбор рынка приходит в Telegram каждое утро (09:00 IL). Следующее — paper trading.**

## Этап 0 — Скелет ✅
- [x] Папка проекта, CLAUDE.md, PLAN.md
- [x] git init + первый коммит
- [x] Railway: проект `binance-lab` (917e1d80-399d-43fb-bf75-5fded3fce538) + Postgres (Online)

## Этап 1 — Collector 🔶 в процессе
- [x] Схема БД: `candles(symbol, tf, open_time, o,h,l,c, volume, close_time, fetched_at)`, PK (symbol,tf,open_time)
- [x] `collector.py`: тянет свечи с публичного Binance API, апсертит в Postgres
- [x] Первая заливка истории: 3900 свечей, 5 пар × (1h×720 + 1d×60), проверено
- [x] Автосбор через **GitHub Actions** (`.github/workflows/collect.yml`, cron `5 * * * *`), пишет в Railway Postgres. Проверено: прогон success, база обновляется. Endpoint = data-api.binance.vision (обычный api.binance.com даёт 451 с US-раннеров).
- **Критерий выполнен:** каждый час в БД свежие свечи без участия Томера ✅

## Этап 2 — Анализ (без торговли) ✅
- [x] `analysis.py`: тренд/RSI/импульс/волатильность/позиция в диапазоне по 5 парам
- [x] Снимки вердиктов в таблицу `verdicts` (динамика сигналов день к дню)
- [x] `send_report.py`: отправка отчёта в Telegram (бот @binancetomerisr_bot, ручной запуск/резерв)
- [x] Автоматизация: cron-сервис `report` на Railway (образ python:3.12, 05:00 UTC = 08:00 IL) клонирует свежий main и запускает `analysis.py` (снимок в `verdicts`) + `send_report.py` (отчёт в Telegram через @binancetomerisr_bot, chat 719222925). В отчёте: день N наблюдений, динамика «изменилось со вчера», раз в 7 дней — итог недели с напоминанием про следующий этап. Код обновляется обычным git push.
- [x] ⚠️ Облачная Claude-routine `trig_019dQ1eVZdbFyRyRkMLfELmJ` — НА ПАУЗЕ: окружение cloud-routine блокирует egress (TCP к Railway Postgres и HTTPS к api.telegram.org → 403), оба её запуска 04.07 упали. Ни один «отчёт от routine» реально не доставлялся. Вернуться, если Anthropic откроет сетевую политику. (GH Actions для нового workflow тоже не подошёл: у git-токена нет scope `workflow`)
- [ ] (позже) дашборд equity/сравнение

## Этап 2 — Paper trading
- [ ] Таблицы `paper_trades`, `paper_equity`
- [ ] Виртуальный портфель (старт условно $10 или больше — на симуляции не важно)
- [ ] Стратегии: buy&hold (бенчмарк) + SMA-cross (тренд)
- [ ] Учёт комиссии 0.1%/сторона и MIN_NOTIONAL — как в реале
- **Критерий:** через 2-3 дня виден виртуальный P&L и лог сделок

## Этап 3 — Разбор + дашборд
- [ ] Ежедневный отчёт (Claude): что двигалось, волатильность, как отработали стратегии vs бенчмарк
- [ ] Простой визуал equity-кривой
- [ ] Механизм расписания разбора (scheduled agent / вручную)
- **Критерий:** читаемый ежедневный отчёт

## Этап 4 — Развилка по реальным деньгам
- Только если Этап 2 честно в плюсе и понятно почему.
- Требует: API-ключ (Spot only, withdrawals OFF, IP whitelist), явное согласие Томера.
