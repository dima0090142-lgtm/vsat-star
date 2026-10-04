"""
VSAT STAR S/W v4.3
GUI-переключатель терминалов (Starlink / VSAT) с логаутом и статусом трафика.
Стиль: градиент + "стекло" (glassmorphism), векторные иконки из icons.py.

Запуск: python gui_app.py
Требуется: pip install PySide6 requests
Файлы terminal_switch.py, settings_store.py и icons.py должны лежать рядом.

Горячие клавиши: F5 - обновить трафик, Ctrl+, - настройки, Esc - свернуть в трей.
Трафик обновляется сам каждые 10 минут; за 30 минут до конца дневного лимита -
напоминание в трее.
"""

import html
import os
import sys
from datetime import datetime

import requests
from PySide6.QtCore import (
    Qt, QThread, Signal, QTimer, QRectF, QPointF, QSize, QPoint,
    QVariantAnimation, QEasingCurve,
)
from PySide6.QtGui import (
    QLinearGradient, QRadialGradient, QPainter, QPainterPath, QColor, QBrush,
    QPen, QAction, QKeySequence, QShortcut, QPalette, QGuiApplication, QFont,
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton,
    QToolButton, QAbstractButton, QLabel, QTextEdit, QFrame, QSystemTrayIcon,
    QMenu, QDialog, QLineEdit, QLayout, QSizePolicy,
)

import icons
import settings_store
import terminal_switch as ts
import updater

APP_NAME = "VSAT STAR"
APP_VERSION = "4.3"
APP_TITLE = f"{APP_NAME} S/W v{APP_VERSION}"
APP_AUTHOR = "Sukhoverkhii Dmitrii"
GITHUB_URL = updater.REPO_URL  # открытый исходный код

AUTO_REFRESH_MINUTES = 10   # как часто программа сама обновляет трафик
REMIND_MINUTES = 30         # за сколько минут до конца дневного лимита напомнить

# ---------- Палитра ----------

STATUS_COLORS = {
    "ok": "#4ADE80",       # зелёный - подключено
    "warn": "#FACC15",     # жёлтый - отключено
    "error": "#F87171",    # красный - ошибка
    "busy": "#60A5FA",     # синий - идёт запрос
    "neutral": "#CBD5E1",
}
DANGER = "#F87171"
PRIMARY = "#38BDF8"

TERMINALS = {
    "starlink": {"label": "Starlink", "icon": "satellite", "accent": "#38BDF8"},
    "vsat": {"label": "VSAT", "icon": "dish", "accent": "#C084FC"},
}

ACTION_TEXT = {
    "starlink": "Переключаю на Starlink…",
    "vsat": "Переключаю на VSAT…",
    "disconnect": "Отключаю…",
    "usage": "Запрашиваю трафик…",
}


def rgba(hex_color, alpha):
    c = QColor(hex_color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


def now_hms():
    return datetime.now().strftime("%H:%M:%S")


def now_hm():
    return datetime.now().strftime("%H:%M")


def short_text(text, limit=160):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit] + "…"


AUTO_CAPTION = f"авто каждые {AUTO_REFRESH_MINUTES} мин"

# Последняя полученная страница трафика - для диагностики разбора полей
USAGE_DUMP_PATH = os.path.join(settings_store.BASE_DIR, "last_card_usage.html")


# ---------- Фоновый поток для сетевых запросов (чтобы GUI не зависал) ----------

class Worker(QThread):
    log = Signal(str)
    succeeded = Signal(str, object)   # (действие, данные)
    failed = Signal(str, str)         # (действие, понятное сообщение)

    def __init__(self, action, session):
        super().__init__()
        self.action = action  # 'starlink' / 'vsat' / 'disconnect' / 'usage'
        self.session = session

    def run(self):
        try:
            if self.action == "usage":
                # Никакого логина - просто читаем уже открытую сессию,
                # чтобы не сбрасывать активное подключение.
                self.log.emit("Запрашиваю статус (без повторного логина)...")
                data = ts.get_usage(self.session, dump_path=USAGE_DUMP_PATH)
                self.log.emit(f"Статус получен: {data}")
                self.succeeded.emit(self.action, data)

            elif self.action == "disconnect":
                self.log.emit("Авторизация...")
                ts.login(self.session)
                resp = ts.disconnect(self.session)
                self.log.emit(f"Logout: код {resp.status_code}, ответ: {short_text(resp.text)}")
                self.succeeded.emit(self.action, None)

            else:  # starlink / vsat
                self.log.emit("Авторизация...")
                ts.login(self.session)
                resp = ts.switch_terminal(self.session, self.action)
                self.log.emit(
                    f"Запуск {ts.TERMINAL_NAMES[self.action]}: код {resp.status_code}, "
                    f"ответ: {short_text(resp.text)}"
                )
                self.succeeded.emit(self.action, None)

        # Timeout проверяем первым: ConnectTimeout наследуется и от ConnectionError.
        except requests.exceptions.Timeout:
            self.failed.emit(self.action, "Панель не отвечает (тайм-аут)")
        except requests.exceptions.ConnectionError:
            self.failed.emit(self.action, f"Нет связи с панелью {ts.BASE_URL}")
        except Exception as e:
            self.failed.emit(self.action, str(e))


# ---------- Отрисовка стеклянной карточки (общая для окна и диалога) ----------

