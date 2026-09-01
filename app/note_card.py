# -*- coding: utf-8 -*-
"""Карточка заметки для сетки главного экрана — Frutiger Aero glass style."""
from __future__ import annotations

import html
from typing import Optional

from PySide6.QtCore import Qt, Signal, QPoint, QPointF, QSize, QRect, QRectF, QTimer
from PySide6.QtGui import (
    QColor, QCursor, QFont, QPainter, QPixmap,
)
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout,
    QGraphicsDropShadowEffect, QWidget,
)

from . import colors as C
from .formatting import fmt_short, fmt_deadline
from .glass import paint_bubble_card
from .models import Note, TYPE_LIST, TYPE_TASK, PRIORITY_NAMES

PREVIEW_CHARS = 420


class GlassCard(QFrame):
    """Базовый glass-виджет: рисует многослойный эффект жидкого стекла.

    При наведении карточка чуть «всплывает», а за курсором следует
    слабое световое пятно — стекло реагирует на пользователя.
    """

    def __init__(self, color_key: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._color_key = color_key
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setObjectName("glassCard")
        # таймер работает только пока мышь над карточкой (~20 fps)
        self._glow_timer = QTimer(self)
        self._glow_timer.setInterval(50)
        self._glow_timer.timeout.connect(self.update)

    def set_color(self, key: str) -> None:
        self._color_key = key
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        hovered = self.underMouse()
        # hover-lift: стекло приподнимается на 2px
        lift = 2.0 if hovered else 0.0
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5 - lift)
        rect.translate(0, -0.0 if not hovered else 0.0)
        glow = None
        if hovered:
            gp = self.mapFromGlobal(QCursor.pos())
            if self.rect().contains(gp):
                glow = QPointF(gp)
        # Карточка = прямоугольный мыльный пузырь: прозрачный центр-линза,
        # цветная «плёнка» по краям, полумесяц + искра (см. app/glass.py).
        paint_bubble_card(
            p, rect, 20.0,
            base_rgb=C.base_rgb(self._color_key),
            hover=hovered,
            glow_pos=glow,
        )
        p.end()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._glow_timer.start()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._glow_timer.stop()
        self.update()
        super().leaveEvent(event)


