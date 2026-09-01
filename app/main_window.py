# -*- coding: utf-8 -*-
"""Главное окно Aero Notes: сетка карточек, часы, поиск, сортировка, фильтры."""
from __future__ import annotations

import random
from typing import List, Optional

from PySide6.QtCore import QEvent, QRect, Qt, QTimer, QSize
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu, QPushButton,
    QScrollArea, QToolButton, QVBoxLayout, QWidget, QMessageBox,
)

from . import colors as C
from .db import Database
from .details_dialog import DetailsDialog
from .editor import NoteEditor
from .formatting import fmt_clock, now_dt, plural
from .models import Note, TYPE_LIST, TYPE_NOTE, TYPE_TASK, TYPE_NAMES
from .note_card import NoteCard

ASSETS_DIR = (__import__("pathlib").Path(__file__).resolve().parent.parent / "assets")

SORT_MODES = [
    ("created", "По дате создания"),
    ("modified", "По дате изменения"),
    ("title", "По теме"),
    ("color", "По цвету"),
    ("status", "По статусу"),
]


class BackgroundWidget(QWidget):
    """Рисует обои Frutiger Aero + мягкую светлую вуаль, чтобы карточки читались."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._pix: Optional[QPixmap] = None
        path = ASSETS_DIR / "backdrop.jpg"
        if path.exists():
            pm = QPixmap(str(path))
            if not pm.isNull():
                self._pix = pm

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        rect = self.rect()
        if self._pix is None:
            # запасной градиент, если файла нет
            top, bottom = QColor("#DFF1FB"), QColor("#E9F8EC")
            from PySide6.QtGui import QLinearGradient
            grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            grad.setColorAt(0.0, top)
            grad.setColorAt(1.0, bottom)
            p.fillRect(rect, grad)
        else:
            pw, ph = self._pix.width(), self._pix.height()
            scale = max(rect.width() / pw, rect.height() / ph)
            tw, th = int(pw * scale), int(ph * scale)
            x, y = (rect.width() - tw) // 2, (rect.height() - th) // 2
            p.drawPixmap(x, y, tw, th, self._pix)
        # вуаль
        p.fillRect(rect, QColor(255, 255, 255, 58))
        veil = QColor(255, 255, 255, 70)
        p.fillRect(QRect(0, 0, rect.width(), 140), veil)
        p.end()


class MainWindow(QMainWindow):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.setWindowTitle("Aero Notes — заметки и задачи")
        self.resize(1340, 850)
        self.setMinimumSize(1020, 660)

        self._cards: List[NoteCard] = []
        self._cols = 0
        self.sort_desc = True

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(14, 10, 14, 12)
        outer.setSpacing(10)

        # фон
        self.bg = BackgroundWidget(central)
        self.bg.lower()

        outer.addWidget(self._build_top_bar())
        body = QHBoxLayout()
        body.setSpacing(10)
        outer.addLayout(body, 1)

        self._build_filter_panel()
        body.addWidget(self.filter_panel)

        self._build_board()
        body.addWidget(self.scroll, 1)

        self._apply_style()
        self._start_clock()

        self.scroll.viewport().installEventFilter(self)
        QTimer.singleShot(0, self.refresh)

    # ==================================================================
    #  Верхняя панель (стекло)
    # ==================================================================
    def _build_top_bar(self) -> QFrame:
        bar = QFrame(self)
        bar.setObjectName("topBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)

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
        return bar

    # ==================================================================
    #  Панель фильтров (маленькая, раскрывающаяся)
    # ==================================================================
    def _build_filter_panel(self) -> None:
        panel = QFrame(self)
        panel.setObjectName("filterPanel")
        panel.setFixedWidth(235)
        panel.setVisible(False)
        self.filter_panel = panel
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(6)

        head = QHBoxLayout()
        t = QLabel("Фильтр", panel)
        t.setStyleSheet("font-size: 13px; font-weight: 700; color: #23405E;")
        head.addWidget(t)
        head.addStretch(1)
        reset = QPushButton("Сбросить", panel)
        reset.setFlat(True)
        reset.setStyleSheet("color: #4a7db3; font-size: 11px; border: none;")
        reset.clicked.connect(self._reset_filters)
        head.addWidget(reset)
        lay.addLayout(head)

        lay.addWidget(self._section("Группы"))
        self.group_checks: List[tuple[int, QCheckBox]] = []
        self._rebuild_group_checks()
        add_group = QPushButton("+ Новая группа…", panel)
        add_group.setFlat(True)
        add_group.setStyleSheet("color: #4a7db3; font-size: 11px; border: none;")
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
                f"QToolButton {{ background: {hexcol}; border: 1px solid rgba(60,90,120,120);"
                f" border-radius: 8px; }}"
                f"QToolButton:checked {{ border: 2px solid #3a6ea5; }}"
            )
            b.toggled.connect(lambda _, k=key: self.refresh())
            self.color_btns[key] = b
            colors_row.addWidget(b)
        lay.addLayout(colors_row)

        lay.addStretch(1)

    def _section(self, text: str) -> QLabel:
        lab = QLabel(text.upper(), self.filter_panel)
        lab.setStyleSheet(
            "color: #5A7188; font-size: 10px; font-weight: 700; letter-spacing: 1px;"
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
        # после заголовка раздела «Группы» (индексы 0–1) идут чекбоксы
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
        self.filter_panel.setVisible(on)

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

        self.empty_label = QLabel("Здесь пока пусто — создайте первую заметку ✦", board)
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
            # статус: сначала активные, затем по дедлайну
            return (1 if n.is_done() else 0, n.deadline or "")

        pinned = sorted((n for n in notes if n.pinned), key=key, reverse=self.sort_desc)
        rest = sorted((n for n in notes if not n.pinned), key=key, reverse=self.sort_desc)
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
        vw = max(self.scroll.viewport().width() - 12, 240)
        cols = max(2, min(6, vw // 300))
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
    #  Действия
    # ==================================================================
    def _create_note(self, ntype: str) -> None:
        color = random.choice(list(C.PALETTE.keys()))
        note = self.db.create_note(ntype, color=color)
        if self.archive_btn.isChecked():
            self.archive_btn.setChecked(False)
        self._open_editor(note.id)

    def _open_editor(self, note_id: int) -> None:
        editor = NoteEditor(self.db, note_id, self)
        editor.exec()
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
        return """
            QMenu { background: rgba(250,252,255,245); border: 1px solid rgba(140,170,200,190);
                    border-radius: 12px; padding: 6px; font-size: 13px; color: #2A4258; }
            QMenu::item { padding: 6px 26px 6px 12px; border-radius: 8px; }
            QMenu::item:selected { background: rgba(120,180,230,150); }
            QMenu::separator { height: 1px; background: rgba(140,170,200,110); margin: 5px 8px; }
        """

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            MainWindow, BackgroundWidget {{ background: #E4F2FB; }}
            QFrame#topBar {{
                background: rgba(255,255,255,120);
                border: 1px solid rgba(255,255,255,170);
                border-radius: 18px;
            }}
            QLabel#brandLabel {{
                color: #23507E; font-size: 14px; font-weight: 800;
                background: rgba(255,255,255,90); border-radius: 12px; padding: 5px 12px;
            }}
            QLabel#clockLabel {{
                color: #1E3A5F; font-size: 12px; font-weight: 600;
                background: rgba(255,255,255,80); border-radius: 12px; padding: 6px 12px;
            }}
            QLabel#countLabel {{ color: rgba(30,58,95,170); font-size: 11px; padding: 0 6px; }}
            QLabel#emptyLabel {{ color: rgba(30,58,95,190); font-size: 15px; }}

            QLineEdit {{
                background: rgba(255,255,255,160); border: 1px solid rgba(255,255,255,200);
                border-radius: 16px; padding: 7px 14px; font-size: 12px; color: #2A4258;
                selection-background-color: rgba(120,180,230,180);
            }}
            QComboBox {{
                background: rgba(255,255,255,160); border: 1px solid rgba(255,255,255,200);
                border-radius: 14px; padding: 6px 12px; font-size: 12px; color: #2A4258;
            }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QComboBox QAbstractItemView {{
                background: rgba(252,253,255,245); border: 1px solid rgba(140,170,200,190);
                border-radius: 10px; selection-background-color: rgba(120,180,230,150);
                outline: none; padding: 4px;
            }}
            QToolButton {{
                background: rgba(255,255,255,160); border: 1px solid rgba(255,255,255,200);
                border-radius: 14px; padding: 6px 12px; font-size: 12px; color: #2A4258;
            }}
            QToolButton:hover {{ background: rgba(255,255,255,215); }}
            QToolButton::menu-indicator {{ image: none; }}
            QToolButton#newButton {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 rgba(150,205,245,235), stop:1 rgba(95,165,220,235));
                color: white; font-weight: 700; border: 1px solid rgba(255,255,255,220);
            }}
            QToolButton#newButton:hover {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 rgba(165,215,250,245), stop:1 rgba(110,180,235,245));
            }}
            QPushButton {{
                background: rgba(255,255,255,160); border: 1px solid rgba(255,255,255,200);
                border-radius: 14px; padding: 6px 14px; font-size: 12px; color: #2A4258;
            }}
            QPushButton:hover {{ background: rgba(255,255,255,215); }}
            QPushButton:checked {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 rgba(150,205,245,235), stop:1 rgba(100,168,225,235));
                color: white; font-weight: 600;
            }}
            QFrame#filterPanel {{
                background: rgba(255,255,255,130);
                border: 1px solid rgba(255,255,255,170); border-radius: 16px;
            }}
            QFrame#filterPanel QCheckBox {{ color: #2A4258; font-size: 12px; spacing: 7px; }}

            QScrollArea {{ background: transparent; border: none; }}
            QWidget#board {{ background: transparent; }}
            QScrollBar:vertical {{
                background: rgba(255,255,255,60); width: 10px; border-radius: 5px; margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(90,140,190,140); border-radius: 5px; min-height: 40px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{
                background: rgba(255,255,255,60); height: 10px; border-radius: 5px; margin: 2px;
            }}
            QScrollBar::handle:horizontal {{
                background: rgba(90,140,190,140); border-radius: 5px; min-width: 40px;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
            {self._menu_qss()}
        """)
