"""
Быстрое переключение между спутниковыми терминалами (Starlink / VSAT)
на локальной панели судна (http://192.168.50.2).

Использование:
    python terminal_switch.py starlink
    python terminal_switch.py vsat
    python terminal_switch.py disconnect

Без аргумента - появится текстовое меню выбора.
"""

import html
import re
import sys

import requests

BASE_URL = "http://192.168.50.2"
LOGIN_URL = f"{BASE_URL}/index.php/login"
SWITCH_URL = f"{BASE_URL}/index.php/crew/start_internet"
LOGOUT_URL = f"{BASE_URL}/index.php/chilli_logout"
USAGE_URL = f"{BASE_URL}/index.php/card-usage"

# Логин/пароль не хранятся в коде (исходники открыты на GitHub) -
# они берутся из настроек программы (vsat_star_settings.db).
USERNAME = ""
PASSWORD = ""

COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru,en;q=0.9,de;q=0.8",
}

# Точное написание, как ожидает сервер (с заглавной буквы)
TERMINAL_NAMES = {
    "starlink": "Starlink",
    "vsat": "VSAT",
}


def create_session():
    """Создаёт новую HTTP-сессию с базовыми заголовками, без логина."""
    session = requests.Session()
    session.headers.update(COMMON_HEADERS)
    return session


def login(session=None, username=None, password=None):
    """Авторизуется на переданной сессии (или создаёт новую) и возвращает её."""
    if session is None:
        session = create_session()

    username = username or USERNAME
    password = password or PASSWORD

    # Заходим на страницу логина, чтобы получить свежую сессию
    session.get(LOGIN_URL, timeout=10)

    login_headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": BASE_URL,
        "Referer": LOGIN_URL,
    }
    data = {"username": username, "password": password}

    resp = session.post(LOGIN_URL, headers=login_headers, data=data, timeout=10)
    print(f"[Логин] статус: {resp.status_code}, url после ответа: {resp.url}")

    if resp.status_code != 200:
        raise RuntimeError(f"Ошибка авторизации, код {resp.status_code} - проверь логин/пароль")

    return session


def switch_terminal(session, terminal_key):
    """Переключает терминал. terminal_key: 'starlink' или 'vsat'."""
    terminal_key = terminal_key.lower()
    if terminal_key not in TERMINAL_NAMES:
        raise ValueError(f"Неизвестный терминал: {terminal_key}. Используй 'starlink' или 'vsat'.")

    terminal_value = TERMINAL_NAMES[terminal_key]

    switch_headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/index.php",
        "X-Requested-With": "XMLHttpRequest",
    }

    # Тело формально JSON, хотя Content-Type указывает на urlencoded -
    # так делает оригинальный сайт, повторяем один в один.
    body = f'{{"terminal":"{terminal_value}"}}'

    resp = session.post(SWITCH_URL, headers=switch_headers, data=body, timeout=15)

    print(f"[Переключение на {terminal_value}] статус: {resp.status_code}")
    print("Ответ сервера:", resp.text[:300])

    if resp.status_code != 200:
        raise RuntimeError(f"Сервер вернул {resp.status_code} при переключении на {terminal_value}")

    return resp


USAGE_KEYS = ("downloaded", "uploaded", "remaining_data", "remaining_time")

