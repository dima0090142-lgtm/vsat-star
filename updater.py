"""
Проверка обновлений VSAT STAR S/W через GitHub.

1. Последний Release (если выложен) - даёт версию и ссылку на скачивание .exe.
2. Если релизов нет - номер версии из начала gui_app.py в ветке main
   (читаем только первые 4 КБ, чтобы не тратить спутниковый трафик).
"""

import re

import requests

REPO = "dima0090142-lgtm/vsat-star"
REPO_URL = f"https://github.com/{REPO}"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RAW_MAIN_APP = f"https://raw.githubusercontent.com/{REPO}/main/gui_app.py"
CONTENTS_API = f"https://api.github.com/repos/{REPO}/contents/gui_app.py?ref=main"

_HEADERS = {"User-Agent": "VSAT-STAR-updater", "Accept": "application/vnd.github+json"}


def parse_version(text):
    """'v4.3' / '4.3.1' / '4,3' -> (4, 3, 1); пустой кортеж, если цифр нет."""
    return tuple(int(n) for n in re.findall(r"\d+", text or ""))


def is_newer(remote, local):
    r, l = parse_version(remote), parse_version(local)
    width = max(len(r), len(l))
    return r + (0,) * (width - len(r)) > l + (0,) * (width - len(l))


def check_latest(timeout=20):
    """
    Возвращает {"version": "4.4", "url": ссылка для скачивания/просмотра}.
    Бросает исключение requests при отсутствии связи.
    """
    resp = requests.get(RELEASES_API, headers=_HEADERS, timeout=timeout)
    if resp.status_code == 200:
        data = resp.json()
        url = data.get("html_url") or f"{REPO_URL}/releases"
        for asset in data.get("assets", []):
            if asset.get("name", "").lower().endswith(".exe"):
                url = asset.get("browser_download_url") or url
                break
        return {"version": data.get("tag_name", "").lstrip("vV"), "url": url}

    # Релизов ещё нет - смотрим версию в исходниках. raw.githubusercontent.com
    # бывает недоступен, тогда тот же файл через API.
    sources = (
        (RAW_MAIN_APP, {"Range": "bytes=0-4095"}),
        (CONTENTS_API, {**_HEADERS, "Accept": "application/vnd.github.raw", "Range": "bytes=0-4095"}),
    )
    last_error = None
    for url, headers in sources:
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            last_error = e
            continue
        match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', resp.text)
        if match:
            return {"version": match.group(1), "url": REPO_URL}
    if last_error:
        raise last_error
    raise RuntimeError("Не удалось определить версию в репозитории")