def paint_glass_card(painter, outer_rect, margin, radius):
    """Мягкая тень в отступах + градиентная карточка со "стеклянными" бликами."""
    painter.setRenderHint(QPainter.Antialiasing)
    card = QRectF(outer_rect).adjusted(margin, margin, -margin, -margin)

    # Тень: несколько полупрозрачных слоёв, без QGraphicsEffect (тот размывает текст на HiDPI)
    painter.setPen(Qt.NoPen)
    for i in range(margin, 0, -1):
        painter.setBrush(QColor(0, 0, 0, int(11 * (1 - i / margin) ** 2) + 1))
        painter.drawRoundedRect(card.adjusted(-i, -i + 4, i, i + 4), radius + i, radius + i)

    path = QPainterPath()
    path.addRoundedRect(card, radius, radius)

    grad = QLinearGradient(card.topLeft(), card.bottomRight())
    grad.setColorAt(0.0, QColor(28, 36, 104))
    grad.setColorAt(0.55, QColor(78, 46, 146))
    grad.setColorAt(1.0, QColor(18, 96, 156))
    painter.fillPath(path, grad)

    # Цветные "сферы" за стеклом
    painter.save()
    painter.setClipPath(path)
    orbs = (
        (QPointF(card.right() - 30, card.top() + 20), 190, QColor(56, 189, 248, 75)),
        (QPointF(card.left() + 10, card.bottom() - 30), 220, QColor(236, 72, 153, 50)),
    )
    for center, r, color in orbs:
        fade = QColor(color)
        fade.setAlpha(0)
        rg = QRadialGradient(center, r)
        rg.setColorAt(0.0, color)
        rg.setColorAt(1.0, fade)
        painter.setBrush(rg)
        painter.drawEllipse(center, r, r)
    painter.restore()

    # Рамка, светлее сверху
    edge = QLinearGradient(card.topLeft(), card.bottomLeft())
    edge.setColorAt(0.0, QColor(255, 255, 255, 95))
    edge.setColorAt(1.0, QColor(255, 255, 255, 25))
    painter.setPen(QPen(QBrush(edge), 1))
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(card.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)


# ---------- Мелкие виджеты ----------

class IconButton(QAbstractButton):
    """Круглая стеклянная кнопка с векторной иконкой; умеет вращать иконку (индикатор загрузки)."""

    def __init__(self, icon_name, tooltip="", size=30, icon_size=16, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tooltip)
        self._icon_name = icon_name
        self._icon_size = icon_size
        self._angle = 0.0
        self._spin = QTimer(self)
        self._spin.setInterval(16)
        self._spin.timeout.connect(self._tick)

    def set_spinning(self, on):
        if on:
            self._spin.start()
        else:
            self._spin.stop()
            self._angle = 0.0
        self.update()

    def _tick(self):
        self._angle = (self._angle + 6) % 360
        self.update()

    def sizeHint(self):
        return self.size()

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        alpha = 26
        if self.isEnabled() and self.underMouse():
            alpha = 70 if self.isDown() else 52
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, alpha))
        p.drawEllipse(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))

        spinning = self._spin.isActive()
        p.setOpacity(1.0 if self.isEnabled() or spinning else 0.4)
        pix = icons.pixmap(self._icon_name, self._icon_size, "#FFFFFF", self.devicePixelRatioF())
        s = self._icon_size
        p.translate(self.width() / 2, self.height() / 2)
        p.rotate(self._angle)
        p.drawPixmap(QPointF(-s / 2, -s / 2), pix)


class StatusDot(QWidget):
    """Цветной индикатор с ореолом; пульсирует, пока идёт запрос."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(18, 18)
        self._color = QColor(STATUS_COLORS["neutral"])
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def set_state(self, color, pulsing=False):
        self._color = QColor(color)
        if pulsing:
            self._timer.start()
        else:
            self._timer.stop()
            self._phase = 0.0
        self.update()

    def _tick(self):
        self._phase = (self._phase + 0.05) % 1.0
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        center = QPointF(self.width() / 2, self.height() / 2)
        p.setPen(Qt.NoPen)

        halo = QColor(self._color)
        if self._timer.isActive():
            halo.setAlpha(int(120 * (1 - self._phase)))
            r = 4 + 5 * self._phase
        else:
            halo.setAlpha(70)
            r = 8
        p.setBrush(halo)
        p.drawEllipse(center, r, r)

        p.setBrush(self._color)
        p.drawEllipse(center, 4, 4)


class ElidedLabel(QLabel):
    """Однострочная подпись, которая обрезается многоточием и не раздувает окно."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setText(text)

    def setText(self, text):
        self._full = text or ""
        self._refresh()

    def full_text(self):
        return self._full

    def _refresh(self):
        elided = self.fontMetrics().elidedText(self._full, Qt.ElideRight, max(self.width(), 10))
        super().setText(elided)
        self.setToolTip(self._full if elided != self._full else "")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (event.Type.FontChange, event.Type.StyleChange):
            self._refresh()

    def sizeHint(self):
        return QSize(10, super().sizeHint().height())

    def minimumSizeHint(self):
        return QSize(10, super().minimumSizeHint().height())


