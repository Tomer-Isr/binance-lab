# Ошибки деплоя — binance-lab

- [2026-07-12] сервис `report` (production) — Deploy Crashed (Railway). Ссылка на письмо: https://mail.google.com/mail/u/0/#inbox/19f54ec8b88950db
- [2026-07-15] сервис `report` (production) — Deploy Crashed (Railway), повторно. Ссылка на письмо: https://mail.google.com/mail/u/0/#inbox/19f645ed49c1d296
- [2026-07-18] сервис `report` (production) — Deploy Crashed (Railway), 3-й раз за неделю. Ссылка на письмо: https://mail.google.com/mail/u/0/#inbox/19f73cfd3e135ac0
- [2026-07-18] GitHub Actions `collect-candles` (main, commit 7d7d710) — Run failed, все job упали за 14 секунд. Новый тип сбоя (отдельно от Railway `report`). Ссылка на письмо: https://mail.google.com/mail/u/0/#inbox/19f76647580dd3e5
- [2026-07-21] сервис `report` (production) — Deploy Crashed (Railway), **4-й раз за 10 дней** (12/15/18/21 июля). Стоит разобраться с причиной падения, не только рестартить. Ссылка на письмо: https://mail.google.com/mail/u/0/#inbox/19f83429cb8f4d8d
- [2026-07-24] сервис `report` (production) — Deploy Crashed (Railway), **5-й раз за 12 дней** (12/15/18/21/24 июля). Паттерн устойчивый — нужен разбор причины, не рестарт. Ссылка на письмо: https://mail.google.com/mail/u/0/#inbox/19f92b6f22b2c331
- [2026-07-27] сервис `report` (production) — Deploy Crashed (Railway), **6-й раз за 15 дней** (12/15/18/21/24/27 июля). Стабильный интервал ~каждые 3 дня — похоже на систематический баг/ресурсный лимит, не случайность. Ссылка на письмо: https://mail.google.com/mail/u/0/#inbox/19fa2295040c2175
- [2026-07-29] сервис `report` (production) — Deploy Crashed (Railway), **7-й раз за 17 дней** (12/15/18/21/24/27/29 июля). Интервал в этот раз сократился до 2 дней (был ~3) — паттерн ухудшается, стоит один раз разобрать причину, а не продолжать рестартить. Ссылка на письмо: https://mail.google.com/mail/u/0/#inbox/19fac78dc050c114
- [2026-07-31] сервис `report` (production) — Deploy Crashed (Railway), **8-й раз за 19 дней** (12/15/18/21/24/27/29/31 июля). Снова интервал 2 дня — держится устойчиво. 8 подряд крашей одного сервиса за 19 дней — рестарт больше не лечит, нужен разбор логов. Ссылка на письмо: https://mail.google.com/mail/u/0/#inbox/19fb6c2f5cc88a75
- [2026-08-02] сервис `report` (production) — Deploy Crashed (Railway), **9-й раз за 21 день** (12/15/18/21/24/27/29/31 июля, 02 августа). Третий раз подряд интервал держится ровно 2 дня — это уже не флуктуация, а системный паттерн. Рестарт давно не решает проблему, стоит один раз залезть в логи. Ссылка на письмо: https://mail.google.com/mail/u/0/#inbox/19fc10fb1549dc2a

## [2026-08-02] Причина серии крашей `report` найдена и устранена

В логах последнего запуска: `01.08 06:06 ✅ отправлено в Telegram` → `02.08 06:01 fatal:
destination path '/app' already exists and is not an empty directory`.

Start command сервиса делал `git clone ... /app`, а Railway между запусками cron
переиспользует файловую систему контейнера. После удачного прогона `/app` остаётся
непустым — клон падает, контейнер выходит с ненулевым кодом, Railway пишет «Deploy
Crashed». Когда контейнер поднимается с чистой ФС — прогон проходит. Отсюда чередование
успех/краш через день-два и отчёт раз в 2-3 дня вместо ежедневного (видно по датам в
таблице `verdicts`: 04, 05, 08, 11, 14, 17, 20, 23, 26, 28, 30 июля, 01 августа).

Исправлено: клон в отдельную папку с очисткой перед ним (`rm -rf /src && git clone ... /src`).
Команда живёт в настройках сервиса на Railway, не в репозитории — правилась через API
(`serviceInstanceUpdate`), в git её нет.
