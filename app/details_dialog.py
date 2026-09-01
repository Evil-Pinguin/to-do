# -*- coding: utf-8 -*-
"""Диалог «Сведения» с метаинформацией и настоящей историей изменений."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QListWidget,
    QListWidgetItem, QWidget,
)

from .colors import color_name
from .db import Database
from .formatting import fmt_dt, fmt_deadline, fmt_history_ts, plural
from .models import Note, TYPE_TASK, PRIORITY_NAMES


class DetailsDialog(QDialog):
    def __init__(self, db: Database, note: Note, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.db = db
        self.note = note
        self.setWindowTitle(f"Сведения — {note.display_title}")
        self.setModal(True)
        self.setMinimumWidth(380)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(8)

        title = QLabel(note.display_title, self)
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 15px; font-weight: 700; color: #23405E;")
        lay.addWidget(title)

        rows = [
            ("Создано", fmt_dt(note.created_at)),
            ("Последнее изменение", fmt_dt(note.modified_at)),
            ("Изменено", f"{note.edit_count} {plural(note.edit_count, 'раз', 'раза', 'раз')}"
                         if note.edit_count else "ни разу"),
            ("Группа", note.group_name or "Без группы"),
            ("Тип", note.type_name),
            ("Цвет", color_name(note.color)),
        ]
        if note.type == TYPE_TASK:
            if note.priority:
                rows.append(("Приоритет", PRIORITY_NAMES.get(note.priority, note.priority)))
            rows.append(("Дедлайн", fmt_deadline(note.deadline) if note.deadline else "—"))
        rows.append(("Картинок", str(note.image_count)))

        for name, value in rows:
            line = QLabel(f"<b>{name}:</b>&nbsp; {value}", self)
            line.setStyleSheet("font-size: 13px; color: #35506E;")
            lay.addWidget(line)

        lay.addSpacing(6)
        btns = QHBoxLayout()
        btns.addStretch(1)

        hist_btn = QPushButton("❑ История…", self)
        hist_btn.clicked.connect(self._show_history)
        btns.addWidget(hist_btn)

        close_btn = QPushButton("Закрыть", self)
        close_btn.clicked.connect(self.accept)
        btns.addWidget(close_btn)
        lay.addLayout(btns)

    def _show_history(self) -> None:
        HistoryDialog(self.db, self.note, self).exec()


class HistoryDialog(QDialog):
    def __init__(self, db: Database, note: Note, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(f"История — {note.display_title}")
        self.setModal(True)
        self.resize(430, 400)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        hint = QLabel("История изменений:", self)
        hint.setStyleSheet("color: #5A7188; font-size: 12px;")
        lay.addWidget(hint)

        lst = QListWidget(self)
        lst.setStyleSheet(
            "QListWidget { background: rgba(255,255,255,210); border: 1px solid"
            " rgba(150,180,210,120); border-radius: 10px; padding: 6px; font-size: 13px; }"
        )
        for row in db.history(note.id):
            lst.addItem(QListWidgetItem(f"{fmt_history_ts(row['ts'])} — {row['event']}"))
        lay.addWidget(lst, 1)

        close = QPushButton("Закрыть", self)
        close.clicked.connect(self.accept)
        lay.addWidget(close, 0, Qt.AlignRight)