_USAGE_SPAN_RE = re.compile(r'<span[^>]*class="[^"]*usageData[^"]*"[^>]*>\s*([^<]*?)\s*</span>', re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_TIME_RE = re.compile(
    r"\d+:\d{2}"
    r"|\d+\s*(?:d|h|min|mins|minutes?|hours?|days?|sec|seconds?|дн\w*|ч|час\w*|мин\w*|сек\w*)\b",
    re.I,
)
_DATA_RE = re.compile(r"\d\s*(?:[kmgt]i?b|bytes?|[кмгт]б|байт\w*)\b", re.I)

# Подсказки по подписи рядом со значением. Порядок важен: "Remaining time"
# должно сработать раньше общего "remaining".
_LABEL_HINTS = (
    ("remaining_time", ("time", "врем", "minute", "минут")),
    ("downloaded", ("download", "загруж", "скачан", "входящ", "received")),
    ("uploaded", ("upload", "отправ", "выгруж", "исходящ", "sent")),
    ("remaining_data", ("remaining", "left", "остат", "quota", "balance", "data", "трафик")),
)


def _value_kind(value):
    if _TIME_RE.search(value):
        return "time"
    if _DATA_RE.search(value):
        return "data"
    return "other"


def _label_key(text):
    text = text.lower()
    for key, hints in _LABEL_HINTS:
        if any(h in text for h in hints):
            return key
    return None


def parse_usage(page_html):
    """
    Разбирает страницу card-usage. Набор полей зависит от терминала (на VSAT
    "остатка данных" может не быть), поэтому значения раскладываются не по
    позиции, а по подписи рядом и по формату: "04:12:33" / "6 days" - это время,
    "1.2 GB" - объём.
    """
    items = []
    prev_end = 0
    for m in _USAGE_SPAN_RE.finditer(page_html):
        label = html.unescape(_TAG_RE.sub(" ", page_html[prev_end:m.start()]))
        label = " ".join(label.split())[-60:]
        prev_end = m.end()
        value = html.unescape(m.group(1)).strip()
        if value:
            items.append((_label_key(label), _value_kind(value), value))

    result = {}
    leftovers = []
    for key, kind, value in items:
        # Формат важнее подписи: время не может быть объёмом и наоборот
        if (key == "remaining_time" and kind == "data") or (key != "remaining_time" and kind == "time"):
            key = None
        if key and key not in result:
            result[key] = value
        else:
            leftovers.append((kind, value))

    for kind, value in leftovers:
        if kind == "time":
            slots = ("remaining_time",)
        elif kind == "data":
            slots = ("downloaded", "uploaded", "remaining_data")
        else:
            slots = ("downloaded", "uploaded", "remaining_data", "remaining_time")
        free = next((s for s in slots if s not in result), None)
        if free:
            result[free] = value

    return {key: result.get(key, "?") for key in USAGE_KEYS}


def get_usage(session, dump_path=None):
    """
    Однократно запрашивает страницу статуса (download/upload/remaining data/remaining time).
    ВАЖНО: страница card-usage в браузере сама обновляется каждые 10 секунд (это и жрёт трафик) -
    здесь один запрос на вызов; программа вызывает его вручную и раз в 10 минут.
    dump_path - куда сохранить полученную страницу для диагностики (без лишних запросов).
    """
    resp = session.get(USAGE_URL, timeout=10)
    print(f"[Статус] статус ответа: {resp.status_code}, размер: {len(resp.content)} байт")

    if dump_path:
        try:
            with open(dump_path, "w", encoding="utf-8") as f:
                f.write(resp.text)
        except OSError as e:
            print(f"Не удалось сохранить {dump_path}: {e}")

    result = parse_usage(resp.text)
    print("Статус:", result)
    return result


def disconnect(session):
    """Завершает сессию (logout), чтобы не расходовать трафик впустую."""
    logout_headers = {
        "Referer": f"{BASE_URL}/index.php",
    }
    resp = session.get(LOGOUT_URL, headers=logout_headers, timeout=10)
    print(f"[Отключение] статус: {resp.status_code}")
    print("Ответ сервера:", resp.text[:300])
    if resp.status_code != 200:
        raise RuntimeError(f"Сервер вернул {resp.status_code} при отключении")
    return resp


def remaining_minutes(text):
    """
    Переводит "Remaining Time" в минуты: "03:07:23" -> 187.4, "1 day 02:00:00" -> 1560.
    Возвращает None, если время не распознано.
    """
    if not text or text == "?":
        return None
    total = 0.0
    found = False
    days = re.search(r"(\d+)\s*(?:d|days?|дн\w*)\b", text, re.I)
    if days:
        total += int(days.group(1)) * 1440
        found = True
    hms = re.search(r"(\d+):(\d{2})(?::(\d{2}))?", text)
    if hms:
        total += int(hms.group(1)) * 60 + int(hms.group(2)) + int(hms.group(3) or 0) / 60
        found = True
    else:
        hours = re.search(r"(\d+)\s*(?:h|hours?|ч|час\w*)\b", text, re.I)
        mins = re.search(r"(\d+)\s*(?:m|min|mins|minutes?|мин\w*)\b", text, re.I)
        if hours:
            total += int(hours.group(1)) * 60
            found = True
        if mins:
            total += int(mins.group(1))
            found = True
    return total if found else None


def main():
    global USERNAME, PASSWORD
    if not USERNAME:
        # Запуск из консоли - берём логин/пароль из настроек программы
        import settings_store
        saved_user, saved_pass = settings_store.load_credentials()
        USERNAME, PASSWORD = saved_user or "", saved_pass or ""

    if len(sys.argv) > 1:
        choice = sys.argv[1].lower()
    else:
        print("Выбери действие:")
        print("  1 - Starlink")
        print("  2 - VSAT")
        print("  3 - Отключиться (logout)")
        raw = input("Твой выбор (1/2/3): ").strip()
        choice = {"1": "starlink", "2": "vsat", "3": "disconnect"}.get(raw, raw)

    session = login()

    if choice == "disconnect":
        disconnect(session)
    else:
        switch_terminal(session, choice)


if __name__ == "__main__":
    main()
