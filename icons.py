"""
Векторные иконки VSAT STAR S/W.

Все иконки генерируются прямо в коде (SVG-разметка + QPainter) - никаких
внешних файлов и эмодзи. Рисуются в сетке 24x24 линиями со скруглёнными
концами, поэтому одинаково чётко выглядят на любом размере и любом DPI.
"""

import math
from functools import lru_cache

from PySide6.QtCore import Qt, QByteArray, QRectF, QPointF
from PySide6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QLinearGradient, QPainterPath, QPen,
)
from PySide6.QtSvg import QSvgRenderer


def _gear_outline(teeth=8, root=7.0, tip=9.6):
    """Контур шестерёнки: для каждого зуба 4 точки (основание - вершина - вершина - основание)."""
    points = []
    for i in range(teeth):
        center = i * 360 / teeth
        for offset, radius in ((-15, root), (-8, tip), (8, tip), (15, root)):
            angle = math.radians(center + offset)
            points.append(f"{12 + radius * math.cos(angle):.2f} {12 + radius * math.sin(angle):.2f}")
    return "M" + " L".join(points) + "Z"


_EYE = '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="3"/>'

# "currentColor" подменяется на нужный цвет при отрисовке.
_SHAPES = {
    # Спутник: корпус-ромб, две солнечные панели и волны сигнала.
    "satellite": (
        '<path d="M12 8.6 15.4 12 12 15.4 8.6 12Z" fill="currentColor" fill-opacity=".25"/>'
        '<path d="M6.5 3.4 9.6 6.5 6.5 9.6 3.4 6.5Z"/><path d="M8 5 5 8"/>'
        '<path d="M17.5 14.4 20.6 17.5 17.5 20.6 14.4 17.5Z"/><path d="M19 16 16 19"/>'
        '<path d="M8.05 8.05 10.3 10.3M13.7 13.7 15.95 15.95"/>'
        '<path d="M3.2 14.5a6.5 6.5 0 0 0 6.3 6.3"/><path d="M6 15a3.2 3.2 0 0 0 3 3"/>'
    ),
    # Спутниковая тарелка (VSAT): чаша, облучатель и волны.
    "dish": (
        '<path d="M4.5 9.5a7.1 7.1 0 0 0 10 10Z" fill="currentColor" fill-opacity=".25"/>'
        '<path d="M9.5 14.5 13 11"/><circle cx="13.3" cy="10.7" r="1.1" fill="currentColor"/>'
        '<path d="M17 11a4 4 0 0 0-4-4"/><path d="M20.5 11a7.5 7.5 0 0 0-7.5-7.5"/>'
    ),
    "power": '<path d="M12 3.5v8"/><path d="M7 6.3a7.5 7.5 0 1 0 10 0"/>',
    "refresh": (
        '<path d="M4 12a8 8 0 0 1 13.66-5.66"/><path d="M18 2.5v4h-4"/>'
        '<path d="M20 12a8 8 0 0 1-13.66 5.66"/><path d="M6 21.5v-4h4"/>'
    ),
    "settings": f'<path d="{_gear_outline()}"/><circle cx="12" cy="12" r="3"/>',
    "close": '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
    "download": '<path d="M12 4v11"/><path d="m7.5 10.5 4.5 4.5 4.5-4.5"/><path d="M5 20h14"/>',
    "upload": '<path d="M12 15V4"/><path d="m7.5 8.5 4.5-4.5 4.5 4.5"/><path d="M5 20h14"/>',
    "database": (
        '<ellipse cx="12" cy="5.5" rx="7.5" ry="2.5"/>'
        '<path d="M4.5 5.5v13c0 1.38 3.36 2.5 7.5 2.5s7.5-1.12 7.5-2.5v-13"/>'
        '<path d="M4.5 12c0 1.38 3.36 2.5 7.5 2.5s7.5-1.12 7.5-2.5"/>'
    ),
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4.5 20.5a7.5 7.5 0 0 1 15 0"/>',
    "lock": '<rect x="5" y="10.5" width="14" height="10" rx="2.5"/><path d="M8.5 10.5V7.5a3.5 3.5 0 0 1 7 0v3"/>',
    "eye": _EYE,
    "eye-off": _EYE + '<path d="M4 4l16 16"/>',
    "trash": '<path d="M4 7h16"/><path d="M9.5 7V4.5h5V7"/><path d="M6.5 7l1 13h9l1-13"/>',
    "terminal": '<rect x="3" y="4.5" width="18" height="15" rx="2.5"/><path d="m7.5 9.5 3 2.5-3 2.5"/><path d="M13 15h3.5"/>',
    "window": '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path d="M3.5 9h17"/>',
    "shield": '<path d="M12 3 5 6v5c0 4.5 3 8.2 7 10 4-1.8 7-5.5 7-10V6Z"/><path d="m9 12 2 2 4-4"/>',
}

