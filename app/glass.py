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

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen,
    QPixmap, QRadialGradient,
)

from . import ambient, theme

# Оттенок окружения для нижнего рефлекса (по умолчанию; живой берём из ambient).
_ENV_REFLEX = (191, 231, 226)

# ----------------------------------------------------------------------------
#  Frosted: шум и «честный» backdrop-blur
# ----------------------------------------------------------------------------
_NOISE_TILE: QPixmap | None = None


def _noise_tile() -> QPixmap:
    """Мелкий полупрозрачный шум — убирает «пластиковость» стекла."""
    global _NOISE_TILE
    if _NOISE_TILE is None:
        import random
        rnd = random.Random(42)
        img = QImage(96, 96, QImage.Format_ARGB32)
        img.fill(0)
        for y in range(96):
            for x in range(96):
                v = rnd.randint(0, 255)
                if v > 128:
                    img.setPixelColor(x, y, QColor(255, 255, 255, (v - 128) // 11))
                else:
                    img.setPixelColor(x, y, QColor(0, 0, 30, (128 - v) // 13))
        _NOISE_TILE = QPixmap.fromImage(img)
    return _NOISE_TILE


def draw_frosted_backdrop(p: QPainter, path: QPainterPath, widget) -> bool:
    """Подложить под стекло размытый кусок фона (аналог backdrop-filter).

    Окно виджета должно реализовать ``frosted_backdrop() -> (QPixmap, QPoint)``
    — размытый снимок фона и его начало в координатах окна.
    """
    if widget is None:
        return False
    win = widget.window()
    fn = getattr(win, "frosted_backdrop", None)
    if fn is None:
        return False
    try:
        res = fn()
    except Exception:
        return False
    if not res:
        return False
    pm, origin = res
    if pm is None or pm.isNull():
        return False
    off = widget.mapTo(win, QPoint(0, 0)) - origin
    p.save()
    p.setClipPath(path)
    p.drawPixmap(-off.x(), -off.y(), pm)
    p.restore()
    return True


def blur_pixmap(src: QPixmap, strength: int = 14) -> QPixmap:
    """Дешёвый сильный blur: уменьшить → увеличить с smooth-фильтрацией."""
    if src.isNull():
        return src
    w = max(1, src.width() // strength)
    h = max(1, src.height() // strength)
    small = src.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    # двойной проход даёт более гладкий результат
    small = small.scaled(max(1, w * 2), max(1, h * 2),
                         Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return small.scaled(src.width(), src.height(),
                        Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
# Холодный тон кромки-линзы (взят с края пузыря: #BDE4EB, чуть темнее).
_RIM_COOL = (125, 170, 195)


def _env_reflex() -> tuple[int, int, int]:
    """Цвет рефлекса из текущего времени суток."""
    return ambient.palette()["reflex"]


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _paint_minimal_rect(
    p: QPainter,
    rect: QRectF,
    radius: float,
    rgb: tuple[int, int, int],
    alpha: int,
    hover: bool = False,
) -> None:
    """Плашка в стиле минимализма: плоская, белая, волосяная граница."""
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    p.fillPath(path, QColor(rgb[0], rgb[1], rgb[2], alpha))
    if hover:
        p.fillPath(path, QColor(0, 0, 0, 8))
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(0, 0, 0, 26), 1.0))
    p.drawPath(path)


def _paint_frosted_rect(
    p: QPainter,
    rect: QRectF,
    radius: float,
    tint_rgb: tuple[int, int, int] | None = None,
    milk: int = 52,
    hover: bool = False,
    glow_pos: "QPointF | None" = None,
    widget=None,
) -> None:
    """Liquid Glass: размытый фон под стеклом + тонкий светлый слой,
    спекулярный блик, шум и светящаяся кромка.

    Если окно предоставляет размытый фон (см. draw_frosted_backdrop),
    тело стекла почти прозрачное; иначе — плотный молочный fallback.
    """
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)

    has_backdrop = draw_frosted_backdrop(p, path, widget)
    if has_backdrop:
        # тонкий слой стекла: 25% → 8% как в референсе
        body = QLinearGradient(rect.topLeft(), rect.bottomRight())
        body.setColorAt(0.0, QColor(255, 255, 255, 64))
        body.setColorAt(1.0, QColor(255, 255, 255, 20))
        p.fillPath(path, body)
    else:
        body = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        body.setColorAt(0.0, QColor(255, 255, 255, milk + 14))
        body.setColorAt(1.0, QColor(255, 255, 255, milk))
        p.fillPath(path, body)
    if tint_rgb is not None:
        p.fillPath(path, QColor(tint_rgb[0], tint_rgb[1], tint_rgb[2], 26))

    p.save()
    p.setClipPath(path)
    # спекулярный блик: яркий из левого-верхнего угла, слабый в правом-нижнем
    spec = QLinearGradient(rect.topLeft(), rect.bottomRight())
    spec.setColorAt(0.00, QColor(255, 255, 255, 88))
    spec.setColorAt(0.30, QColor(255, 255, 255, 0))
    spec.setColorAt(0.70, QColor(255, 255, 255, 0))
    spec.setColorAt(1.00, QColor(255, 255, 255, 30))
    p.fillPath(path, spec)
    # верхняя внутренняя световая нить (inset 0 1px)
    p.setPen(QPen(QColor(255, 255, 255, 120), 1.0))
    p.drawLine(QPointF(rect.x() + radius * 0.7, rect.y() + 1.0),
               QPointF(rect.right() - radius * 0.7, rect.y() + 1.0))
    p.setPen(Qt.NoPen)
    # лёгкий шум — стекло, а не пластик
    p.setOpacity(0.55)
    p.fillPath(path, QBrush(_noise_tile()))
    p.setOpacity(1.0)
    if hover:
        p.fillPath(path, QColor(255, 255, 255, 20))
    if glow_pos is not None:
        glow = QRadialGradient(glow_pos, max(rect.width(), rect.height()) * 0.45)
        glow.setColorAt(0.0, QColor(255, 255, 255, 36))
        glow.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, glow)
    p.restore()

    # тонкая светящаяся кромка
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 96), 1.0))
    p.drawPath(path)


def paint_bubble_glass(
    p: QPainter,
    rect: QRectF,
    radius: float,
    base_rgb: tuple[int, int, int] = (255, 255, 255),
    body_alpha: int = 150,
    hover: bool = False,
    sparkle: bool = True,
    reflex_alpha: int = 55,
    widget=None,
) -> None:
    """Нарисовать стеклянную «пузырьковую» плашку в *rect*.

    ``body_alpha`` — плотность тела в центре (0–255); края всегда чуть
    плотнее и холоднее за счёт рима.
    """
    p.setRenderHint(QPainter.Antialiasing)

    if theme.is_minimal():
        _paint_minimal_rect(p, rect, radius, (255, 255, 255), 246)
        return
    if theme.is_frosted():
        if body_alpha >= 160:
            # диалоги/редактор: плотное молочное стекло — тёмный текст читается
            _paint_frosted_rect(p, rect, radius, milk=205, widget=widget)
        else:
            # панели: настоящее стекло — размытый фон просвечивает
            _paint_frosted_rect(p, rect, radius, milk=30, widget=widget)
        return

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
    for width, alpha in ((8.0, 26), (5.0, 38), (2.6, 54)):
        p.setPen(QPen(QColor(rim[0], rim[1], rim[2], alpha), width))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

    # ---- 2b. Диагональный луч света — как лучи солнца на обоях ------------
    sheen = QLinearGradient(rect.topRight(), rect.bottomLeft())
    sheen.setColorAt(0.00, QColor(255, 255, 255, 0))
    sheen.setColorAt(0.40, QColor(255, 255, 255, 0))
    sheen.setColorAt(0.50, QColor(255, 255, 255, 26))
    sheen.setColorAt(0.60, QColor(255, 255, 255, 0))
    sheen.setColorAt(1.00, QColor(255, 255, 255, 0))
    p.fillPath(path, sheen)

    # ---- 3. Блик-полумесяц вдоль верхней дуги (свет слева-сверху) ---------
    ew = rect.width() * 1.25
    eh = rect.height() * 0.62
    crescent = QPainterPath()
    crescent.addEllipse(QRectF(rect.x() - ew * 0.14, rect.y() - eh * 0.42, ew, eh))
    crescent = crescent.intersected(path)
    shine = QLinearGradient(rect.topLeft(), QPointF(rect.x(), rect.y() + eh * 0.58))
    shine.setColorAt(0.0, QColor(255, 255, 255, 150))
    shine.setColorAt(0.55, QColor(255, 255, 255, 52))
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
    env = _mix(_env_reflex(), base_rgb, 0.35)
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


def paint_bubble_card(
    p: QPainter,
    rect: QRectF,
    radius: float,
    base_rgb: tuple[int, int, int],
    hover: bool = False,
    glow_pos: "QPointF | None" = None,
    widget=None,
) -> None:
    """Прямоугольный «мыльный пузырь» — как paint_bubble_circle, но для карточек.

    Центр почти прозрачный (линза), цвет заметки сконцентрирован у краёв,
    как плёнка пузыря; рим, полумесяц, искра и цветной рефлекс — те же.
    ``glow_pos`` — позиция курсора: мягкое свечение следует за мышью.
    """
    p.setRenderHint(QPainter.Antialiasing)

    if theme.is_minimal():
        # Минимализм: белая карточка с еле заметным тоном цвета заметки,
        # волосяная граница — как у Apple.
        tint = _mix((255, 255, 255), base_rgb, 0.10)
        _paint_minimal_rect(p, rect, 12.0, tint, 255, hover=hover)
        return
    if theme.is_frosted():
        # Frosted: размытый фон под стеклом, цвет заметки — лёгкий оттенок
        _paint_frosted_rect(p, rect, radius, tint_rgb=base_rgb,
                            milk=48, hover=hover, glow_pos=glow_pos,
                            widget=widget)
        return

    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    r_, g_, b_ = base_rgb

    # ---- 1. Центр: лёгкая дымка (читаемость текста) + едва заметный тон ----
    # ночью дымка плотнее, чтобы тёмный текст читался на тёмном фоне
    boost = ambient.palette()["haze_boost"]
    haze = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    haze.setColorAt(0.0, QColor(255, 255, 255, min(255, 60 + boost)))
    haze.setColorAt(0.5, QColor(255, 255, 255, min(255, 44 + boost)))
    haze.setColorAt(1.0, QColor(255, 255, 255, min(255, 56 + boost)))
    p.fillPath(path, haze)
    p.fillPath(path, QColor(r_, g_, b_, 34))

    p.save()
    p.setClipPath(path)

    # ---- 2. Цветная «плёнка» — цвет сгущается к краям, центр прозрачный ----
    for width, alpha in ((radius * 2.6, 30), (radius * 1.5, 42), (radius * 0.7, 58)):
        p.setPen(QPen(QColor(r_, g_, b_, alpha), width))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

    # ---- 3. Рим-кромка (холодное кольцо преломления) ------------------------
    rim = _mix(base_rgb, _RIM_COOL, 0.60)
    for width, alpha in ((6.5, 34), (3.8, 48), (1.8, 66)):
        p.setPen(QPen(QColor(rim[0], rim[1], rim[2], alpha), width))
        p.drawPath(path)

    # ---- 4. Диагональный луч света ------------------------------------------
    sheen = QLinearGradient(rect.topRight(), rect.bottomLeft())
    sheen.setColorAt(0.00, QColor(255, 255, 255, 0))
    sheen.setColorAt(0.40, QColor(255, 255, 255, 0))
    sheen.setColorAt(0.50, QColor(255, 255, 255, 30))
    sheen.setColorAt(0.60, QColor(255, 255, 255, 0))
    sheen.setColorAt(1.00, QColor(255, 255, 255, 0))
    p.fillPath(path, sheen)

    # ---- 5. Блик-полумесяц вдоль верхней дуги --------------------------------
    ew = rect.width() * 1.25
    eh = rect.height() * 0.60
    crescent = QPainterPath()
    crescent.addEllipse(QRectF(rect.x() - ew * 0.14, rect.y() - eh * 0.42, ew, eh))
    crescent = crescent.intersected(path)
    shine = QLinearGradient(rect.topLeft(), QPointF(rect.x(), rect.y() + eh * 0.58))
    shine.setColorAt(0.0, QColor(255, 255, 255, 170))
    shine.setColorAt(0.55, QColor(255, 255, 255, 58))
    shine.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillPath(crescent, shine)

    # ---- 6. Искра с крестовым глинтом ----------------------------------------
    cx = rect.x() + radius * 1.2
    cy = rect.y() + radius * 1.05
    srad = min(max(7.0, min(rect.width(), rect.height()) * 0.075), 14.0)
    p.setPen(Qt.NoPen)
    halo = QRadialGradient(QPointF(cx, cy), srad * 2.3)
    halo.setColorAt(0.0, QColor(255, 255, 255, 185))
    halo.setColorAt(0.5, QColor(255, 255, 255, 62))
    halo.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(halo)
    p.drawEllipse(QPointF(cx, cy), srad * 2.3, srad * 2.3)
    for w, h in ((srad * 3.5, srad * 0.5), (srad * 0.5, srad * 3.5)):
        g = QRadialGradient(QPointF(cx, cy), max(w, h) / 2)
        g.setColorAt(0.0, QColor(255, 255, 255, 205))
        g.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(g)
        p.drawEllipse(QPointF(cx, cy), w / 2, h / 2)

    # ---- 7. Нижний цветной рефлекс -------------------------------------------
    env = _mix(_env_reflex(), base_rgb, 0.30)
    ref_h = rect.height() * 0.26
    ref_rect = QRectF(rect.x(), rect.bottom() - ref_h, rect.width(), ref_h)
    ref = QLinearGradient(ref_rect.topLeft(), ref_rect.bottomLeft())
    ref.setColorAt(0.0, QColor(env[0], env[1], env[2], 0))
    ref.setColorAt(1.0, QColor(env[0], env[1], env[2], 88))
    p.fillPath(path, ref)

    if hover:
        p.fillPath(path, QColor(255, 255, 255, 22))

    # ---- 7b. Hover-свет: слабое свечение следует за курсором ---------------
    if glow_pos is not None:
        glow = QRadialGradient(glow_pos, max(rect.width(), rect.height()) * 0.45)
        glow.setColorAt(0.0, QColor(255, 255, 255, 44))
        glow.setColorAt(0.4, QColor(255, 255, 255, 16))
        glow.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, glow)

    p.restore()

    # ---- 8. Внешний контур -----------------------------------------------------
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 185), 1.1))
    p.drawPath(path)


