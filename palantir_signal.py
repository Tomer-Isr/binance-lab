# -*- coding: utf-8 -*-
"""palantir_signal.py — отправка ошибок приложения в контур «Сигналы» Палантира.

Копируется в проект как есть (один файл, без зависимостей — только стандартная
библиотека). Эталон живёт в palantir/collectors/signal_client/.

Подключение — три строки:

    from palantir_signal import report_error, guard

    report_error("не смог получить свечи", component="collector")   # вручную
    with guard("отчёт по свечам", component="report"):              # или обёрткой
        do_work()

Переменные окружения: PALANTIR_TOKEN (обязательно), PALANTIR_PRODUCT (код
проекта), PALANTIR_URL (по умолчанию боевой домен). Без PALANTIR_TOKEN модуль
молча отключается — приложение работает как раньше.

🔑 ГЛАВНОЕ ПРАВИЛО: отправка сигнала НИКОГДА не должна ронять или тормозить
приложение. Ошибка при отправке ошибки — не повод падать. Поэтому здесь всё
обёрнуто в try/except, стоит жёсткий таймаут, а отправка идёт в фоновом потоке.
"""
import atexit
import hashlib
import os
import queue
import threading
import time
import traceback
from urllib import request as _urlreq

_URL = os.environ.get("PALANTIR_URL", "https://palantir.tomerisr.org.il").rstrip("/")
_TOKEN = os.environ.get("PALANTIR_TOKEN", "")
_PRODUCT = os.environ.get("PALANTIR_PRODUCT", "")
_TIMEOUT = 10

# Локальный дедуп: ошибка внутри цикла способна выстрелить тысячу раз за минуту.
# Дверь бы их склеила, но сетевой флуд всё равно вредит — и приложению, и каналу.
# Поэтому одинаковые ошибки копим и отправляем не чаще раза в _WINDOW секунд,
# передавая накопленный счётчик в hits.
_WINDOW = 300
_seen = {}          # отпечаток -> [время последней отправки, накоплено с тех пор]
_lock = threading.Lock()

_q = queue.Queue(maxsize=100)   # ограничена: лучше потерять сигнал, чем съесть память
_worker = None


def _fingerprint(text, component):
    norm = "".join("<n>" if ch.isdigit() else ch for ch in str(text)[:500])
    return hashlib.sha1(f"{component}|{norm}".encode("utf-8", "replace")).hexdigest()[:16]


def _post(payload):
    import json
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    # Явный User-Agent обязателен: домен за Cloudflare, дефолтный python-urllib
    # отлетает с 403 ещё до сервиса.
    req = _urlreq.Request(
        f"{_URL}/error?token={_TOKEN}", data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "User-Agent": f"palantir-signal/{_PRODUCT or 'unknown'}"})
    with _urlreq.urlopen(req, timeout=_TIMEOUT) as r:
        r.read()


def _drain():
    while True:
        item = _q.get()
        if item is None:
            return
        try:
            _post(item)
        except Exception:
            # Молча: приложение не должно страдать из-за недоступности Палантира.
            pass
        finally:
            _q.task_done()


def _ensure_worker():
    global _worker
    if _worker is None or not _worker.is_alive():
        # daemon: поток не должен мешать процессу завершиться.
        _worker = threading.Thread(target=_drain, name="palantir-signal", daemon=True)
        _worker.start()
        atexit.register(_flush)


def _flush(timeout=5):
    """Даёт очереди дошуметь при выходе — иначе ошибка, из-за которой процесс
    и падает, не успеет уехать. Именно она обычно самая нужная.

    ⚠️ Ждём unfinished_tasks, а НЕ empty(): очередь становится пустой в момент,
    когда воркер ЗАБРАЛ задачу, то есть до того, как ушёл HTTP-запрос. С проверкой
    на empty() flush возвращался мгновенно, процесс завершался и убивал
    поток-демон вместе с недоотправленным сигналом — падение терялось ровно в
    том случае, ради которого всё и делалось.
    """
    try:
        deadline = time.time() + timeout
        while _q.unfinished_tasks and time.time() < deadline:
            time.sleep(0.05)
    except Exception:
        pass


def report_error(text, component=None, severity="high", meta=None, product=None):
    """Отправляет ошибку в Палантир. Возвращает True, если сигнал поставлен в очередь.

    Никогда не бросает исключений — при любой внутренней проблеме просто вернёт False.
    """
    try:
        if not _TOKEN:
            return False
        prod = product or _PRODUCT
        if not prod:
            return False

        fp = _fingerprint(text, component)
        now = time.time()
        with _lock:
            last, pending = _seen.get(fp, (0, 0))
            if now - last < _WINDOW:
                _seen[fp] = (last, pending + 1)   # копим, не шлём
                return False
            hits = pending + 1
            _seen[fp] = (now, 0)
            if len(_seen) > 500:                  # защита от роста словаря
                _seen.clear()

        payload = {"product": prod, "text": str(text)[:8000], "severity": severity,
                   "hits": hits}
        if component:
            payload["component"] = str(component)[:200]
        if meta:
            payload["meta"] = meta

        _ensure_worker()
        try:
            _q.put_nowait(payload)
        except queue.Full:
            return False
        return True
    except Exception:
        return False


def report_exception(exc, component=None, severity="high", meta=None, note=None):
    """Отправляет пойманное исключение вместе с трейсбеком."""
    try:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        head = f"{note}: " if note else ""
        return report_error(f"{head}{type(exc).__name__}: {exc}\n\n{tb[-3000:]}",
                            component=component, severity=severity, meta=meta)
    except Exception:
        return False


def install_excepthook(component=None, severity="high"):
    """Ловит НЕОБРАБОТАННОЕ падение процесса и шлёт его в Палантир.

    Лучший вариант для скриптов и cron-задач: не нужно оборачивать код в
    try/except и искать точку входа — достаточно двух строк в начале файла.
    Скрипт всё равно падает с тем же трейсбеком и тем же кодом возврата;
    контур только узнаёт об этом.

        import palantir_signal
        palantir_signal.install_excepthook(component="collector")
    """
    import sys
    prev = sys.excepthook

    def hook(exc_type, exc, tb):
        try:
            if not issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
                report_exception(exc, component=component, severity=severity,
                                 note="процесс упал")
                _flush(6)
        except Exception:
            pass
        prev(exc_type, exc, tb)      # обычное поведение сохраняется

    sys.excepthook = hook


class guard:
    """Контекст-менеджер: сообщает об исключении и пробрасывает его дальше.

    Намеренно НЕ глушит ошибку — приложение должно вести себя ровно так же,
    как вело бы без Палантира. Контур только наблюдает.
    """

    def __init__(self, note=None, component=None, severity="high", meta=None):
        self.note, self.component = note, component
        self.severity, self.meta = severity, meta

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc is not None:
            report_exception(exc, component=self.component, severity=self.severity,
                             meta=self.meta, note=self.note)
            _flush(3)
        return False        # исключение летит дальше
