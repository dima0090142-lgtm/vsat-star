"""
Локальное хранилище настроек (логин/пароль, видимость журнала, позиция окна)
для VSAT STAR S/W. Использует SQLite-файл рядом со скриптом - никаких внешних серверов.
"""

import os
import sqlite3
import sys
from contextlib import closing

if getattr(sys, "frozen", False):
    # Запущено как собранный .exe (PyInstaller) - база лежит рядом с exe,
    # а не во временной папке распаковки (она меняется при каждом запуске).
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(BASE_DIR, "vsat_star_settings.db")

_UPSERT = (
    "INSERT INTO settings (key, value) VALUES (?, ?) "
    "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
)


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    return conn


def get_setting(key, default=None):
    with closing(_connect()) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(key, value):
    with closing(_connect()) as conn, conn:
        conn.execute(_UPSERT, (key, value))


def get_bool(key, default=False):
    value = get_setting(key)
    return default if value is None else value == "1"


def set_bool(key, value):
    set_setting(key, "1" if value else "0")


def save_credentials(username, password):
    with closing(_connect()) as conn, conn:
        conn.executemany(_UPSERT, (("username", username), ("password", password)))


def load_credentials():
    """Возвращает (username, password) или (None, None), если ещё не сохранено."""
    with closing(_connect()) as conn:
        cur = conn.execute("SELECT key, value FROM settings WHERE key IN ('username', 'password')")
        data = dict(cur.fetchall())
    return data.get("username"), data.get("password")