def paint_bubble_circle(
    p: QPainter,
    rect: QRectF,
    hover: bool = False,
    pressed: bool = False,
) -> None:
    """Круглый «мыльный пузырь» — максимально близко к пузырям с обоев.

    Тело почти полностью прозрачное (линза: плотнее к краю), рим-кромка,
    полумесяц сверху, искра с глинтом и цветной рефлекс снизу.
    """
    p.setRenderHint(QPainter.Antialiasing)

    if theme.is_minimal():
        # Минимализм: чистый белый круг с волосяной границей
        p.setPen(QPen(QColor(0, 0, 0, 30), 1.0))
        p.setBrush(QColor(255, 255, 255, 252 if not hover else 255))
        p.drawEllipse(rect)
        if pressed:
            p.setBrush(QColor(0, 0, 0, 16))
            p.setPen(Qt.NoPen)
            p.drawEllipse(rect)
        return
    if theme.is_frosted():
        # Frosted: стеклянная линза — radial-градиент со светом из 30%/30%,
        # внутреннее свечение и светлая кромка
        body = QRadialGradient(
            QPointF(rect.x() + rect.width() * 0.30, rect.y() + rect.height() * 0.30),
            rect.width() * 0.85,
        )
        body.setColorAt(0.0, QColor(255, 255, 255, 150 + (25 if hover else 0)))
        body.setColorAt(0.45, QColor(255, 255, 255, 60))
        body.setColorAt(1.0, QColor(255, 255, 255, 16))
        p.setPen(QPen(QColor(255, 255, 255, 110), 1.2))
        p.setBrush(body)
        p.drawEllipse(rect)
        # внутреннее свечение по краю (inset glow)
        inner = QRadialGradient(rect.center(), rect.width() * 0.52)
        inner.setColorAt(0.0, QColor(255, 255, 255, 0))
        inner.setColorAt(0.82, QColor(255, 255, 255, 0))
        inner.setColorAt(1.0, QColor(255, 255, 255, 70))
        p.setPen(Qt.NoPen)
        p.setBrush(inner)
        p.drawEllipse(rect)
        if pressed:
            p.setBrush(QColor(0, 0, 30, 40))
            p.drawEllipse(rect)
        return

    path = QPainterPath()
    path.addEllipse(rect)
    center = rect.center()
    rad = rect.width() / 2.0

    # ---- 1. Тело-линза: прозрачный центр, плотнее к краю -------------------
    body = QRadialGradient(center, rad)
    boost = 26 if hover else 0
    body.setColorAt(0.00, QColor(236, 251, 255, 26 + boost))
    body.setColorAt(0.72, QColor(226, 246, 252, 44 + boost))
    body.setColorAt(0.93, QColor(205, 236, 246, 92 + boost))
    body.setColorAt(1.00, QColor(189, 228, 235, 128 + boost))
    p.fillPath(path, body)

    p.save()
    p.setClipPath(path)

    # ---- 2. Рим-кромка ------------------------------------------------------
    for width, alpha in ((6.0, 42), (3.4, 60), (1.6, 84)):
        p.setPen(QPen(QColor(_RIM_COOL[0], _RIM_COOL[1], _RIM_COOL[2], alpha), width))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(rect.adjusted(0.8, 0.8, -0.8, -0.8))

    # ---- 3. Полумесяц сверху (свет слева-сверху) ---------------------------
    crescent = QPainterPath(path)
    inner = QPainterPath()
    inner.addEllipse(rect.adjusted(rad * 0.16, rad * 0.34, -rad * 0.02, rad * 0.22))
    crescent = crescent.subtracted(inner)
    top_half = QPainterPath()
    top_half.addRect(QRectF(rect.x(), rect.y(), rect.width(), rect.height() * 0.55))
    crescent = crescent.intersected(top_half)
    shine = QLinearGradient(rect.topLeft(), QPointF(rect.x(), center.y()))
    shine.setColorAt(0.0, QColor(255, 255, 255, 205))
    shine.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillPath(crescent, shine)

    # ---- 4. Искра с крестовым глинтом --------------------------------------
    cx = rect.x() + rect.width() * 0.30
    cy = rect.y() + rect.height() * 0.26
    srad = rad * 0.16
    p.setPen(Qt.NoPen)
    halo = QRadialGradient(QPointF(cx, cy), srad * 2.4)
    halo.setColorAt(0.0, QColor(255, 255, 255, 200))
    halo.setColorAt(0.5, QColor(255, 255, 255, 70))
    halo.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(halo)
    p.drawEllipse(QPointF(cx, cy), srad * 2.4, srad * 2.4)
    for w, h in ((srad * 3.6, srad * 0.55), (srad * 0.55, srad * 3.6)):
        g = QRadialGradient(QPointF(cx, cy), max(w, h) / 2)
        g.setColorAt(0.0, QColor(255, 255, 255, 215))
        g.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(g)
        p.drawEllipse(QPointF(cx, cy), w / 2, h / 2)

    # ---- 5. Нижний цветной рефлекс ------------------------------------------
    reflex = QPainterPath(path)
    ref_inner = QPainterPath()
    ref_inner.addEllipse(rect.adjusted(rad * 0.06, -rad * 0.30, -rad * 0.20, -rad * 0.18))
    reflex = reflex.subtracted(ref_inner)
    bottom_half = QPainterPath()
    bottom_half.addRect(QRectF(rect.x(), center.y(), rect.width(), rect.height()))
    reflex = reflex.intersected(bottom_half)
    ref_g = QLinearGradient(QPointF(rect.x(), center.y()), rect.bottomLeft())
    env_c = _env_reflex()
    ref_g.setColorAt(0.0, QColor(env_c[0], env_c[1], env_c[2], 0))
    ref_g.setColorAt(1.0, QColor(env_c[0], env_c[1], env_c[2], 120))
    p.fillPath(reflex, ref_g)

    if pressed:
        p.fillPath(path, QColor(150, 200, 225, 45))

    p.restore()

    # ---- 6. Внешний контур ---------------------------------------------------
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 190), 1.2))
    p.drawEllipse(rect)
