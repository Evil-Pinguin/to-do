# -*- coding: utf-8 -*-
"""Отрисовка «пузырькового» стекла в духе assets/backdrop.jpg.

Стиль срисован с мыльных пузырей на обоях:

1. Тело почти прозрачное и светлеет к центру — стекло читается не заливкой.
2. Вместо жёсткого контура — мягкий «рим» (кольцо преломления): цвет
   сгущается и холоднеет к краю, как у линзы.
3. Двойной блик: широкий мягкий полумесяц вдоль верхней дуги + маленькая
   яркая искра с крестообразным глинтом (свет — слева-сверху, как солнце
   на картинке).
4. Нижний рефлекс не белый, а цветной — стекло «подбирает» оттенок
   окружения (небо/трава: циан-мятный).
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient,
)

# Оттенок окружения для нижнего рефлекса (небо у горизонта + трава).
_ENV_REFLEX = (191, 231, 226)
# Холодный тон кромки-линзы (взят с края пузыря: #BDE4EB, чуть темнее).
_RIM_COOL = (125, 170, 195)


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def paint_bubble_glass(
    p: QPainter,
    rect: QRectF,
    radius: float,
    base_rgb: tuple[int, int, int] = (255, 255, 255),
    body_alpha: int = 150,
    hover: bool = False,
    sparkle: bool = True,
    reflex_alpha: int = 55,
) -> None:
    """Нарисовать стеклянную «пузырьковую» плашку в *rect*.

    ``body_alpha`` — плотность тела в центре (0–255); края всегда чуть
    плотнее и холоднее за счёт рима.
    """
    p.setRenderHint(QPainter.Antialiasing)

    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)

    r_, g_, b_ = base_rgb

    # ---- 1. Тело: светлое в центре, чуть плотнее к низу -------------------
    body = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    lite = _mix(base_rgb, (255, 255, 255), 0.30)
    body.setColorAt(0.0, QColor(r_, g_, b_, body_alpha))
    body.setColorAt(0.45, QColor(lite[0], lite[1], lite[2], max(0, body_alpha - 22)))
    body.setColorAt(1.0, QColor(r_, g_, b_, min(255, body_alpha + 18)))
    p.fillPath(path, body)

    p.save()
    p.setClipPath(path)

    # ---- 2. Рим — мягкое кольцо преломления вместо жёсткой рамки ----------
    rim = _mix(base_rgb, _RIM_COOL, 0.55)
    for width, alpha in ((7.0, 22), (4.5, 32), (2.4, 46)):
        p.setPen(QPen(QColor(rim[0], rim[1], rim[2], alpha), width))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

    # ---- 3. Блик-полумесяц вдоль верхней дуги (свет слева-сверху) ---------
    ew = rect.width() * 1.25
    eh = rect.height() * 0.62
    crescent = QPainterPath()
    crescent.addEllipse(QRectF(rect.x() - ew * 0.14, rect.y() - eh * 0.42, ew, eh))
    crescent = crescent.intersected(path)
    shine = QLinearGradient(rect.topLeft(), QPointF(rect.x(), rect.y() + eh * 0.58))
    shine.setColorAt(0.0, QColor(255, 255, 255, 135))
    shine.setColorAt(0.55, QColor(255, 255, 255, 45))
    shine.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillPath(crescent, shine)

    # ---- 4. Искра с глинтом в левом верхнем углу ---------------------------
    if sparkle:
        cx = rect.x() + radius * 1.15
        cy = rect.y() + radius * 1.05
        srad = max(7.0, min(rect.width(), rect.height()) * 0.075)
        srad = min(srad, 15.0)

        halo = QRadialGradient(QPointF(cx, cy), srad * 2.2)
        halo.setColorAt(0.0, QColor(255, 255, 255, 165))
        halo.setColorAt(0.45, QColor(255, 255, 255, 55))
        halo.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(halo)
        p.drawEllipse(QPointF(cx, cy), srad * 2.2, srad * 2.2)

        # крестообразный глинт — две вытянутые «полоски света»
        for w, h in ((srad * 3.4, srad * 0.5), (srad * 0.5, srad * 3.4)):
            g = QRadialGradient(QPointF(cx, cy), max(w, h) / 2)
            g.setColorAt(0.0, QColor(255, 255, 255, 195))
            g.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setBrush(g)
            p.drawEllipse(QPointF(cx, cy), w / 2, h / 2)

        core = QRadialGradient(QPointF(cx, cy), srad * 0.8)
        core.setColorAt(0.0, QColor(255, 255, 255, 235))
        core.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(core)
        p.drawEllipse(QPointF(cx, cy), srad * 0.8, srad * 0.8)

    # ---- 5. Нижний рефлекс — цветной, от окружения -------------------------
    env = _mix(_ENV_REFLEX, base_rgb, 0.35)
    ref_h = rect.height() * 0.24
    ref_rect = QRectF(rect.x(), rect.bottom() - ref_h, rect.width(), ref_h)
    ref = QLinearGradient(ref_rect.topLeft(), ref_rect.bottomLeft())
    ref.setColorAt(0.0, QColor(env[0], env[1], env[2], 0))
    ref.setColorAt(0.7, QColor(env[0], env[1], env[2], int(reflex_alpha * 0.6)))
    ref.setColorAt(1.0, QColor(255, 255, 255, reflex_alpha))
    p.fillPath(path, ref)

    # ---- 6. Hover — лёгкое общее свечение ----------------------------------
    if hover:
        p.fillPath(path, QColor(255, 255, 255, 28))

    p.restore()

    # ---- 7. Внешний контур — тонкий и мягкий (не «рамка») ------------------
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 165), 1.0))
    p.drawPath(path)
