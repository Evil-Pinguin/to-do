# -*- coding: utf-8 -*-
"""Напоминания о дедлайнах задач.

Система двойная:
  1. Трей-иконка + системное уведомление Windows (QSystemTrayIcon.showMessage)
  2. In-app glass popup — красивое всплывающее окно поверх карточек

Настройки: за сколько до дедлайна напоминать (15 мин / 1 ч / 1 день / 1 нед).
Хранятся в базе (таблица reminder_settings), по умолчанию — за 1 час.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, List, Callable

from PySide6.QtCore import Qt, QTimer, Signal, QPoint, QPropertyAnimation, QEasingCurve, QRect
from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QFont, QPixmap, QIcon
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QPushButton,
    QSystemTrayIcon, QVBoxLayout, QWidget, QFrame, QComboBox,
    QGraphicsDropShadowEffect,
)

from . import colors as C
from .formatting import fmt_deadline

# Варианты опережения: (метка, секунды)
REMIND_OFFSETS = [
    ("За 15 минут",  15 * 60),
    ("За 1 час",     60 * 60),
    ("За 1 день",    24 * 3600),
    ("За 1 неделю",  7 * 24 * 3600),
]
DEFAULT_OFFSET_IDX = 1  # «За 1 час»

CHECK_INTERVAL_MS = 60_000  # проверяем раз в минуту


# ---------------------------------------------------------------------------
#  Вспомогательный виджет: glass popup
# ---------------------------------------------------------------------------

class ReminderPopup(QWidget):
    """Всплывающее glass-окошко напоминания поверх главного окна."""

    dismissed = Signal()

    def __init__(self, title: str, deadline_str: str,
                 on_open: Optional[Callable] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self._on_open = on_open

        self.setFixedWidth(340)

        # Тень
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(20, 60, 110, 120))
        self.setGraphicsEffect(shadow)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(8)

        # Верхняя строка: иконка + заголовок + крестик
        top = QHBoxLayout()
        bell = QLabel("⚑", self)
        bell.setStyleSheet("color: #E57373; font-size: 18px; background: transparent;")
        top.addWidget(bell)

        head = QLabel("Напоминание о задаче", self)
        head.setStyleSheet(
            "color: #1a3a5c; font-size: 12px; font-weight: 700; background: transparent;"
        )
        top.addWidget(head, 1)

        close_btn = QPushButton("✕", self)
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton { border: none; border-radius: 11px; background: rgba(255,255,255,130);"
            " color: #5A7188; font-size: 11px; }"
            "QPushButton:hover { background: rgba(220,90,90,160); color: white; }"
        )
        close_btn.clicked.connect(self._dismiss)
        top.addWidget(close_btn)
        root.addLayout(top)

        # Заголовок задачи
        task_lbl = QLabel(title, self)
        task_lbl.setWordWrap(True)
        task_lbl.setStyleSheet(
            "color: #23405E; font-size: 14px; font-weight: 700; background: transparent;"
        )
        root.addWidget(task_lbl)

        # Дедлайн
        dl_lbl = QLabel(f"До: {deadline_str}", self)
        dl_lbl.setStyleSheet(
            "color: #d25454; font-size: 12px; font-weight: 600; background: transparent;"
        )
        root.addWidget(dl_lbl)

        # Кнопки
        btns = QHBoxLayout()
        btns.setSpacing(8)
        if on_open:
            open_btn = QPushButton("Открыть задачу", self)
            open_btn.setCursor(Qt.PointingHandCursor)
            open_btn.setStyleSheet(
                "QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                " stop:0 rgba(140,200,245,230), stop:1 rgba(85,155,215,230));"
                " border: 1px solid rgba(255,255,255,200); border-radius: 10px;"
                " color: white; font-size: 12px; font-weight: 700; padding: 6px 16px; }"
                "QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                " stop:0 rgba(160,215,250,240), stop:1 rgba(100,170,230,240)); }"
            )
            open_btn.clicked.connect(self._open)
            btns.addWidget(open_btn)

        dismiss_btn = QPushButton("Понятно", self)
        dismiss_btn.setCursor(Qt.PointingHandCursor)
        dismiss_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,160);"
            " border: 1px solid rgba(255,255,255,200); border-radius: 10px;"
            " color: #35506E; font-size: 12px; padding: 6px 16px; }"
            "QPushButton:hover { background: rgba(255,255,255,220); }"
        )
        dismiss_btn.clicked.connect(self._dismiss)
        btns.addWidget(dismiss_btn)
        root.addLayout(btns)

        self.adjustSize()

        # Авто-закрытие через 30 секунд
        QTimer.singleShot(30_000, self._dismiss)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(4, 4, -4, -8)  # отступ для тени

        path = QPainterPath()
        path.addRoundedRect(rect, 16, 16)

        # Основное glass-тело
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0.0, QColor(255, 255, 255, 220))
        grad.setColorAt(0.45, QColor(235, 247, 255, 200))
        grad.setColorAt(1.0, QColor(200, 230, 250, 185))
        p.fillPath(path, grad)

        # Specular highlight — верхняя треть
        shine_rect = QRect(rect.x(), rect.y(), rect.width(), rect.height() // 3)
        shine_path = QPainterPath()
        shine_path.addRoundedRect(shine_rect, 16, 16)
        shine_path = shine_path.intersected(path)
        shine = QLinearGradient(shine_rect.topLeft(), shine_rect.bottomLeft())
        shine.setColorAt(0.0, QColor(255, 255, 255, 140))
        shine.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(shine_path, shine)

        # Рамка
        p.setPen(QColor(180, 215, 245, 200))
        p.drawPath(path)
        p.end()

    def _dismiss(self) -> None:
        self.dismissed.emit()
        self.close()

    def _open(self) -> None:
        if self._on_open:
            self._on_open()
        self._dismiss()

    def show_at_corner(self, parent: QWidget) -> None:
        """Показать в правом нижнем углу родительского окна с анимацией."""
        parent_geom = parent.geometry()
        x = parent_geom.right() - self.width() - 24
        y = parent_geom.bottom() - self.height() - 48
        self.move(x, y + 30)
        self.show()
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(280)
        anim.setStartValue(QPoint(x, y + 30))
        anim.setEndValue(QPoint(x, y))
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._anim = anim  # держим ссылку


# ---------------------------------------------------------------------------
#  Менеджер напоминаний
# ---------------------------------------------------------------------------

class ReminderManager:
    """Проверяет дедлайны и показывает уведомления.

    Подключается к главному окну; db и open_callback передаются при создании.
    """

    def __init__(self, db, parent_window: QWidget,
                 open_note_callback: Optional[Callable[[int], None]] = None):
        self.db = db
        self.parent = parent_window
        self.open_cb = open_note_callback
        self._offset_sec: int = REMIND_OFFSETS[DEFAULT_OFFSET_IDX][1]
        self._fired: set[int] = set()   # note_id уже показанных сегодня
        self._popups: list[ReminderPopup] = []

        # Трей
        self._tray: Optional[QSystemTrayIcon] = None
        self._setup_tray()

        # Таймер проверки
        self._timer = QTimer(parent_window)
        self._timer.setInterval(CHECK_INTERVAL_MS)
        self._timer.timeout.connect(self.check)
        self._timer.start()

        # Первая проверка — через 3 сек после старта
        QTimer.singleShot(3000, self.check)

    # ------------------------------------------------------------------
    def set_offset(self, idx: int) -> None:
        idx = max(0, min(idx, len(REMIND_OFFSETS) - 1))
        self._offset_sec = REMIND_OFFSETS[idx][1]
        self._fired.clear()  # сбрасываем «уже показали» при смене настройки

    def get_offset_idx(self) -> int:
        for i, (_, sec) in enumerate(REMIND_OFFSETS):
            if sec == self._offset_sec:
                return i
        return DEFAULT_OFFSET_IDX

    # ------------------------------------------------------------------
    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(self.parent)
        # Минимальная иконка из QPixmap
        pm = QPixmap(32, 32)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        # фон — жёлтая скруглённая карточка
        p.setBrush(QColor("#FFE082"))
        p.setPen(QColor("#c8a800"))
        p.drawRoundedRect(2, 2, 28, 28, 7, 7)
        # галочка
        p.setPen(QColor("#23405E"))
        p.setFont(QFont("Arial", 14, QFont.Bold))
        p.drawText(pm.rect(), Qt.AlignCenter, "✓")
        p.end()
        self._tray.setIcon(QIcon(pm))
        self._tray.setToolTip("Aero Notes")
        self._tray.show()

    # ------------------------------------------------------------------
    def check(self) -> None:
        """Проверяем все задачи с дедлайном."""
        from .formatting import parse_ts
        from .models import TYPE_TASK
        try:
            notes = self.db.notes(archived=False)
        except Exception:
            return

        now = datetime.now()
        threshold = timedelta(seconds=self._offset_sec)

        for note in notes:
            if note.type != TYPE_TASK:
                continue
            if note.done or not note.deadline:
                continue
            if note.id in self._fired:
                continue
            dl = parse_ts(note.deadline)
            if dl is None:
                continue
            time_left = dl - now
            if timedelta(0) <= time_left <= threshold:
                self._fire(note, dl)

    def _fire(self, note, deadline: datetime) -> None:
        self._fired.add(note.id)
        dl_str = fmt_deadline(note.deadline)

        # 1. Системное уведомление
        if self._tray and self._tray.supportsMessages():
            self._tray.showMessage(
                "Напоминание — Aero Notes",
                f"{note.display_title}\nДо: {dl_str}",
                QSystemTrayIcon.Information,
                8000,
            )

        # 2. In-app popup
        on_open = (lambda nid=note.id: self.open_cb(nid)) if self.open_cb else None
        popup = ReminderPopup(note.display_title, dl_str, on_open=on_open, parent=None)
        popup.dismissed.connect(lambda p=popup: self._popups.remove(p) if p in self._popups else None)
        self._popups.append(popup)
        popup.show_at_corner(self.parent)
