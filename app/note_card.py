# -*- coding: utf-8 -*-
"""Карточка заметки для сетки главного экрана."""
from __future__ import annotations

import html
from typing import Optional

from PySide6.QtCore import Qt, Signal, QPoint, QSize
from PySide6.QtGui import QColor, QFont, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout,
    QGraphicsDropShadowEffect, QWidget,
)

from . import colors as C
from .formatting import fmt_short, fmt_deadline
from .models import Note, TYPE_LIST, TYPE_TASK, PRIORITY_NAMES

PREVIEW_CHARS = 420


class NoteCard(QFrame):
    """Квадратная стеклянная карточка с цветом заметки."""

    openRequested = Signal(int)          # двойной клик — открыть редактор
    menuRequested = Signal(object, QPoint)  # нажали ⋯ (note, global pos)

    def __init__(self, note: Note, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.note = note
        self.setObjectName("card")
        self.setMinimumHeight(236)
        self.setMaximumHeight(236)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_color_style()

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(40, 80, 140, 80))
        self.setGraphicsEffect(shadow)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 10, 10)
        root.setSpacing(6)

        # --- верхняя строка: 📌 ... ⋯ ---
        top = QHBoxLayout()
        top.setSpacing(4)
        self.pin_label = QLabel("⚑", self)
        self.pin_label.setToolTip("Закреплённая заметка")
        self.pin_label.setVisible(note.pinned)
        top.addWidget(self.pin_label)

        self.type_label = QLabel(note.type_name, self)
        self.type_label.setStyleSheet(
            f"color: {C.TEXT_MUTED}; font-size: 10px; font-weight: 600;"
            "background: rgba(255,255,255,110); border-radius: 7px; padding: 1px 7px;"
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
            " font-weight: 700; color: #35506e; padding: 0 2px 3px 2px; }"
            "QToolButton:hover { background: rgba(255,255,255,170); }"
        )
        self.menu_btn.clicked.connect(
            lambda: self.menuRequested.emit(self.note, self.menu_btn.mapToGlobal(QPoint(0, 26)))
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
        self.title_label.setStyleSheet(f"color: {C.TEXT_DARK}; border: none;")
        root.addWidget(self.title_label)

        # --- превью содержимого ---
        self.preview_label = QLabel(self)
        self.preview_label.setWordWrap(True)
        self.preview_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.preview_label.setStyleSheet(
            f"color: {C.TEXT_MUTED}; font-size: 12px; border: none; line-height: 130%;"
        )
        self.preview_label.setTextFormat(Qt.RichText)
        root.addWidget(self.preview_label, 1)

        # --- превью картинки, если есть ---
        self.thumb_label = QLabel(self)
        self.thumb_label.setStyleSheet("border: none; background: transparent;")
        self.thumb_label.setVisible(False)
        root.addWidget(self.thumb_label, 0, Qt.AlignLeft)

        # --- нижняя строка: группа / картинки / дата ---
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.group_label = QLabel(self)
        self.group_label.setStyleSheet(
            f"color: {C.TEXT_DARK}; font-size: 10px; font-weight: 600;"
            "background: rgba(255,255,255,120); border-radius: 8px; padding: 2px 8px;"
        )
        bottom.addWidget(self.group_label)
        self.img_label = QLabel(self)
        self.img_label.setStyleSheet(f"color: {C.TEXT_MUTED}; font-size: 10px; border: none;")
        bottom.addWidget(self.img_label)
        bottom.addStretch(1)
        self.date_label = QLabel(self)
        self.date_label.setStyleSheet(f"color: {C.TEXT_MUTED}; font-size: 10px; border: none;")
        bottom.addWidget(self.date_label)
        root.addLayout(bottom)

        self._fill()

    # ------------------------------------------------------------------
    def _apply_color_style(self) -> None:
        key = self.note.color
        self.setStyleSheet(
            f"QFrame#card {{ background-color: {C.rgba(key, 225)};"
            f" border: 1px solid {C.border_rgba(key, 170)}; border-radius: 14px; }}"
            f"QFrame#card:hover {{ background-color: {C.rgba(key, 242)}; }}"
        )

    def _fill(self) -> None:
        n = self.note
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
                parts.append(
                    f'<span style="color:{pcol};">● {PRIORITY_NAMES.get(n.priority, n.priority)}'
                    f" приоритет</span>"
                )
            body = html.escape("\n".join(n.content.splitlines()[:5]))
            if body:
                parts.append(body.replace("\n", "<br>"))
            return "<br>".join(parts) or "<i>Без описания</i>"

        # обычная заметка
        text = n.content.strip()
        if not text:
            return "<i>Пустая заметка…</i>"
        lines = text.splitlines()[:8]
        text = "\n".join(lines)[:PREVIEW_CHARS]
        return html.escape(text).replace("\n", "<br>")

    # ------------------------------------------------------------------
    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.openRequested.emit(self.note.id)
        super().mouseDoubleClickEvent(event)