class ToggleSwitch(QAbstractButton):
    """Переключатель в стиле iOS с плавной анимацией."""

    def __init__(self, checked=False, accent=PRIMARY, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(42, 24)
        self._accent = QColor(accent)
        self.setChecked(checked)
        self._offset = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self.toggled.connect(self._animate)

    def _animate(self, checked):
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def _on_anim(self, value):
        self._offset = float(value)
        self.update()

    def sizeHint(self):
        return QSize(42, 24)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        off = QColor(255, 255, 255, 45)
        t = self._offset
        track = QColor(
            int(off.red() + (self._accent.red() - off.red()) * t),
            int(off.green() + (self._accent.green() - off.green()) * t),
            int(off.blue() + (self._accent.blue() - off.blue()) * t),
            int(off.alpha() + (230 - off.alpha()) * t),
        )
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.setBrush(track)
        p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

        knob = rect.height() - 6
        x = rect.left() + 3 + t * (rect.width() - knob - 6)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(QRectF(x, rect.top() + 3, knob, knob))


class TerminalButton(QToolButton):
    """Крупная плитка терминала: иконка над подписью, подсветка активного."""

    def __init__(self, key, parent=None):
        super().__init__(parent)
        self.key = key
        self._info = TERMINALS[key]
        self._active = False
        accent = self._info["accent"]

        self.setText(self._info["label"])
        self.setIcon(icons.icon(self._info["icon"], "#FFFFFF"))
        self.setIconSize(QSize(32, 32))
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"Подключиться через {self._info['label']}")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(92)
        self.setProperty("active", False)
        self.setStyleSheet(f"""
            QToolButton {{
                background-color: rgba(255, 255, 255, 26);
                border: 1px solid rgba(255, 255, 255, 48);
                border-radius: 16px;
                color: white;
                font-size: 14px;
                font-weight: 600;
                padding: 12px 6px 10px 6px;
            }}
            QToolButton:hover {{ background-color: rgba(255, 255, 255, 50); }}
            QToolButton:pressed {{ background-color: rgba(255, 255, 255, 18); }}
            QToolButton:disabled {{
                background-color: rgba(255, 255, 255, 14);
                border: 1px solid rgba(255, 255, 255, 28);
                color: rgba(255, 255, 255, 110);
            }}
            QToolButton[active="true"] {{
                background-color: {rgba(accent, 55)};
                border: 2px solid {rgba(accent, 210)};
            }}
            QToolButton[active="true"]:hover {{ background-color: {rgba(accent, 80)}; }}
        """)

    def set_active(self, active):
        if active == self._active:
            return
        self._active = active
        self.setProperty("active", active)
        color = self._info["accent"] if active else "#FFFFFF"
        self.setIcon(icons.icon(self._info["icon"], color))
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._active:
            return
        # Маленький "светодиод" в углу активной плитки
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        center = QPointF(self.width() - 16, 16)
        glow = QColor(STATUS_COLORS["ok"])
        glow.setAlpha(80)
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(center, 7, 7)
        p.setBrush(QColor(STATUS_COLORS["ok"]))
        p.drawEllipse(center, 3.5, 3.5)


