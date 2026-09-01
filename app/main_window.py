# -*- coding: utf-8 -*-
"""Главное окно Aero Notes: сетка карточек, часы, поиск, сортировка, фильтры."""
from __future__ import annotations

import random
from typing import List, Optional

from PySide6.QtCore import QEvent, QRect, QRectF, Qt, QTimer, QSize
from PySide6.QtGui import (
    QAction, QColor, QFont, QIcon, QLinearGradient, QPainter, QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu, QPushButton,
    QScrollArea, QToolButton, QVBoxLayout, QWidget, QMessageBox,
)

from . import ambient
from . import colors as C
from . import theme
from .bubbles import BubbleButton
from .db import Database
from .details_dialog import DetailsDialog
from .editor import NoteEditor
from .formatting import fmt_clock, now_dt, plural
from .glass import paint_bubble_glass, paint_bubble_circle
from .models import Note, TYPE_LIST, TYPE_NOTE, TYPE_TASK, TYPE_NAMES
from .note_card import NoteCard
from .reminder import ReminderManager, REMIND_OFFSETS

SORT_MODES = [
    ("created",  "По дате создания"),
    ("modified", "По дате изменения"),
    ("title",    "По теме"),
    ("color",    "По цвету"),
    ("status",   "По статусу"),
]


# ---------------------------------------------------------------------------
#  Фоновый виджет
# ---------------------------------------------------------------------------

class BackgroundWidget(QWidget):
    """Живой фон Liquid Glass: световые пятна + медленно плавающие пузыри.

    Палитра зависит от времени суток (app/ambient.py): утро/день/вечер/ночь.
    Статичная часть (градиент + пятна) кешируется в QPixmap; каждый кадр
    поверх рисуются только пузыри — дёшево.
    """

    # относительные позиции пузырей: (fx, fy, радиус_px, фаза, амплитуда_px)
    _BUBBLES = [
        (0.16, 0.30, 26, 0.0, 9),
        (0.34, 0.68, 40, 1.7, 12),
        (0.57, 0.22, 18, 3.1, 7),
        (0.72, 0.55, 30, 4.4, 10),
        (0.88, 0.78, 22, 2.3, 8),
        (0.93, 0.16, 34, 5.2, 11),
    ]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._cache: Optional[QPixmap] = None
        self._cache_key: tuple = ()
        self._t = 0.0
        # медленное дыхание пузырей (~8 кадров/с достаточно)
        self._anim = QTimer(self)
        self._anim.setInterval(120)
        self._anim.timeout.connect(self._tick_anim)
        self._anim.start()
        # раз в минуту проверяем, не сменилось ли время суток
        self._period = ambient.period()
        self._clock = QTimer(self)
        self._clock.setInterval(60_000)
        self._clock.timeout.connect(self._check_period)
        self._clock.start()

    def _tick_anim(self) -> None:
        if not self.isVisible() or theme.is_minimal():
            return
        self._t += 0.12
        self.update()

    def _check_period(self) -> None:
        if ambient.period() != self._period:
            self._period = ambient.period()
            self._cache = None
            win = self.window()
            if win is not None:
                win.update()
            self.update()

    def _rebuild_cache(self) -> None:
        pal = ambient.palette()
        w, h = max(1, self.width()), max(1, self.height())
        pm = QPixmap(w, h)
        p = QPainter(pm)
        # небо — мягкий вертикальный градиент
        sky = QLinearGradient(0, 0, 0, h)
        sky.setColorAt(0.0, QColor(pal["sky"][0]))
        sky.setColorAt(1.0, QColor(pal["sky"][1]))
        p.fillRect(0, 0, w, h, sky)
        # большие размытые световые пятна
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        for (r_, g_, b_, a_, fx, fy, fr) in pal["blobs"]:
            rad = fr * max(w, h)
            cx, cy = fx * w, fy * h
            grad = QRadialGradient(cx, cy, rad)
            grad.setColorAt(0.0, QColor(r_, g_, b_, a_))
            grad.setColorAt(0.55, QColor(r_, g_, b_, int(a_ * 0.45)))
            grad.setColorAt(1.0, QColor(r_, g_, b_, 0))
            p.setBrush(grad)
            p.drawEllipse(QRectF(cx - rad, cy - rad, rad * 2, rad * 2))
        # лёгкая вуаль
        if pal["veil"]:
            p.fillRect(0, 0, w, h, QColor(255, 255, 255, pal["veil"]))
        p.end()
        self._cache = pm
        self._cache_key = (w, h, self._period)

    def paintEvent(self, event) -> None:  # noqa: N802
        import math
        p = QPainter(self)
        rect = self.rect()
        if theme.is_minimal():
            p.fillRect(rect, QColor(theme.MIN_BG))
            p.end()
            return
        key = (rect.width(), rect.height(), ambient.period())
        if self._cache is None or self._cache_key != key:
            self._period = ambient.period()
            self._rebuild_cache()
        p.drawPixmap(0, 0, self._cache)
        # декоративные пузыри — почти прозрачные, медленно дышат
        p.setRenderHint(QPainter.Antialiasing)
        for (fx, fy, r, phase, amp) in self._BUBBLES:
            x = fx * rect.width()
            y = fy * rect.height() + amp * math.sin(self._t * 0.35 + phase)
            paint_bubble_circle(p, QRectF(x - r, y - r, r * 2, r * 2))
        p.end()