class NoteCard(GlassCard):
    """Квадратная стеклянная карточка с цветом заметки."""

    openRequested = Signal(int)
    menuRequested = Signal(object, QPoint)

    def __init__(self, note: Note, parent: Optional[QWidget] = None):
        super().__init__(note.color, parent)
        self.note = note
        self.setMinimumHeight(236)
        self.setMaximumHeight(236)
        self.setCursor(Qt.PointingHandCursor)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 7)
        shadow.setColor(QColor(30, 70, 130, 90))
        self.setGraphicsEffect(shadow)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 10, 10)
        root.setSpacing(6)

        # --- верхняя строка ---
        top = QHBoxLayout()
        top.setSpacing(4)
        self.pin_label = QLabel("⚑", self)
        self.pin_label.setToolTip("Закреплённая заметка")
        self.pin_label.setVisible(note.pinned)
        self.pin_label.setStyleSheet(
            "color: #d28c00; font-size: 13px; background: transparent;"
        )
        top.addWidget(self.pin_label)

        self.type_label = QLabel(note.type_name, self)
        self.type_label.setStyleSheet(
            f"color: {C.TEXT_DARK}; font-size: 10px; font-weight: 700;"
            "background: rgba(255,255,255,130); border-radius: 7px; padding: 1px 7px;"
            "border: 1px solid rgba(255,255,255,180);"
        )
        top.addWidget(self.type_label)
        top.addStretch(1)

        self.menu_btn = QToolButton(self)
        self.menu_btn.setText("⋯")
        self.menu_btn.setToolTip("Меню заметки")
        self.menu_btn.setCursor(Qt.PointingHandCursor)
        self.menu_btn.setFixedSize(QSize(30, 26))
        self.menu_btn.setStyleSheet(
            "QToolButton { border: none; border-radius: 9px; font-size: 15px;"
            " font-weight: 700; color: #35506e; padding: 0 2px 3px 2px;"
            " background: transparent; }"
            "QToolButton:hover { background: rgba(255,255,255,180); }"
        )
        self.menu_btn.clicked.connect(
            lambda: self.menuRequested.emit(
                self.note, self.menu_btn.mapToGlobal(QPoint(0, 26))
            )
        )
        top.addWidget(self.menu_btn, 0, Qt.AlignTop | Qt.AlignRight)
        root.addLayout(top)

        # --- заголовок ---
        self.title_label = QLabel(self)
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.title_label.setWordWrap(True)
        self.title_label.setMaximumHeight(44)
        self.title_label.setStyleSheet(
            f"color: {C.TEXT_DARK}; border: none; background: transparent;"
        )
        root.addWidget(self.title_label)

        # --- превью ---
        self.preview_label = QLabel(self)
        self.preview_label.setWordWrap(True)
        self.preview_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.preview_label.setStyleSheet(
            f"color: {C.TEXT_MUTED}; font-size: 12px; border: none;"
            "background: transparent; line-height: 130%;"
        )
        self.preview_label.setTextFormat(Qt.RichText)
        root.addWidget(self.preview_label, 1)

        # --- превью картинки ---
        self.thumb_label = QLabel(self)
        self.thumb_label.setStyleSheet("border: none; background: transparent;")
        self.thumb_label.setVisible(False)
        root.addWidget(self.thumb_label, 0, Qt.AlignLeft)

        # --- нижняя строка ---
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.group_label = QLabel(self)
        self.group_label.setStyleSheet(
            f"color: {C.TEXT_DARK}; font-size: 10px; font-weight: 700;"
            "background: rgba(255,255,255,130); border-radius: 8px; padding: 2px 8px;"
            "border: 1px solid rgba(255,255,255,170);"
        )
        bottom.addWidget(self.group_label)
        self.img_label = QLabel(self)
        self.img_label.setStyleSheet(
            f"color: {C.TEXT_MUTED}; font-size: 10px; border: none; background: transparent;"
        )
        bottom.addWidget(self.img_label)
        bottom.addStretch(1)
        self.date_label = QLabel(self)
        self.date_label.setStyleSheet(
            f"color: {C.TEXT_MUTED}; font-size: 10px; border: none; background: transparent;"
        )
        bottom.addWidget(self.date_label)
        root.addLayout(bottom)

        self._fill()

    # ------------------------------------------------------------------
    def refresh(self, note: Note) -> None:
        self.note = note
        self.set_color(note.color)
        self._fill()

    def _fill(self) -> None:
        n = self.note
        self.pin_label.setVisible(n.pinned)
        self.title_label.setText(html.escape(n.display_title))
        self.preview_label.setText(self._preview_html())

        if n.group_name:
            self.group_label.setText(f"◆ {n.group_name}")
            self.group_label.setVisible(True)
        else:
            self.group_label.setVisible(False)

        self.img_label.setText(f"▣ {n.image_count}" if n.image_count else "")
        self.date_label.setText(fmt_short(n.modified_at))

        if n.first_image:
            pm = QPixmap()
            if pm.loadFromData(n.first_image):
                self.thumb_label.setPixmap(
                    pm.scaled(96, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                self.thumb_label.setVisible(True)
        else:
            self.thumb_label.setVisible(False)

    # ------------------------------------------------------------------
    def _preview_html(self) -> str:
        n = self.note

        if n.type == TYPE_LIST:
            lines = []
            for it in n.list_items()[:7]:
                mark = "☑" if it.done else "☐"
                txt = html.escape(it.text or "…")
                if it.done:
                    lines.append(
                        f'<span style="color:#8aa0b4; text-decoration: line-through;">'
                        f"{mark} {txt}</span>"
                    )
                else:
                    lines.append(f"{mark} {txt}")
            return "<br>".join(lines) or "<i>Пустой список</i>"

        if n.type == TYPE_TASK:
            parts = []
            if n.done:
                parts.append('<b style="color:#3e9e63;">✓ Выполнено</b>')
            elif n.deadline:
                dl_txt = f"До: {fmt_deadline(n.deadline)}"
                col = "#d25454" if n.is_overdue() else C.TEXT_DARK
                parts.append(f'<b style="color:{col};">{html.escape(dl_txt)}</b>')
            if n.priority:
                pcol = C.PRIORITY_COLORS.get(n.priority, ("", "#888"))[1]
                # маленький «стеклянный бейдж», а не просто цветной текст
                parts.append(
                    f'<span style="background-color: rgba(255,255,255,110);'
                    f' color:{pcol}; font-weight:600;">'
                    f"&nbsp;● {PRIORITY_NAMES.get(n.priority, n.priority)}"
                    f" приоритет&nbsp;</span>"
                )
            body = html.escape("\n".join(n.content.splitlines()[:5]))
            if body:
                parts.append(body.replace("\n", "<br>"))
            return "<br>".join(parts) or "<i>Без описания</i>"

        text = n.content.strip()
        if not text:
            return "<i>Пустая заметка…</i>"
        lines = text.splitlines()[:8]
        text = "\n".join(lines)[:PREVIEW_CHARS]
        return html.escape(text).replace("\n", "<br>")

    # ------------------------------------------------------------------
    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.openRequested.emit(self.note.id)
        super().mouseDoubleClickEvent(event)