class StatTile(QFrame):
    """Плитка статистики трафика: иконка в цветном "бейдже", подпись и значение."""

    def __init__(self, icon_name, caption, accent, parent=None):
        super().__init__(parent)
        self.setObjectName("tile")
        self.setStyleSheet("""
            #tile {
                background-color: rgba(0, 0, 0, 38);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 12px;
            }
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(9)

        badge = QLabel()
        badge.setFixedSize(30, 30)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(f"background-color: {rgba(accent, 50)}; border-radius: 9px;")
        badge.setPixmap(icons.icon(icon_name, accent, 2.0).pixmap(QSize(16, 16)))
        lay.addWidget(badge)

        col = QVBoxLayout()
        col.setSpacing(0)
        cap = QLabel(caption)
        cap.setStyleSheet("color: rgba(255,255,255,150); font-size: 10px;")
        self.value = ElidedLabel("—")
        self.value.setStyleSheet("color: white; font-size: 14px; font-weight: 700;")
        col.addWidget(cap)
        col.addWidget(self.value)
        lay.addLayout(col, stretch=1)

    def set_value(self, text):
        self.value.setText(text if text and text != "?" else "—")

    def set_alert(self, on):
        color = STATUS_COLORS["warn"] if on else "white"
        self.value.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: 700;")


def section_label(text):
    label = QLabel(text.upper())
    label.setStyleSheet("color: rgba(255,255,255,140); font-size: 10px; font-weight: 700; letter-spacing: 1.5px;")
    return label


LINE_EDIT_QSS = f"""
    QLineEdit {{
        background-color: rgba(0, 0, 0, 50);
        border: 1px solid rgba(255, 255, 255, 45);
        border-radius: 10px;
        color: white;
        padding: 8px 6px;
        font-size: 13px;
        selection-background-color: {rgba(PRIMARY, 150)};
    }}
    QLineEdit:focus {{
        border: 1px solid {rgba(PRIMARY, 210)};
        background-color: rgba(0, 0, 0, 70);
    }}
"""

GLASS_BUTTON_QSS = """
    QPushButton {
        background-color: rgba(255, 255, 255, 30);
        border: 1px solid rgba(255, 255, 255, 60);
        border-radius: 12px;
        color: white;
        font-size: 13px;
        font-weight: 600;
        padding: 9px 16px;
    }
    QPushButton:hover { background-color: rgba(255, 255, 255, 55); }
    QPushButton:pressed { background-color: rgba(255, 255, 255, 20); }
"""

PRIMARY_BUTTON_QSS = """
    QPushButton {
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #38BDF8, stop:1 #818CF8);
        border: 1px solid rgba(255, 255, 255, 90);
        border-radius: 12px;
        color: white;
        font-size: 13px;
        font-weight: 700;
        padding: 9px 16px;
    }
    QPushButton:hover {
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #5ECBFA, stop:1 #99A3FA);
    }
    QPushButton:pressed { background-color: #3A8FD0; }
"""

MENU_QSS = """
    QMenu {
        background-color: #1F2457;
        color: white;
        border: 1px solid rgba(255, 255, 255, 45);
        padding: 6px;
    }
    QMenu::item { padding: 7px 22px 7px 10px; border-radius: 6px; }
    QMenu::item:selected { background-color: rgba(255, 255, 255, 32); }
    QMenu::item:disabled { color: rgba(255, 255, 255, 90); }
    QMenu::separator { height: 1px; background: rgba(255, 255, 255, 35); margin: 5px 8px; }
    QMenu::icon { padding-left: 8px; }
"""


def styled_line_edit(text, placeholder, icon_name):
    edit = QLineEdit(text or "")
    edit.setPlaceholderText(placeholder)
    edit.setStyleSheet(LINE_EDIT_QSS)
    pal = edit.palette()
    pal.setColor(QPalette.PlaceholderText, QColor(255, 255, 255, 110))
    edit.setPalette(pal)
    edit.addAction(icons.icon(icon_name, "#CBD5E1"), QLineEdit.ActionPosition.LeadingPosition)
    return edit


def drop_hover_state(*widgets):
    """После модального окна Qt не присылает leaveEvent - сбрасываем "залипший" hover вручную."""
    for w in widgets:
        w.setAttribute(Qt.WA_UnderMouse, False)
        w.update()


# ---------- Диалог настроек (логин/пароль) ----------

class UpdateCheckWorker(QThread):
    found = Signal(dict)   # {"version": ..., "url": ...}
    failed = Signal(str)

    def run(self):
        try:
            self.found.emit(updater.check_latest())
        except requests.exceptions.RequestException:
            self.failed.emit("Нет связи с GitHub")
        except Exception as e:
            self.failed.emit(str(e))


class SettingsDialog(QDialog):
    MARGIN = 14
    RADIUS = 18

    def __init__(self, parent, username, password, show_log, on_saved):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle(f"Настройки — {APP_NAME}")
        self.setModal(True)
        self._on_saved = on_saved
        self._handled = False

        root = QVBoxLayout(self)
        m = self.MARGIN
        root.setContentsMargins(m + 18, m + 14, m + 18, m + 18)
        root.setSizeConstraint(QLayout.SetFixedSize)

        content = QWidget()
        content.setFixedWidth(290)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        root.addWidget(content)

        # Заголовок
        header = QHBoxLayout()
        header.setSpacing(8)
        gear = QLabel()
        gear.setPixmap(icons.icon("settings", "#FFFFFF").pixmap(QSize(20, 20)))
        title = QLabel("Настройки")
        title.setStyleSheet("color: white; font-size: 16px; font-weight: 700;")
        close_btn = IconButton("close", "Сохранить и закрыть", size=28, icon_size=14)
        close_btn.clicked.connect(self._save_and_close)  # крестик тоже сохраняет
        header.addWidget(gear)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(close_btn)
        lay.addLayout(header)
        lay.addSpacing(4)

        # Учётная запись
        lay.addWidget(section_label("Учётная запись панели"))
        self.username_edit = styled_line_edit(username, "Логин", "user")
        self.password_edit = styled_line_edit(password, "Пароль", "lock")
        self.password_edit.setEchoMode(QLineEdit.Password)
        self._eye_action = self.password_edit.addAction(
            icons.icon("eye", "#CBD5E1"), QLineEdit.ActionPosition.TrailingPosition
        )
        self._eye_action.setToolTip("Показать пароль")
        self._eye_action.triggered.connect(self._toggle_password)
        lay.addWidget(self.username_edit)
        lay.addWidget(self.password_edit)
        lay.addSpacing(4)

        # Интерфейс
        lay.addWidget(section_label("Интерфейс"))
        log_row = QHBoxLayout()
        log_icon = QLabel()
        log_icon.setPixmap(icons.icon("terminal", "#CBD5E1").pixmap(QSize(18, 18)))
        log_text = QLabel("Показывать журнал действий")
        log_text.setStyleSheet("color: white; font-size: 13px;")
        self.show_log_switch = ToggleSwitch(show_log)
        log_row.addWidget(log_icon)
        log_row.addSpacing(4)
        log_row.addWidget(log_text)
        log_row.addStretch()
        log_row.addWidget(self.show_log_switch)
        lay.addLayout(log_row)

        # Примечание о хранении
        note_row = QHBoxLayout()
        note_row.setSpacing(6)
        note_icon = QLabel()
        note_icon.setPixmap(icons.icon("shield", "#94A3B8").pixmap(QSize(14, 14)))
        note = QLabel("Данные хранятся только на этом компьютере")
        note.setStyleSheet("color: rgba(255,255,255,120); font-size: 10px;")
        note_row.addWidget(note_icon)
        note_row.addWidget(note)
        note_row.addStretch()
        lay.addSpacing(2)
        lay.addLayout(note_row)
        lay.addSpacing(4)

        # О программе
        lay.addWidget(section_label("О программе"))
        lay.addWidget(self._build_about())
        lay.addSpacing(6)

        # Кнопки
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        cancel_btn = QPushButton("Отмена")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(GLASS_BUTTON_QSS)
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Сохранить")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(PRIMARY_BUTTON_QSS)
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save_and_close)
        buttons.addWidget(cancel_btn, stretch=1)
        buttons.addWidget(save_btn, stretch=1)
        lay.addLayout(buttons)

    def _build_about(self):
        card = QFrame()
        card.setObjectName("aboutCard")
        card.setStyleSheet("""
            #aboutCard {
                background-color: rgba(0, 0, 0, 38);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 12px;
            }
        """)
        outer = QVBoxLayout(card)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(10)
        lay = QHBoxLayout()
        lay.setSpacing(10)
        outer.addLayout(lay)

        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(QSize(40, 40)))
        logo.setAlignment(Qt.AlignTop)
        lay.addWidget(logo)

        col = QVBoxLayout()
        col.setSpacing(2)
        name = QLabel(APP_TITLE)
        name.setStyleSheet("color: white; font-size: 13px; font-weight: 700;")
        author = QLabel(f"Автор: {APP_AUTHOR}")
        author.setStyleSheet("color: rgba(255,255,255,200); font-size: 11px;")
        if GITHUB_URL:
            source = QLabel(
                f"Открытый исходный код: <a href='{GITHUB_URL}' "
                f"style='color:{PRIMARY}; text-decoration:none;'>GitHub</a>"
            )
            source.setOpenExternalLinks(True)
        else:
            source = QLabel("Открытый исходный код на GitHub —\nссылка появится в следующем обновлении")
        source.setStyleSheet("color: rgba(255,255,255,130); font-size: 10px;")
        col.addWidget(name)
        col.addWidget(author)
        col.addWidget(source)
        lay.addLayout(col, stretch=1)

        # Проверка обновлений
        update_row = QVBoxLayout()
        update_row.setSpacing(6)
        self.update_btn = QPushButton("  Проверить обновления")
        self.update_btn.setIcon(icons.icon("refresh"))
        self.update_btn.setIconSize(QSize(14, 14))
        self.update_btn.setCursor(Qt.PointingHandCursor)
        self.update_btn.setStyleSheet(GLASS_BUTTON_QSS.replace("padding: 9px 16px", "padding: 6px 10px")
                                      .replace("font-size: 13px", "font-size: 11px"))
        self.update_btn.clicked.connect(self._check_updates)
        self.update_status = QLabel("")
        self.update_status.setOpenExternalLinks(True)
        self.update_status.setStyleSheet("color: rgba(255,255,255,170); font-size: 10px;")
        self.update_status.setAlignment(Qt.AlignCenter)
        self.update_status.setVisible(False)
        update_row.addWidget(self.update_btn)
        update_row.addWidget(self.update_status)
        outer.addLayout(update_row)
        return card

    def _check_updates(self):
        self.update_btn.setEnabled(False)
        self.update_status.setStyleSheet("color: rgba(255,255,255,170); font-size: 10px;")
        self.update_status.setText("Проверяю…")
        self.update_status.setVisible(True)
        # Поток привязан к главному окну - не оборвётся, если диалог закроют раньше
        worker = UpdateCheckWorker(self.parent())
        worker.found.connect(self._on_update_info)
        worker.failed.connect(self._on_update_failed)
        worker.finished.connect(worker.deleteLater)
        self._update_worker = worker
        worker.start()

    def _on_update_info(self, info):
        self.update_btn.setEnabled(True)
        if updater.is_newer(info["version"], APP_VERSION):
            self.update_status.setStyleSheet(f"color: {STATUS_COLORS['warn']}; font-size: 10px;")
            self.update_status.setText(
                f"Доступна v{info['version']} — <a href='{info['url']}' "
                f"style='color:{PRIMARY}; text-decoration:none;'>скачать</a>"
            )
        else:
            self.update_status.setStyleSheet(f"color: {STATUS_COLORS['ok']}; font-size: 10px;")
            self.update_status.setText("У вас последняя версия")

    def _on_update_failed(self, message):
        self.update_btn.setEnabled(True)
        self.update_status.setStyleSheet(f"color: {STATUS_COLORS['error']}; font-size: 10px;")
        self.update_status.setText(message)

    def _toggle_password(self):
        hidden = self.password_edit.echoMode() == QLineEdit.Password
        self.password_edit.setEchoMode(QLineEdit.Normal if hidden else QLineEdit.Password)
        self._eye_action.setIcon(icons.icon("eye-off" if hidden else "eye", "#CBD5E1"))
        self._eye_action.setToolTip("Скрыть пароль" if hidden else "Показать пароль")

    def _save(self):
        self._handled = True
        self._on_saved(
            self.username_edit.text().strip(),
            self.password_edit.text(),
            self.show_log_switch.isChecked(),
        )

    def _save_and_close(self):
        self._save()
        self.accept()

    def reject(self):
        self._handled = True
        super().reject()

    def closeEvent(self, event):
        # Alt+F4 тоже сохраняет - как крестик в заголовке
        if not self._handled:
            self._save()
        super().closeEvent(event)

    def paintEvent(self, event):
        paint_glass_card(QPainter(self), self.rect(), self.MARGIN, self.RADIUS)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.windowHandle():
            self.windowHandle().startSystemMove()


# ---------- Главное окно ----------

class MainWindow(QWidget):
    MARGIN = 16          # место под тень вокруг карточки
    RADIUS = 22
    CONTENT_WIDTH = 344
    LOG_HEIGHT = 140

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(icons.app_icon())

        self.worker = None
        self._active_terminal = None
        self._last_status = ("neutral", "Готово", "")
        self._tray_hint_shown = False
        self._quiet_run = False       # фоновое автообновление - без смены статуса и уведомлений об ошибках
        self._limit_reminded = False  # напоминание о лимите уже показано в этой сессии

        # Персистентная сессия на весь жизненный цикл приложения -
        # статус трафика читается БЕЗ повторного логина через неё.
        self.session = ts.create_session()

        username, password = settings_store.load_credentials()
        if username:
            ts.USERNAME = username
        if password:
            ts.PASSWORD = password
        self._show_log_pref = settings_store.get_bool("show_log", False)

        self._build_ui()
        self._build_tray()
        self._build_shortcuts()
        self._apply_log_visibility(self._show_log_pref)
        self._restore_position()

        self.auto_timer = QTimer(self)
        self.auto_timer.setInterval(AUTO_REFRESH_MINUTES * 60 * 1000)
        self.auto_timer.timeout.connect(self._auto_refresh)
        self.auto_timer.start()

        self._set_status("neutral", "Готово", "Выберите терминал для подключения")

    # ---- UI ----

    def _build_ui(self):
        root = QVBoxLayout(self)
        m = self.MARGIN
        root.setContentsMargins(m + 18, m + 14, m + 18, m + 18)
        root.setSizeConstraint(QLayout.SetFixedSize)  # окно само подстраивает высоту под журнал

        content = QWidget()
        content.setFixedWidth(self.CONTENT_WIDTH)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        root.addWidget(content)

        lay.addLayout(self._build_header())
        lay.addWidget(self._build_status_card())

        # --- Терминалы ---
        lay.addSpacing(2)
        lay.addWidget(section_label("Терминал"))
        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        self.terminal_buttons = {}
        for key in TERMINALS:
            btn = TerminalButton(key)
            btn.clicked.connect(lambda _=False, k=key: self._run_action(k))
            self.terminal_buttons[key] = btn
            tiles.addWidget(btn)
        lay.addLayout(tiles)

        self.btn_disconnect = QPushButton("  Отключить")
        self.btn_disconnect.setIcon(icons.icon("power", "#FCA5A5", 2.0))
        self.btn_disconnect.setIconSize(QSize(18, 18))
        self.btn_disconnect.setCursor(Qt.PointingHandCursor)
        self.btn_disconnect.setToolTip("Завершить сессию, чтобы не расходовать трафик")
        self.btn_disconnect.setMinimumHeight(44)
        self.btn_disconnect.setStyleSheet(f"""
            QPushButton {{
                background-color: {rgba(DANGER, 38)};
                border: 1px solid {rgba(DANGER, 120)};
                border-radius: 14px;
                color: #FFE4E4;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {rgba(DANGER, 75)}; }}
            QPushButton:pressed {{ background-color: {rgba(DANGER, 25)}; }}
            QPushButton:disabled {{
                background-color: rgba(255, 255, 255, 14);
                border: 1px solid rgba(255, 255, 255, 28);
                color: rgba(255, 255, 255, 110);
            }}
        """)
        self.btn_disconnect.clicked.connect(lambda: self._run_action("disconnect"))
        lay.addWidget(self.btn_disconnect)

        # --- Трафик (обновляется только вручную) ---
        lay.addSpacing(2)
        traffic_header = QHBoxLayout()
        traffic_header.addWidget(section_label("Трафик"))
        traffic_header.addStretch()
        self.usage_caption = QLabel(AUTO_CAPTION)
        self.usage_caption.setToolTip(
            f"Трафик обновляется сам каждые {AUTO_REFRESH_MINUTES} минут и по кнопке «Обновить» (F5).\n"
            f"За {REMIND_MINUTES} минут до конца дневного лимита придёт напоминание."
        )
        self.usage_caption.setStyleSheet("color: rgba(255,255,255,120); font-size: 10px;")
        traffic_header.addWidget(self.usage_caption)
        lay.addLayout(traffic_header)

        grid = QGridLayout()
        grid.setSpacing(8)
        self.stat_tiles = {
            "downloaded": StatTile("download", "Загружено", "#38BDF8"),
            "uploaded": StatTile("upload", "Отправлено", "#C084FC"),
            "remaining_data": StatTile("database", "Остаток данных", "#4ADE80"),
            "remaining_time": StatTile("clock", "Остаток времени", "#FACC15"),
        }
        for i, tile in enumerate(self.stat_tiles.values()):
            grid.addWidget(tile, i // 2, i % 2)
        lay.addLayout(grid)

        # --- Журнал (скрыт по умолчанию, включается в настройках) ---
        self.log_panel = QWidget()
        log_lay = QVBoxLayout(self.log_panel)
        log_lay.setContentsMargins(0, 2, 0, 0)
        log_lay.setSpacing(6)
        log_header = QHBoxLayout()
        log_header.addWidget(section_label("Журнал"))
        log_header.addStretch()
        clear_btn = IconButton("trash", "Очистить журнал", size=24, icon_size=13)
        log_header.addWidget(clear_btn)
        log_lay.addLayout(log_header)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(self.LOG_HEIGHT)
        self.log_box.setStyleSheet("""
            QTextEdit {
                background-color: rgba(0, 0, 0, 70);
                color: #D5F5E3;
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 35);
                font-family: Consolas, monospace;
                font-size: 11px;
                padding: 4px;
            }
            QScrollBar:vertical { background: transparent; width: 8px; margin: 4px 2px; }
            QScrollBar::handle:vertical { background: rgba(255,255,255,60); border-radius: 3px; min-height: 20px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)
        clear_btn.clicked.connect(self.log_box.clear)
        log_lay.addWidget(self.log_box)
        lay.addWidget(self.log_panel)

    def _build_header(self):
        header = QHBoxLayout()
        header.setSpacing(6)

        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(QSize(34, 34)))
        header.addWidget(logo)
        header.addSpacing(4)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel(
            f"{APP_NAME} <span style='font-size:10px; font-weight:600; color:rgba(255,255,255,150);'>"
            f"v{APP_VERSION}</span>"
        )
        title.setStyleSheet("color: white; font-size: 16px; font-weight: 700;")
        subtitle = QLabel("Переключатель терминалов")
        subtitle.setStyleSheet("color: rgba(255,255,255,140); font-size: 11px;")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch()

        self.refresh_btn = IconButton("refresh", "Обновить статус трафика (F5)")
        self.refresh_btn.clicked.connect(lambda: self._run_action("usage"))
        self.gear_btn = IconButton("settings", "Настройки (Ctrl+,)")
        self.gear_btn.clicked.connect(self._open_settings)
        self.close_btn = IconButton("close", "Свернуть в трей (Esc)")
        self.close_btn.clicked.connect(self._hide_to_tray)

        for btn in (self.refresh_btn, self.gear_btn, self.close_btn):
            header.addWidget(btn)
        return header

    def _build_status_card(self):
        card = QFrame()
        card.setObjectName("statusCard")
        card.setStyleSheet("""
            #statusCard {
                background-color: rgba(255, 255, 255, 22);
                border: 1px solid rgba(255, 255, 255, 38);
                border-radius: 14px;
            }
        """)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(10)

        self.status_dot = StatusDot()
        lay.addWidget(self.status_dot)

        col = QVBoxLayout()
        col.setSpacing(1)
        self.status_title = ElidedLabel()
        self.status_detail = ElidedLabel()
        self.status_detail.setStyleSheet("color: rgba(255,255,255,150); font-size: 11px;")
        col.addWidget(self.status_title)
        col.addWidget(self.status_detail)
        lay.addLayout(col, stretch=1)

        self.status_time = QLabel()
        self.status_time.setStyleSheet("color: rgba(255,255,255,110); font-size: 10px;")
        self.status_time.setAlignment(Qt.AlignRight | Qt.AlignTop)
        lay.addWidget(self.status_time)
        return card

    def _build_tray(self):
        self.tray = QSystemTrayIcon(icons.app_icon(), self)
        self.tray.setToolTip(APP_TITLE)

        menu = QMenu(self)
        menu.setStyleSheet(MENU_QSS)
        self.act_show = QAction(icons.icon("window"), "Показать окно", self)
        self.act_show.triggered.connect(self._toggle_window)
        self.tray_actions = {}
        for key, info in TERMINALS.items():
            act = QAction(icons.icon(info["icon"], info["accent"]), info["label"], self)
            act.triggered.connect(lambda _=False, k=key: self._run_action(k))
            self.tray_actions[key] = act
        act_off = QAction(icons.icon("power", "#FCA5A5"), "Отключить", self)
        act_off.triggered.connect(lambda: self._run_action("disconnect"))
        self.tray_actions["disconnect"] = act_off
        act_usage = QAction(icons.icon("refresh"), "Обновить трафик", self)
        act_usage.triggered.connect(lambda: self._run_action("usage"))
        self.tray_actions["usage"] = act_usage
        act_quit = QAction(icons.icon("close"), "Выход", self)
        act_quit.triggered.connect(self._quit_app)

        menu.addAction(self.act_show)
        menu.addSeparator()
        for key in ("starlink", "vsat", "disconnect", "usage"):
            menu.addAction(self.tray_actions[key])
        menu.addSeparator()
        menu.addAction(act_quit)
        menu.aboutToShow.connect(
            lambda: self.act_show.setText("Скрыть окно" if self.isVisible() else "Показать окно")
        )

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _build_shortcuts(self):
        QShortcut(QKeySequence("F5"), self, activated=lambda: self._run_action("usage"))
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self._open_settings)
        QShortcut(QKeySequence("Esc"), self, activated=self._hide_to_tray)

    # ---- Окно и трей ----

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self._toggle_window()

    def _toggle_window(self):
        if self.isVisible() and not self.isMinimized():
            self._hide_to_tray()
        else:
            self._show_window()

    def _show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _hide_to_tray(self):
        self._save_position()
        self.hide()
        if not self._tray_hint_shown:
            self._tray_hint_shown = True
            self.tray.showMessage(APP_NAME, "Приложение работает в трее", icons.app_icon(), 2000)

    def _quit_app(self):
        settings_store.save_credentials(ts.USERNAME, ts.PASSWORD)
        self._save_position()
        if self.worker is not None and self.worker.isRunning():
            self.worker.wait(3000)
        self.tray.hide()
        QApplication.instance().quit()

    def _save_position(self):
        if self.isVisible():
            pos = self.pos()
            settings_store.set_setting("window_pos", f"{pos.x()},{pos.y()}")

    def _restore_position(self):
        raw = settings_store.get_setting("window_pos")
        if not raw:
            return
        try:
            x, y = (int(v) for v in raw.split(","))
        except ValueError:
            return
        # Не восстанавливаем позицию за пределами экранов (например, отключили монитор)
        if QGuiApplication.screenAt(QPoint(x + 80, y + 60)) is not None:
            self.move(x, y)

    # ---- Настройки ----

    def _open_settings(self):
        if not self.isVisible():
            self._show_window()
        dialog = SettingsDialog(
            self, ts.USERNAME, ts.PASSWORD, self._show_log_pref, self._save_settings
        )
        dialog.exec()
        drop_hover_state(self.gear_btn, self.refresh_btn, self.btn_disconnect, *self.terminal_buttons.values())

    def _save_settings(self, username, password, show_log):
        credentials_changed = (username != ts.USERNAME) or (password != ts.PASSWORD)
        ts.USERNAME = username
        ts.PASSWORD = password
        settings_store.save_credentials(username, password)

        if credentials_changed:
            # Старые cookies больше не годятся для нового пользователя -
            # начинаем с чистой сессии, чтобы не ловить 500 из-за конфликта.
            self.session = ts.create_session()
            self._set_active_terminal(None)
            self._append_log("Логин/пароль изменены - сессия сброшена.")

        self._show_log_pref = show_log
        settings_store.set_bool("show_log", show_log)
        self._apply_log_visibility(show_log)
        self._append_log("Настройки сохранены.")

    def _apply_log_visibility(self, show_log):
        self.log_panel.setVisible(show_log)

    # ---- Отрисовка и перетаскивание ----

    def paintEvent(self, event):
        paint_glass_card(QPainter(self), self.rect(), self.MARGIN, self.RADIUS)

    def mousePressEvent(self, event):
        # Нативное перемещение: работает прилипание к краям экрана (Aero Snap)
        if event.button() == Qt.LeftButton and self.windowHandle():
            self.windowHandle().startSystemMove()

    def closeEvent(self, event):
        # Сворачивание в трей вместо закрытия
        event.ignore()
        self._hide_to_tray()

    # ---- Журнал ----

    def _append_log(self, text, level="info"):
        color = {"info": "#D5F5E3", "ok": "#86EFAC", "error": "#FCA5A5"}.get(level, "#D5F5E3")
        self.log_box.append(
            f'<span style="color:#7C8DB5">[{now_hms()}]</span> '
            f'<span style="color:{color}">{html.escape(text)}</span>'
        )

    # ---- Статус ----

    def _set_status(self, level, title, detail=""):
        color = STATUS_COLORS.get(level, STATUS_COLORS["neutral"])
        title_color = color if level in ("ok", "warn", "error") else "#FFFFFF"
        self.status_dot.set_state(color, pulsing=(level == "busy"))
        self.status_title.setStyleSheet(f"color: {title_color}; font-size: 14px; font-weight: 700;")
        self.status_title.setText(title)
        self.status_detail.setText(detail)
        self.status_time.setText(now_hm())

        if level != "busy":
            self._last_status = (level, title, detail)
            tray_color = color if level in ("ok", "warn", "error") else None
            self.tray.setIcon(icons.app_icon(tray_color))
            self.tray.setToolTip(f"{APP_TITLE}\n{title}")

    def _set_active_terminal(self, key):
        self._active_terminal = key
        for k, btn in self.terminal_buttons.items():
            btn.set_active(k == key)

    def _notify_if_hidden(self, title, message, error=False):
        # Действие запущено из меню трея - показываем результат уведомлением
        if not self.isVisible():
            kind = QSystemTrayIcon.Warning if error else QSystemTrayIcon.Information
            self.tray.showMessage(title, message, kind, 3000)

    # ---- Запуск действия ----

    def _set_busy(self, busy, action=None):
        for w in (*self.terminal_buttons.values(), self.btn_disconnect, self.refresh_btn):
            w.setEnabled(not busy)
        for act in self.tray_actions.values():
            act.setEnabled(not busy)
        self.refresh_btn.set_spinning(busy)
        if busy and not self._quiet_run:
            self._set_status("busy", ACTION_TEXT.get(action, "Выполняю…"), "Ожидаю ответ панели")

    def _auto_refresh(self):
        if self.worker is None:
            self._run_action("usage", quiet=True)

    def _run_action(self, action, quiet=False):
        if self.worker is not None:
            return  # предыдущий запрос ещё не завершился
        self._quiet_run = quiet
        self._set_busy(True, action)
        self._append_log(f"Автообновление: {action}" if quiet else f"Действие: {action}")

        worker = Worker(action, self.session)
        worker.log.connect(self._append_log)
        worker.succeeded.connect(self._on_success)
        worker.failed.connect(self._on_failure)
        worker.finished.connect(self._on_worker_finished)
        self.worker = worker
        worker.start()

    def _on_worker_finished(self):
        self._set_busy(False)
        self._quiet_run = False
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None

    def _on_success(self, action, payload):
        if action == "usage":
            self._on_usage(payload)
            return

        # Цифры трафика относились к прошлому подключению - сбрасываем
        for tile in self.stat_tiles.values():
            tile.set_value(None)
        self.usage_caption.setText(AUTO_CAPTION)
        if action == "disconnect":
            self._set_active_terminal(None)
            self._set_status("warn", "Отключено", f"Сессия завершена в {now_hm()}")
            self._append_log("Сессия завершена.", "ok")
            self._notify_if_hidden(APP_NAME, "Отключено")
        else:
            label = TERMINALS[action]["label"]
            self._set_active_terminal(action)
            self._set_status("ok", f"Активен: {label}", f"Подключено в {now_hm()}")
            self._append_log(f"Активен терминал {label}.", "ok")
            self._notify_if_hidden(APP_NAME, f"Активен: {label}")
            self._limit_reminded = False
            self.auto_timer.start()  # отсчёт 10 минут заново
            QTimer.singleShot(3000, self._auto_refresh)  # сразу узнаём остаток времени

    def _on_failure(self, action, message):
        self._append_log(f"ОШИБКА: {message}", "error")
        if self._quiet_run:
            # Фоновое обновление не дёргает статус и не шлёт уведомления каждые 10 минут
            self.usage_caption.setText(f"ошибка в {now_hm()}")
            return
        if action == "usage":
            level, title, _ = self._last_status
            self._set_status(level, title, f"Трафик не получен: {message}")
            self.usage_caption.setText("ошибка запроса")
        else:
            self._set_status("error", "Ошибка", message)
        self._notify_if_hidden(f"{APP_NAME}: ошибка", message, error=True)

    def _on_usage(self, data):
        level, title, detail = self._last_status
        if all(v == "?" for v in data.values()):
            for tile in self.stat_tiles.values():
                tile.set_value(None)
            self.usage_caption.setText("нет данных")
            self._set_status(level, title, "Нет данных о трафике - возможно, нужно сначала подключиться")
            return
        for key, tile in self.stat_tiles.items():
            tile.set_value(data.get(key))
        self.usage_caption.setText(f"обновлено в {now_hm()}")
        self._set_status(level, title, detail)
        self._check_limit(data.get("remaining_time"))

    def _check_limit(self, remaining):
        minutes = ts.remaining_minutes(remaining)
        low = minutes is not None and minutes <= REMIND_MINUTES
        self.stat_tiles["remaining_time"].set_alert(low)
        if not low:
            self._limit_reminded = False
            return
        if self._limit_reminded:
            return
        self._limit_reminded = True
        left = max(0, round(minutes))
        text = f"До конца дневного лимита осталось {left} мин"
        self._append_log(text, "error")
        level, title, _ = self._last_status
        self._set_status(level, title, text)
        self.tray.showMessage(f"{APP_NAME}: заканчивается лимит", text, QSystemTrayIcon.Warning, 10000)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setQuitOnLastWindowClosed(False)  # не закрываться при скрытии окна в трей
    font = QFont("Segoe UI")
    font.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(font)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