_SVG_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" '
    'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
)

# Набор размеров, из которых QIcon подбирает подходящий (с учётом HiDPI).
_ICON_SIZES = (16, 18, 20, 24, 28, 32, 36, 40, 48, 56, 64, 72, 96, 128)


@lru_cache(maxsize=256)
def _svg_bytes(name, color, stroke):
    body = _SHAPES[name].replace("currentColor", color)
    return _SVG_TEMPLATE.format(color=color, stroke=stroke, body=body).encode("utf-8")


def render(painter, rect, name, color="#FFFFFF", stroke=1.8):
    """Рисует иконку name в прямоугольнике rect на уже открытом QPainter."""
    QSvgRenderer(QByteArray(_svg_bytes(name, color, stroke))).render(painter, QRectF(rect))


@lru_cache(maxsize=1024)
def pixmap(name, size, color="#FFFFFF", dpr=1.0, stroke=1.8, opacity=1.0):
    side = max(1, round(size * dpr))
    pm = QPixmap(side, side)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setOpacity(opacity)
    render(p, QRectF(0, 0, side, side), name, color, stroke)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


@lru_cache(maxsize=256)
def icon(name, color="#FFFFFF", stroke=1.8):
    """QIcon с обычным и приглушённым (disabled) состоянием."""
    ic = QIcon()
    for size in _ICON_SIZES:
        ic.addPixmap(pixmap(name, size, color, 1.0, stroke), QIcon.Normal)
        ic.addPixmap(pixmap(name, size, color, 1.0, stroke, 0.4), QIcon.Disabled)
    return ic


# ---------- Иконка приложения (окно / трей) ----------

def app_pixmap(size, status_color=None, dpr=1.0):
    """Скруглённый градиентный квадрат со спутником; опционально - точка статуса."""
    side = max(1, round(size * dpr))
    pm = QPixmap(side, side)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    pad = side * 0.04
    rect = QRectF(pad, pad, side - 2 * pad, side - 2 * pad)
    radius = side * 0.26
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)

    grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0.0, QColor(46, 58, 160))
    grad.setColorAt(0.55, QColor(112, 62, 196))
    grad.setColorAt(1.0, QColor(26, 150, 206))
    p.fillPath(path, grad)

    gloss = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.center().y()))
    gloss.setColorAt(0.0, QColor(255, 255, 255, 70))
    gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillPath(path, gloss)

    inset = side * 0.17
    render(p, rect.adjusted(inset, inset, -inset, -inset), "satellite", "#FFFFFF", 2.1)

    if status_color:
        r = side * 0.19
        center = QPointF(side - r - pad * 0.5, side - r - pad * 0.5)
        p.setPen(QPen(QColor(20, 24, 64), max(1.0, side * 0.06)))
        p.setBrush(QColor(status_color))
        p.drawEllipse(center, r, r)

    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


@lru_cache(maxsize=16)
def app_icon(status_color=None):
    ic = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        ic.addPixmap(app_pixmap(size, status_color))
    return ic