# ---------------------------------------------------------------------------
#  Стеклянная панель — базовый виджет для TopBar и FilterPanel
# ---------------------------------------------------------------------------

class GlassPanel(QFrame):
    """QFrame с нарисованным glass-фоном (без blur-зависимостей платформы)."""

    def __init__(self, radius: int = 18, alpha_top: int = 210,
                 alpha_bottom: int = 175, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._radius = radius
        self._alpha_top = alpha_top
        self._alpha_bottom = alpha_bottom
        self.setAttribute(Qt.WA_StyledBackground, False)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        # Панели держат контролы — тело чуть плотнее карточек,
        # но стиль тот же: рим, полумесяц, искра, цветной рефлекс.
        paint_bubble_glass(
            p, rect, float(self._radius),
            base_rgb=(248, 253, 255),
            body_alpha=max(60, self._alpha_top - 75),
            sparkle=self._radius >= 14,
            reflex_alpha=45,
        )
        p.end()


# ---------------------------------------------------------------------------
#  Главное окно
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.setWindowTitle("Aero Notes — заметки и задачи")
        self.resize(1340, 850)
        # Минимум совсем маленький: окно можно сжать в «виджет» со списком
        self.setMinimumSize(280, 320)

        self._cards: List[NoteCard] = []
        self._cols = 0
        self.sort_desc = True
        self._compact = False

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(14, 10, 14, 12)
        outer.setSpacing(10)
        self._outer_lay = outer

        self.bg = BackgroundWidget(central)
        self.bg.lower()

        self.top_bar = self._build_top_bar()
        outer.addWidget(self.top_bar)
        body = QHBoxLayout()
        body.setSpacing(10)
        outer.addLayout(body, 1)

        self._build_filter_panel()
        body.addWidget(self.filter_panel)

        self._build_board()
        body.addWidget(self.scroll, 1)

        # Плавающая кнопка-пузырь «+» (правый нижний угол)
        self.fab = BubbleButton(central)
        fab_menu = QMenu(self.fab)
        for ntype in (TYPE_NOTE, TYPE_LIST, TYPE_TASK):
            act = fab_menu.addAction(TYPE_NAMES[ntype])
            act.triggered.connect(lambda _=False, t=ntype: self._create_note(t))
        self.fab.setMenu(fab_menu)
        self.fab.raise_()

        # Кнопка-пузырь поменьше — открывает песочницу со связями
        self.sandbox_btn = BubbleButton(central, glyph="graph", size=52)
        self.sandbox_btn.setToolTip("Песочница: холст со связями заметок")
        self.sandbox_btn.clicked.connect(self._open_sandbox)
        self._sandbox_win = None

        # Мини-булавка для режима-виджета (топ-бар там спрятан)
        self.pin_fab = QToolButton(central)
        self.pin_fab.setText("📌")
        self.pin_fab.setToolTip("Окно поверх всех остальных")
        self.pin_fab.setCheckable(True)
        self.pin_fab.setCursor(Qt.PointingHandCursor)
        self.pin_fab.setFixedSize(QSize(30, 30))
        self.pin_fab.setObjectName("pinFab")
        self.pin_fab.toggled.connect(self._set_pinned)
        self.pin_fab.setVisible(False)

        self._apply_style()
        self._start_clock()

        self.scroll.viewport().installEventFilter(self)
        QTimer.singleShot(0, self.refresh)

        # Напоминания — запускаем после появления окна
        QTimer.singleShot(500, self._start_reminders)

    def resizeEvent(self, event) -> None:  # noqa: N802
        # Обои должны растягиваться на всё окно (иначе останутся крошечными
        # в углу — их размер layout'ом не управляется).
        central = self.centralWidget()
        self.bg.setGeometry(central.rect())
        self._update_compact_mode()
        # Кнопка-пузырь — в правом нижнем углу поверх всего
        m = 14 if self._compact else 26
        self.fab.move(
            central.width() - self.fab.width() - m,
            central.height() - self.fab.height() - m,
        )
        self.fab.raise_()
        # пузырь песочницы — слева от «+», по нижнему краю
        self.sandbox_btn.move(
            self.fab.x() - self.sandbox_btn.width() - 10,
            self.fab.y() + self.fab.height() - self.sandbox_btn.height(),
        )
        self.sandbox_btn.raise_()
        # мини-булавка — правый верхний угол (только в режиме-виджете)
        self.pin_fab.move(central.width() - self.pin_fab.width() - 8, 8)
        self.pin_fab.raise_()
        super().resizeEvent(event)

    def _update_compact_mode(self) -> None:
        """Режим-виджет: в маленьком окне остаётся только список заметок."""
        compact = self.width() < 720 or self.height() < 520
        if compact == self._compact:
            return
        self._compact = compact
        self.top_bar.setVisible(not compact)
        self.filter_panel.setVisible(not compact and self.filter_btn.isChecked())
        self.pin_fab.setVisible(compact)
        if compact:
            self._outer_lay.setContentsMargins(6, 6, 6, 6)
            self.fab.set_compact(True)
            self.sandbox_btn.set_compact(True)
        else:
            self._outer_lay.setContentsMargins(14, 10, 14, 12)
            self.fab.set_compact(False)
            self.sandbox_btn.set_compact(False)
        self._relayout(force=True)

    # ==================================================================
    #  Верхняя панель
    # ==================================================================
    def _build_top_bar(self) -> GlassPanel:
        bar = GlassPanel(radius=20, alpha_top=215, alpha_bottom=180, parent=self)
        bar.setObjectName("topBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(8)

        # Кнопка выбора темы — левый верхний угол
        self.theme_btn = QToolButton(bar)
        self.theme_btn.setText("◐ Тема")
        self.theme_btn.setToolTip("Тема оформления")
        self.theme_btn.setPopupMode(QToolButton.InstantPopup)
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        tmenu = QMenu(self.theme_btn)
        self._theme_actions = {}
        for key, title in theme.THEME_NAMES.items():
            act = tmenu.addAction(title)
            act.setCheckable(True)
            act.setChecked(theme.current() == key)
            act.triggered.connect(lambda _=False, k=key: self._set_theme(k))
            self._theme_actions[key] = act
        self.theme_btn.setMenu(tmenu)
        lay.addWidget(self.theme_btn)

        app_label = QLabel("✦ Aero Notes", bar)
        app_label.setObjectName("brandLabel")
        lay.addWidget(app_label)

        self.clock_label = QLabel("", bar)
        self.clock_label.setObjectName("clockLabel")
        lay.addWidget(self.clock_label)

        lay.addStretch(1)

        self.count_label = QLabel("", bar)
        self.count_label.setObjectName("countLabel")
        lay.addWidget(self.count_label)

        self.search_edit = QLineEdit(bar)
        self.search_edit.setPlaceholderText("Поиск по заметкам…")
        self.search_edit.setFixedWidth(230)
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(lambda _: self.refresh())
        lay.addWidget(self.search_edit)

        self.sort_combo = QComboBox(bar)
        for _, title in SORT_MODES:
            self.sort_combo.addItem(title)
        self.sort_combo.setToolTip("Сортировка")
        self.sort_combo.currentIndexChanged.connect(lambda _: self.refresh())
        lay.addWidget(self.sort_combo)

        self.sort_dir_btn = QToolButton(bar)
        self.sort_dir_btn.setText("↓")
        self.sort_dir_btn.setToolTip("Сначала новые / сначала старые")
        self.sort_dir_btn.setCheckable(True)
        self.sort_dir_btn.setChecked(True)
        self.sort_dir_btn.clicked.connect(self._flip_sort_dir)
        lay.addWidget(self.sort_dir_btn)

        self.filter_btn = QPushButton("☰  Фильтр", bar)
        self.filter_btn.setCheckable(True)
        self.filter_btn.toggled.connect(self._toggle_filter_panel)
        lay.addWidget(self.filter_btn)

        self.archive_btn = QPushButton("▦  Архив", bar)
        self.archive_btn.setCheckable(True)
        self.archive_btn.toggled.connect(lambda _: self.refresh())
        lay.addWidget(self.archive_btn)

        # Настройки напоминаний
        remind_lbl = QLabel("⚑", bar)
        remind_lbl.setToolTip("Напоминания о дедлайнах")
        remind_lbl.setStyleSheet(
            "color: #c8960a; font-size: 14px; background: transparent; padding: 0 2px;"
        )
        lay.addWidget(remind_lbl)

        self.remind_combo = QComboBox(bar)
        for label, _ in REMIND_OFFSETS:
            self.remind_combo.addItem(label)
        self.remind_combo.setCurrentIndex(1)  # «За 1 час»
        self.remind_combo.setToolTip("За сколько до дедлайна напоминать")
        self.remind_combo.currentIndexChanged.connect(self._on_remind_changed)
        lay.addWidget(self.remind_combo)

        self.new_btn = QToolButton(bar)
        self.new_btn.setText("+  Создать")
        self.new_btn.setObjectName("newButton")
        self.new_btn.setPopupMode(QToolButton.InstantPopup)
        self.new_btn.setCursor(Qt.PointingHandCursor)
        menu = QMenu(self.new_btn)
        for ntype in (TYPE_NOTE, TYPE_LIST, TYPE_TASK):
            act = menu.addAction(TYPE_NAMES[ntype])
            act.setData(ntype)
            act.triggered.connect(lambda _=False, t=ntype: self._create_note(t))
        self.new_btn.setMenu(menu)
        lay.addWidget(self.new_btn)

        # Булавка «поверх всех окон»
        self.pin_btn = QToolButton(bar)
        self.pin_btn.setText("📌")
        self.pin_btn.setToolTip("Окно поверх всех остальных")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setCursor(Qt.PointingHandCursor)
        self.pin_btn.toggled.connect(self._set_pinned)
        lay.addWidget(self.pin_btn)
        return bar

    # ==================================================================
    #  Тема и булавка
    # ==================================================================
    def _set_theme(self, key: str) -> None:
        theme.set_current(key)
        for k, act in self._theme_actions.items():
            act.setChecked(k == key)
        self._apply_style()
        # перерисовать всё, что рисуется вручную
        self.bg.update()
        self.top_bar.update()
        self.filter_panel.update()
        self.fab.update()
        self.sandbox_btn.update()
        self.pin_fab.update()
        for card in self._cards:
            card.update()
        # песочница, если открыта
        if getattr(self, "_sandbox_win", None) is not None and self._sandbox_win.isVisible():
            self._sandbox_win.setStyleSheet(self.styleSheet())
            self._sandbox_win.canvas.update()
            self._sandbox_win.fab.update()
            for c in self._sandbox_win.canvas.cards:
                c.update()

    def _set_pinned(self, on: bool) -> None:
        for b in (self.pin_btn, self.pin_fab):
            b.blockSignals(True)
            b.setChecked(on)
            b.blockSignals(False)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        self.show()  # после смены флага окно нужно показать заново

    # ==================================================================
    #  Песочница
    # ==================================================================
    def _open_sandbox(self) -> None:
        from .sandbox import SandboxWindow
        if self._sandbox_win is None or not self._sandbox_win.isVisible():
            self._sandbox_win = SandboxWindow(self.db, self)
        self._sandbox_win.show()
        self._sandbox_win.raise_()
        self._sandbox_win.activateWindow()

    # ==================================================================
    #  Панель фильтров
    # ==================================================================
    def _build_filter_panel(self) -> None:
        panel = GlassPanel(radius=16, alpha_top=205, alpha_bottom=170, parent=self)
        panel.setObjectName("filterPanel")
        panel.setFixedWidth(235)
        panel.setVisible(False)
        self.filter_panel = panel
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(6)

        head = QHBoxLayout()
        t = QLabel("Фильтр", panel)
        t.setStyleSheet("font-size: 13px; font-weight: 700; color: #23405E; background: transparent;")
        head.addWidget(t)
        head.addStretch(1)
        reset = QPushButton("Сбросить", panel)
        reset.setFlat(True)
        reset.setStyleSheet(
            "QPushButton { color: #4a7db3; font-size: 11px; border: none;"
            " background: transparent; padding: 2px 6px; border-radius: 8px; }"
            "QPushButton:hover { background: rgba(74,125,179,40); }"
        )
        reset.clicked.connect(self._reset_filters)
        head.addWidget(reset)
        lay.addLayout(head)

        lay.addWidget(self._section("Группы"))
        self.group_checks: List[tuple[int, QCheckBox]] = []
        self._rebuild_group_checks()
        add_group = QPushButton("+ Новая группа…", panel)
        add_group.setFlat(True)
        add_group.setStyleSheet(
            "QPushButton { color: #4a7db3; font-size: 11px; border: none;"
            " background: transparent; padding: 2px 6px; border-radius: 8px; }"
            "QPushButton:hover { background: rgba(74,125,179,40); }"
        )
        add_group.clicked.connect(self._add_group)
        lay.addWidget(add_group)

        lay.addSpacing(6)
        lay.addWidget(self._section("Тип"))
        self.type_checks = {}
        for ntype, name in ((TYPE_NOTE, "Заметки"), (TYPE_LIST, "Списки"), (TYPE_TASK, "Задачи")):
            cb = QCheckBox(name, panel)
            cb.setChecked(True)
            cb.stateChanged.connect(lambda _: self.refresh())
            self.type_checks[ntype] = cb
            lay.addWidget(cb)

        lay.addSpacing(6)
        lay.addWidget(self._section("Статус"))
        self.status_combo = QComboBox(panel)
        self.status_combo.addItem("Любой")
        self.status_combo.addItem("Активные")
        self.status_combo.addItem("Выполненные")
        self.status_combo.currentIndexChanged.connect(lambda _: self.refresh())
        lay.addWidget(self.status_combo)

        lay.addSpacing(6)
        lay.addWidget(self._section("Цвет"))
        colors_row = QHBoxLayout()
        colors_row.setSpacing(5)
        self.color_btns = {}
        for key, (name, hexcol) in C.PALETTE.items():
            b = QToolButton(panel)
            b.setFixedSize(QSize(24, 24))
            b.setCheckable(True)
            b.setToolTip(name)
            b.setStyleSheet(
                f"QToolButton {{ background: {hexcol}; border: 1px solid rgba(60,90,120,100);"
                f" border-radius: 8px; }}"
                f"QToolButton:checked {{ border: 2.5px solid #3a6ea5; }}"
            )
            b.toggled.connect(lambda _, k=key: self.refresh())
            self.color_btns[key] = b
            colors_row.addWidget(b)
        lay.addLayout(colors_row)

        lay.addStretch(1)

    def _section(self, text: str) -> QLabel:
        lab = QLabel(text.upper(), self.filter_panel)
        lab.setStyleSheet(
            "color: #5A7188; font-size: 10px; font-weight: 700;"
            "letter-spacing: 1px; background: transparent;"
        )
        return lab

    def _rebuild_group_checks(self) -> None:
        if not hasattr(self, "group_checks"):
            return
        checked = {gid for gid, cb in self.group_checks if cb.isChecked()}
        for _, cb in self.group_checks:
            cb.setParent(None)
            cb.deleteLater()
        self.group_checks = []
        lay = self.filter_panel.layout()
        insert_at = 2
        for g in self.db.groups():
            cb = QCheckBox(g.name, self.filter_panel)
            if g.id in checked:
                cb.setChecked(True)
            cb.stateChanged.connect(lambda _: self.refresh())
            self.group_checks.append((g.id, cb))
            lay.insertWidget(insert_at, cb)
            insert_at += 1

    def _add_group(self) -> None:
        name, ok = QInputDialog.getText(self, "Новая группа", "Название группы:")
        if ok and name.strip():
            self.db.add_group(name)
            self._rebuild_group_checks()
            self.refresh()

    def _reset_filters(self) -> None:
        for gid, cb in self.group_checks:
            cb.setChecked(False)
        for cb in self.type_checks.values():
            cb.setChecked(True)
        self.status_combo.setCurrentIndex(0)
        for b in self.color_btns.values():
            b.setChecked(False)
        self.search_edit.clear()
        self.refresh()

    def _toggle_filter_panel(self, on: bool) -> None:
        self.filter_panel.setVisible(on and not self._compact)

    # ==================================================================
    #  Доска с карточками
    # ==================================================================
    def _build_board(self) -> None:
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)

        board = QWidget()
        board.setObjectName("board")
        self.grid = QGridLayout(board)
        self.grid.setContentsMargins(6, 6, 6, 6)
        self.grid.setSpacing(16)

        self.empty_label = QLabel(
            "Здесь пока пусто — создайте первую заметку ✦", board
        )
        self.empty_label.setObjectName("emptyLabel")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setVisible(False)

        self.scroll.setWidget(board)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.scroll.viewport() and event.type() == QEvent.Resize:
            self._relayout()
        return super().eventFilter(obj, event)

    # ==================================================================
    #  Данные: фильтрация, сортировка, отрисовка
    # ==================================================================
    def refresh(self) -> None:
        notes = self.db.notes(archived=self.archive_btn.isChecked())
        notes = self._filter_notes(notes)
        notes = self._sort_notes(notes)

        for card in self._cards:
            card.deleteLater()
        self._cards = []
        for n in notes:
            card = NoteCard(n)
            card.openRequested.connect(self._open_editor)
            card.menuRequested.connect(self._card_menu)
            self._cards.append(card)

        total = len(self.db.notes(archived=False)) + len(self.db.notes(archived=True))
        word = plural(len(notes), "заметка", "заметки", "заметок")
        scope = "в архиве" if self.archive_btn.isChecked() else ""
        self.count_label.setText(f"Показано: {len(notes)} {word} {scope} из {total}")

        self._relayout(force=True)

    def _filter_notes(self, notes: List[Note]) -> List[Note]:
        q = self.search_edit.text().strip().lower()
        active_groups = {gid for gid, cb in self.group_checks if cb.isChecked()}
        active_types = {t for t, cb in self.type_checks.items() if cb.isChecked()}
        active_colors = {k for k, b in self.color_btns.items() if b.isChecked()}
        status = self.status_combo.currentIndex()

        result = []
        for n in notes:
            if q and q not in n.plain_text():
                continue
            if active_groups and n.group_id not in active_groups:
                continue
            if n.type not in active_types:
                continue
            if active_colors and n.color not in active_colors:
                continue
            if status == 1 and n.is_done():
                continue
            if status == 2 and not n.is_done():
                continue
            result.append(n)
        return result

    def _sort_notes(self, notes: List[Note]) -> List[Note]:
        mode = SORT_MODES[self.sort_combo.currentIndex()][0]

        def key(n: Note):
            if mode == "created":
                return n.created_at
            if mode == "modified":
                return n.modified_at
            if mode == "title":
                return n.display_title.lower()
            if mode == "color":
                return C.color_index(n.color)
            return (1 if n.is_done() else 0, n.deadline or "")

        pinned = sorted((n for n in notes if n.pinned), key=key, reverse=self.sort_desc)
        rest   = sorted((n for n in notes if not n.pinned), key=key, reverse=self.sort_desc)
        return pinned + rest

    def _flip_sort_dir(self) -> None:
        self.sort_desc = self.sort_dir_btn.isChecked()
        self.sort_dir_btn.setText("↓" if self.sort_desc else "↑")
        self.refresh()

    def _clear_grid(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

    def _relayout(self, force: bool = False) -> None:
        vw = max(self.scroll.viewport().width() - 12, 160)
        # В компактном режиме-виджете — одна колонка, как список
        if self._compact:
            cols = 1 if vw < 560 else 2
        else:
            cols = max(1, min(6, vw // 300))
        if cols == self._cols and not force:
            return
        self._cols = cols
        self._clear_grid()

        if not self._cards:
            self.empty_label.setVisible(True)
            self.grid.addWidget(self.empty_label, 0, 0, 1, cols)
            self.grid.setRowStretch(1, 1)
            return
        self.empty_label.setVisible(False)

        for i, card in enumerate(self._cards):
            r, c = divmod(i, cols)
            self.grid.addWidget(card, r, c)
        for c in range(cols):
            self.grid.setColumnStretch(c, 1)

    # ==================================================================
    #  Часы
    # ==================================================================
    def _start_clock(self) -> None:
        self._tick()
        timer = QTimer(self)
        timer.setInterval(500)
        timer.timeout.connect(self._tick)
        timer.start()

    def _tick(self) -> None:
        self.clock_label.setText(fmt_clock(now_dt()))

    # ==================================================================
    #  Напоминания
    # ==================================================================
    def _start_reminders(self) -> None:
        self._reminder_mgr = ReminderManager(
            db=self.db,
            parent_window=self,
            open_note_callback=self._open_editor,
        )
        self._reminder_mgr.set_offset(self.remind_combo.currentIndex())

    def _on_remind_changed(self, idx: int) -> None:
        if hasattr(self, "_reminder_mgr"):
            self._reminder_mgr.set_offset(idx)

    # ==================================================================
    #  Действия
    # ==================================================================
    def _create_note(self, ntype: str) -> None:
        color = random.choice(list(C.PALETTE.keys()))
        note = self.db.create_note(ntype, color=color)
        if self.archive_btn.isChecked():
            self.archive_btn.setChecked(False)
        self._open_editor(note.id)

    def _open_editor(self, note_id: int) -> None:
        # затемняющая вуаль под модальным окном — глубина по брифу
        overlay = QWidget(self.centralWidget())
        overlay.setAttribute(Qt.WA_StyledBackground, True)
        overlay.setStyleSheet("background: rgba(30, 48, 80, 70);")
        overlay.setGeometry(self.centralWidget().rect())
        overlay.show()
        overlay.raise_()
        try:
            editor = NoteEditor(self.db, note_id, self)
            editor.exec()
        finally:
            overlay.deleteLater()
        self.refresh()

    def _swatch_icon(self, hexcol: str) -> QIcon:
        pm = QPixmap(20, 20)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(hexcol))
        p.setPen(QColor(90, 110, 140, 160))
        p.drawRoundedRect(1, 1, 18, 18, 5, 5)
        p.end()
        return QIcon(pm)

    def _card_menu(self, note: Note, pos) -> None:
        m = self._build_card_menu(note)
        m.exec(pos)

    def _build_card_menu(self, note: Note) -> QMenu:
        m = QMenu(self)
        m.setAttribute(Qt.WA_TranslucentBackground)
        m.setStyleSheet(self._menu_qss())

        m.addAction("Сведения", lambda: self._show_details(note))

        color_menu = m.addMenu("Изменить цвет")
        for key, (name, hexcol) in C.PALETTE.items():
            act = QAction(self._swatch_icon(hexcol), name, color_menu)
            if note.color == key:
                font = QFont()
                font.setBold(True)
                act.setFont(font)
            color_menu.addAction(act)
            act.triggered.connect(lambda _=False, k=key: self._set_color(note, k))

        group_menu = m.addMenu("Переместить в группу")
        none_act = QAction("Без группы", group_menu)
        if note.group_id is None:
            none_act.setText("✓ Без группы")
        group_menu.addAction(none_act)
        none_act.triggered.connect(lambda: self._move_group(note, None))
        for g in self.db.groups():
            act = QAction("✓ " + g.name if g.id == note.group_id else g.name, group_menu)
            group_menu.addAction(act)
            act.triggered.connect(lambda _=False, gid=g.id: self._move_group(note, gid))
        group_menu.addSeparator()
        group_menu.addAction("Новая группа…", self._add_group)

        m.addSeparator()
        m.addAction(("Открепить" if note.pinned else "Закрепить"),
                    lambda: self._toggle_pin(note))
        m.addAction("Создать копию", lambda: self._duplicate(note))
        if note.archived:
            m.addAction("Восстановить из архива", lambda: self._archive(note, False))
        else:
            m.addAction("Архивировать", lambda: self._archive(note, True))

        m.addSeparator()
        del_act = m.addAction("Удалить")
        del_act.triggered.connect(lambda: self._delete(note))
        return m

    def _show_details(self, note: Note) -> None:
        fresh = self.db.note_by_id(note.id)
        if fresh:
            DetailsDialog(self.db, fresh, self).exec()
            self.refresh()

    def _set_color(self, note: Note, color: str) -> None:
        self.db.set_color(note.id, color)
        self.refresh()

    def _move_group(self, note: Note, group_id: Optional[int]) -> None:
        self.db.move_to_group(note.id, group_id)
        self.refresh()

    def _toggle_pin(self, note: Note) -> None:
        self.db.set_pinned(note.id, not note.pinned)
        self.refresh()

    def _duplicate(self, note: Note) -> None:
        new_id = self.db.duplicate(note.id)
        if new_id:
            self.refresh()

    def _archive(self, note: Note, archived: bool) -> None:
        self.db.set_archived(note.id, archived)
        self.refresh()

    def _delete(self, note: Note) -> None:
        ret = QMessageBox.question(
            self, "Удалить заметку?",
            f"Удалить «{note.display_title}» навсегда?\nЭто действие необратимо.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            self.db.delete_note(note.id)
            self.refresh()

    # ==================================================================
    #  Стили
    # ==================================================================
    def _menu_qss(self) -> str:
        if theme.is_minimal():
            return f"""
                QMenu {{
                    background: #FFFFFF;
                    border: 1px solid {theme.MIN_HAIRLINE};
                    border-radius: 10px; padding: 5px;
                    font-size: 13px; color: {theme.MIN_TEXT};
                }}
                QMenu::item {{ padding: 6px 26px 6px 14px; border-radius: 6px; }}
                QMenu::item:selected {{ background: #F0F0F2; }}
                QMenu::separator {{
                    height: 1px; background: {theme.MIN_HAIRLINE}; margin: 5px 10px;
                }}
            """
        return """
            QMenu {
                background: rgba(240,250,255,235);
                border: 1px solid rgba(200,225,245,220);
                border-radius: 14px; padding: 6px;
                font-size: 13px; color: #2A4258;
            }
            QMenu::item { padding: 6px 26px 6px 14px; border-radius: 9px; }
            QMenu::item:selected { background: rgba(130,190,240,160); }
            QMenu::separator {
                height: 1px; background: rgba(160,200,235,130); margin: 5px 10px;
            }
        """

    def _apply_style(self) -> None:
        if theme.is_minimal():
            self._apply_minimal_style()
            return
        self.setStyleSheet(f"""
            MainWindow, BackgroundWidget {{ background: #E4F2FB; }}

            /* GlassPanel рисует себя сам через paintEvent, QSS только для дочерних */
            GlassPanel {{ background: transparent; border: none; }}

            QLabel#brandLabel {{
                color: #1a3d6b; font-size: 14px; font-weight: 800;
                background: rgba(255,255,255,140); border-radius: 12px;
                padding: 5px 14px;
                border: 1px solid rgba(255,255,255,210);
            }}
            QLabel#clockLabel {{
                color: #1E3A5F; font-size: 12px; font-weight: 600;
                background: rgba(255,255,255,120); border-radius: 12px;
                padding: 6px 12px;
                border: 1px solid rgba(255,255,255,190);
            }}
            QLabel#countLabel {{ color: rgba(30,58,95,170); font-size: 11px; padding: 0 6px; background: transparent; }}
            QLabel#emptyLabel {{ color: rgba(30,58,95,190); font-size: 15px; background: transparent; }}

            QLineEdit {{
                background: rgba(255,255,255,175);
                border: 1px solid rgba(255,255,255,215);
                border-radius: 16px; padding: 7px 14px;
                font-size: 12px; color: #2A4258;
                selection-background-color: rgba(120,180,230,180);
            }}
            QLineEdit:focus {{
                background: rgba(255,255,255,210);
                border: 1.5px solid rgba(140,195,240,200);
            }}
            QComboBox {{
                background: rgba(255,255,255,170);
                border: 1px solid rgba(255,255,255,210);
                border-radius: 14px; padding: 6px 12px;
                font-size: 12px; color: #2A4258;
            }}
            QComboBox:hover {{ background: rgba(255,255,255,210); }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QComboBox QAbstractItemView {{
                background: rgba(245,251,255,245);
                border: 1px solid rgba(170,210,240,200);
                border-radius: 12px;
                selection-background-color: rgba(130,190,240,160);
                outline: none; padding: 4px;
            }}
            QToolButton {{
                background: rgba(255,255,255,170);
                border: 1px solid rgba(255,255,255,210);
                border-radius: 14px; padding: 6px 12px;
                font-size: 12px; color: #2A4258;
            }}
            QToolButton:hover {{ background: rgba(255,255,255,220); }}
            QToolButton::menu-indicator {{ image: none; }}
            QToolButton#newButton {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 rgba(155,210,250,235), stop:1 rgba(90,160,220,235));
                color: white; font-weight: 700;
                border: 1px solid rgba(255,255,255,230);
            }}
            QToolButton#newButton:hover {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 rgba(170,220,255,245), stop:1 rgba(105,175,235,245));
            }}
            QToolButton#pinFab {{
                background: rgba(255,255,255,190);
                border: 1px solid rgba(255,255,255,230);
                border-radius: 15px; padding: 0; font-size: 13px;
            }}
            QToolButton#pinFab:checked {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 rgba(155,210,250,235), stop:1 rgba(90,160,220,235));
                border: 1px solid rgba(255,255,255,230);
            }}
            QPushButton {{
                background: rgba(255,255,255,170);
                border: 1px solid rgba(255,255,255,210);
                border-radius: 14px; padding: 6px 14px;
                font-size: 12px; color: #2A4258;
            }}
            QPushButton:hover {{ background: rgba(255,255,255,225); }}
            QPushButton:checked {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 rgba(155,210,250,235), stop:1 rgba(95,165,225,235));
                color: white; font-weight: 600;
                border: 1px solid rgba(255,255,255,220);
            }}

            /* Панель фильтров — GlassPanel рисует фон, стили для дочерних */
            GlassPanel QCheckBox {{
                color: #2A4258; font-size: 12px; spacing: 7px;
                background: transparent;
            }}
            GlassPanel QCheckBox::indicator {{
                width: 15px; height: 15px; border-radius: 4px;
                background: rgba(255,255,255,160);
                border: 1px solid rgba(130,170,210,160);
            }}
            GlassPanel QCheckBox::indicator:checked {{
                background: rgba(100,170,230,200);
                border: 1px solid rgba(80,140,200,200);
            }}

            QScrollArea {{ background: transparent; border: none; }}
            QWidget#board {{ background: transparent; }}
            QScrollBar:vertical {{
                background: rgba(255,255,255,60); width: 10px;
                border-radius: 5px; margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(90,140,190,130); border-radius: 5px; min-height: 40px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{
                background: rgba(255,255,255,60); height: 10px;
                border-radius: 5px; margin: 2px;
            }}
            QScrollBar::handle:horizontal {{
                background: rgba(90,140,190,130); border-radius: 5px; min-width: 40px;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
            {self._menu_qss()}
        """)

    def _apply_minimal_style(self) -> None:
        """Минимализм в духе Apple: плоско, бело, волосяные границы."""
        T, M, H, A = theme.MIN_TEXT, theme.MIN_MUTED, theme.MIN_HAIRLINE, theme.MIN_ACCENT
        self.setStyleSheet(f"""
            MainWindow, BackgroundWidget {{ background: {theme.MIN_BG}; }}
            GlassPanel {{ background: transparent; border: none; }}

            QLabel#brandLabel {{
                color: {T}; font-size: 14px; font-weight: 700;
                background: transparent; padding: 5px 10px; border: none;
            }}
            QLabel#clockLabel {{
                color: {M}; font-size: 12px; font-weight: 500;
                background: transparent; padding: 6px 8px; border: none;
            }}
            QLabel#countLabel {{ color: {M}; font-size: 11px; padding: 0 6px; background: transparent; }}
            QLabel#emptyLabel {{ color: {M}; font-size: 15px; background: transparent; }}

            QLineEdit {{
                background: #FFFFFF;
                border: 1px solid {H};
                border-radius: 10px; padding: 7px 12px;
                font-size: 12px; color: {T};
                selection-background-color: {A};
                selection-color: white;
            }}
            QLineEdit:focus {{ border: 1.5px solid {A}; }}
            QComboBox {{
                background: #FFFFFF; border: 1px solid {H};
                border-radius: 10px; padding: 6px 12px;
                font-size: 12px; color: {T};
            }}
            QComboBox:hover {{ background: #FAFAFC; }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QComboBox QAbstractItemView {{
                background: #FFFFFF; border: 1px solid {H};
                border-radius: 10px;
                selection-background-color: #F0F0F2;
                selection-color: {T};
                outline: none; padding: 4px;
            }}
            QToolButton {{
                background: #FFFFFF; border: 1px solid {H};
                border-radius: 10px; padding: 6px 12px;
                font-size: 12px; color: {T};
            }}
            QToolButton:hover {{ background: #F0F0F2; }}
            QToolButton:checked {{ background: {A}; color: white; border: none; }}
            QToolButton::menu-indicator {{ image: none; }}
            QToolButton#newButton {{
                background: {A}; color: white; font-weight: 600; border: none;
            }}
            QToolButton#newButton:hover {{ background: #0077ED; }}
            QToolButton#pinFab {{
                background: rgba(255,255,255,235); border: 1px solid {H};
                border-radius: 15px; padding: 0; font-size: 13px;
            }}
            QToolButton#pinFab:checked {{ background: {A}; border: none; }}
            QPushButton {{
                background: #FFFFFF; border: 1px solid {H};
                border-radius: 10px; padding: 6px 14px;
                font-size: 12px; color: {T};
            }}
            QPushButton:hover {{ background: #F0F0F2; }}
            QPushButton:checked {{
                background: {A}; color: white; font-weight: 600; border: none;
            }}

            GlassPanel QCheckBox {{
                color: {T}; font-size: 12px; spacing: 7px; background: transparent;
            }}
            GlassPanel QCheckBox::indicator {{
                width: 15px; height: 15px; border-radius: 4px;
                background: #FFFFFF; border: 1px solid {H};
            }}
            GlassPanel QCheckBox::indicator:checked {{
                background: {A}; border: 1px solid {A};
            }}

            QScrollArea {{ background: transparent; border: none; }}
            QWidget#board {{ background: transparent; }}
            QScrollBar:vertical {{
                background: transparent; width: 10px;
                border-radius: 5px; margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(0,0,0,55); border-radius: 5px; min-height: 40px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{
                background: transparent; height: 10px;
                border-radius: 5px; margin: 2px;
            }}
            QScrollBar::handle:horizontal {{
                background: rgba(0,0,0,55); border-radius: 5px; min-width: 40px;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
            {self._menu_qss()}
        """)
