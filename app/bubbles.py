# -*- coding: utf-8 -*-
"""Круглые кнопки-пузыри (плавающие, поверх контента)."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QToolButton, QWidget

from . import theme
from .glass import paint_bubble_circle


class BubbleButton(QToolButton):
    """Плавающая круглая кнопка в виде мыльного пузыря.

    ``glyph``: "plus" — плюсик (создание), "graph" — два кружка со связью
    (песочница).
    """

    SIZE = 74

    def __init__(self, parent: Optional[QWidget] = None, glyph: str = "plus",
                 size: int | None = None):
        super().__init__(parent)
        self._glyph = glyph
        s = size or self.SIZE
        self._base_size = s
        self.setFixedSize(QSize(s, s))
        self.setCursor(Qt.PointingHandCursor)
        self.setPopupMode(QToolButton.InstantPopup)
        self.setStyleSheet(
            "QToolButton { background: transparent; border: none; }"
            "QToolButton::menu-indicator { image: none; }"
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(26)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(70, 120, 160, 70))
        self.setGraphicsEffect(shadow)

    def set_compact(self, on: bool) -> None:
        """В режиме-виджете пузырь поменьше, чтобы не загораживал список."""
        s = max(40, int(self._base_size * 0.7)) if on else self._base_size
        self.setFixedSize(QSize(s, s))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        rect = QRectF(self.rect()).adjusted(2.0, 2.0, -2.0, -2.0)
        paint_bubble_circle(
            p, rect,
            hover=self.underMouse(),
            pressed=self.isDown(),
        )
        if self._glyph == "graph":
            self._draw_graph(p, rect)
        else:
            self._draw_plus(p, rect)
        p.end()

    # -- глифы ---------------------------------------------------------
    def _draw_plus(self, p: QPainter, rect: QRectF) -> None:
        c = rect.center()
        arm = rect.width() * 0.185
        if theme.is_minimal():
            pens = [QPen(QColor(theme.MIN_ACCENT), 3.5, Qt.SolidLine, Qt.RoundCap)]
        else:
            pens = [
                QPen(QColor(90, 130, 160, 110), 5.5, Qt.SolidLine, Qt.RoundCap),
                QPen(QColor(255, 255, 255, 240), 4.0, Qt.SolidLine, Qt.RoundCap),
            ]
        for pen in pens:
            p.setPen(pen)
            p.drawLine(QPointF(c.x() - arm, c.y()), QPointF(c.x() + arm, c.y()))
            p.drawLine(QPointF(c.x(), c.y() - arm), QPointF(c.x(), c.y() + arm))

    def _draw_graph(self, p: QPainter, rect: QRectF) -> None:
        """Два кружка, соединённые линией, — «карта связей»."""
        w = rect.width()
        a = QPointF(rect.x() + w * 0.34, rect.y() + w * 0.64)
        b = QPointF(rect.x() + w * 0.66, rect.y() + w * 0.36)
        r1, r2 = w * 0.11, w * 0.085
        if theme.is_minimal():
            line_pen = QPen(QColor(theme.MIN_ACCENT), 2.4, Qt.SolidLine, Qt.RoundCap)
            fill = QColor(theme.MIN_ACCENT)
            shadow_pen = None
        else:
            line_pen = QPen(QColor(255, 255, 255, 235), 2.8, Qt.SolidLine, Qt.RoundCap)
            fill = QColor(255, 255, 255, 235)
            shadow_pen = QPen(QColor(90, 130, 160, 110), 4.2, Qt.SolidLine, Qt.RoundCap)
        if shadow_pen is not None:
            p.setPen(shadow_pen)
            p.drawLine(a, b)
        p.setPen(line_pen)
        p.drawLine(a, b)
        p.setPen(Qt.NoPen)
        if not theme.is_minimal():
            p.setBrush(QColor(90, 130, 160, 110))
            p.drawEllipse(QPointF(a.x() + 1, a.y() + 1), r1, r1)
            p.drawEllipse(QPointF(b.x() + 1, b.y() + 1), r2, r2)
        p.setBrush(fill)
        p.drawEllipse(a, r1, r1)
        p.drawEllipse(b, r2, r2)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(event)
