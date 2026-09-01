# -*- coding: utf-8 -*-
"""Диалог «Сведения» с метаинформацией и настоящей историей изменений."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QDialog, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QWidget,
)

from .colors import color_name
from .db import Database
from .formatting import fmt_dt, fmt_deadline, fmt_history_ts, plural
from .glass import paint_bubble_glass
from .models import Note, TYPE_TASK, PRIORITY_NAMES


class GlassDialog(QDialog):
    """Базовый диалог с нарисованным glass-фоном."""

    _RADIUS = 20

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(
            Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowSystemMenuHint
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        # Диалоги — самое плотное стекло (много текста), но стиль тот же
        # «пузырьковый»: рим-кромка, полумесяц, искра, цветной рефлекс.
        paint_bubble_glass(
            p, rect, float(self._RADIUS),
            base_rgb=(250, 253, 255),
            body_alpha=195,
            reflex_alpha=40,
        )
        p.end()

    def _glass_btn_style(self) -> str:
        return (
            "QPushButton {"
            " background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "   stop:0 rgba(255,255,255,200), stop:1 rgba(220,238,255,180));"
            " border: 1px solid rgba(180,215,245,200);"
            " border-radius: 12px; padding: 7px 20px;"
            " font-size: 13px; color: #23405E;"
            "}"
            "QPushButton:hover {"
            " background: rgba(255,255,255,230);"
            " border: 1px solid rgba(130,185,235,210);"
            "}"
            "QPushButton:pressed {"
            " background: rgba(200,230,250,220);"
            "}"
        )

    def _accent_btn_style(self) -> str:
        return (
            "QPushButton {"
            " background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "   stop:0 rgba(155,210,250,235), stop:1 rgba(90,160,220,235));"
            " border: 1px solid rgba(255,255,255,220);"
            " border-radius: 12px; padding: 7px 20px;"
            " font-size: 13px; color: white; font-weight: 700;"
            "}"
            "QPushButton:hover {"
            " background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "   stop:0 rgba(170,220,255,245), stop:1 rgba(105,175,235,245));"
            "}"
        )


class DetailsDialog(GlassDialog):
    def __init__(self, db: Database, note: Note, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.db = db
        self.note = note
        self.setWindowTitle(f"Сведения — {note.display_title}")
        self.setModal(True)
        self.setMinimumWidth(400)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 18)
        lay.setSpacing(8)

        title = QLabel(note.display_title, self)
        title.setWordWrap(True)
        title.setStyleSheet(
            "font-size: 16px; font-weight: 800; color: #1a3d6b; background: transparent;"
        )
        lay.addWidget(title)

        # Разделитель
        sep = QFrame(self)
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background: rgba(160,200,235,120); max-height: 1px;")
        lay.addWidget(sep)

        rows = [
            ("Создано",             fmt_dt(note.created_at)),
            ("Последнее изменение", fmt_dt(note.modified_at)),
            ("Изменено",            f"{note.edit_count} {plural(note.edit_count, 'раз', 'раза', 'раз')}"
                                    if note.edit_count else "ни разу"),
            ("Группа",              note.group_name or "Без группы"),
            ("Тип",                 note.type_name),
            ("Цвет",                color_name(note.color)),
        ]
        if note.type == TYPE_TASK:
            if note.priority:
                rows.append(("Приоритет", PRIORITY_NAMES.get(note.priority, note.priority)))
            rows.append(("Дедлайн", fmt_deadline(note.deadline) if note.deadline else "—"))
        rows.append(("Картинок", str(note.image_count)))

        for name, value in rows:
            line = QLabel(f"<b>{name}:</b>&nbsp; {value}", self)
            line.setStyleSheet(
                "font-size: 13px; color: #35506E; background: transparent;"
            )
            lay.addWidget(line)

        lay.addSpacing(8)
        btns = QHBoxLayout()
        btns.addStretch(1)

        hist_btn = QPushButton("❑ История…", self)
        hist_btn.setStyleSheet(self._glass_btn_style())
        hist_btn.setCursor(Qt.PointingHandCursor)
        hist_btn.clicked.connect(self._show_history)
        btns.addWidget(hist_btn)

        close_btn = QPushButton("Закрыть", self)
        close_btn.setStyleSheet(self._accent_btn_style())
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        btns.addWidget(close_btn)
        lay.addLayout(btns)

    def _show_history(self) -> None:
        HistoryDialog(self.db, self.note, self).exec()


class HistoryDialog(GlassDialog):
    def __init__(self, db: Database, note: Note, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(f"История — {note.display_title}")
        self.setModal(True)
        self.resize(450, 420)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(8)

        hint = QLabel("История изменений:", self)
        hint.setStyleSheet(
            "color: #5A7188; font-size: 12px; background: transparent;"
        )
        lay.addWidget(hint)

        lst = QListWidget(self)
        lst.setStyleSheet(
            "QListWidget {"
            " background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "   stop:0 rgba(255,255,255,210), stop:1 rgba(240,250,255,195));"
            " border: 1px solid rgba(180,215,245,180);"
            " border-radius: 12px; padding: 6px; font-size: 13px;"
            "}"
            "QListWidget::item { border-radius: 7px; padding: 3px 6px; color: #35506E; }"
            "QListWidget::item:selected {"
            " background: rgba(130,190,240,160); color: #1a3d6b;"
            "}"
        )
        for row in db.history(note.id):
            lst.addItem(QListWidgetItem(f"{fmt_history_ts(row['ts'])} — {row['event']}"))
        lay.addWidget(lst, 1)

        close = QPushButton("Закрыть", self)
        close.setStyleSheet(self._accent_btn_style())
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.accept)
        lay.addWidget(close, 0, Qt.AlignRight)
