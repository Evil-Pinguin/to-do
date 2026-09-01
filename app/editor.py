# -*- coding: utf-8 -*-
"""Редактор заметки: заголовок + контент по типу + картинки + автосохранение.

Автосохранение: сохраняем примерно через секунду после того, как человек
перестал печатать. При этом одно открытие/редактирование считается одной
сессией правок — «Изменено: N раз» растёт на 1 за сессию, а не за символ.
"""
from __future__ import annotations

from datetime import timedelta
from typing import List, Optional

from PySide6.QtCore import QBuffer, QIODevice, Qt, QTimer, Signal, QDateTime, QSize, QRectF
from PySide6.QtGui import QImage, QPixmap, QKeySequence, QShortcut, QColor, QPainter
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateTimeEdit, QDialog, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QTextEdit,
    QToolButton, QVBoxLayout, QWidget, QApplication,
)

from . import colors as C
from .db import Database
from .formatting import fmt_dt, plural, now_dt
from .glass import paint_bubble_glass
from .models import ListItem, dump_list, TYPE_LIST, TYPE_TASK, PRIORITIES

AUTOSAVE_MS = 1000  # пауза после ввода, после которой сохраняем
MAX_IMAGE_SIDE = 1600


def compress_image(data: bytes) -> bytes:
    """Уменьшаем очень большие картинки, чтобы база не распухала."""
    img = QImage.fromData(data)
    if img.isNull():
        return data
    if len(data) <= 400 * 1024:
        return data
    scaled = img
    if max(img.width(), img.height()) > MAX_IMAGE_SIDE:
        scaled = img.scaled(MAX_IMAGE_SIDE, MAX_IMAGE_SIDE,
                            Qt.KeepAspectRatio, Qt.SmoothTransformation)
    buf = QBuffer()
    buf.open(QIODevice.ReadWrite)
    fmt = "PNG" if scaled.hasAlphaChannel() else "JPG"
    scaled.save(buf, fmt, 86)
    return bytes(buf.data())


class ListRow(QFrame):
    """Строка списка: ☐ | текст | ✕"""

    changed = Signal()
    toggled = Signal(bool)

    def __init__(self, text: str = "", done: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setStyleSheet(
            "ListRow { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 rgba(255,255,255,190), stop:1 rgba(240,250,255,165)); border: 1px solid rgba(255,255,255,210); border-radius: 11px; }"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 3, 4, 3)
        lay.setSpacing(6)

        self.checkbox = QCheckBox(self)
        self.checkbox.setChecked(done)
        self.checkbox.setStyleSheet("QCheckBox { font-size: 14px; }")
        self.edit = QLineEdit(text, self)
        self.edit.setFrame(False)
        self.edit.setStyleSheet(
            "QLineEdit { background: transparent; font-size: 13px; border: none; }"
        )
        self.edit.setPlaceholderText("Новый пункт…")
        self.del_btn = QToolButton(self)
        self.del_btn.setText("✕")
        self.del_btn.setFixedSize(24, 24)
        self.del_btn.setStyleSheet(
            "QToolButton { border: none; border-radius: 8px; color:#8aa0b4;"
            " font-size: 11px; } QToolButton:hover { background: rgba(220,90,90,60);"
            " color: #c94f4f; }"
        )

        lay.addWidget(self.checkbox, 0)
        lay.addWidget(self.edit, 1)
        lay.addWidget(self.del_btn, 0)

    def text(self) -> str:
        return self.edit.text()

    def is_done(self) -> bool:
        return self.checkbox.isChecked()


class NoteEditor(QDialog):
    def __init__(self, db: Database, note_id: int, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.db = db
        self.note = db.note_by_id(note_id)
        assert self.note is not None
        self.deleted_on_close = False

        self._loading = True
        self._opened_new = self.note.edit_count == 0
        self._dirty: set = set()          # что меняли с прошлого сохранения
        self._logged: set = set()          # события, уже записанные в историю за сессию
        self._session_counted = False      # +1 «Изменено N раз» только раз за сессию
        self._list_rows: List[ListRow] = []
        self._image_rows: List[tuple[int, bytes]] = [
            (r["id"], bytes(r["data"])) for r in db.images(note_id)
        ]

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(AUTOSAVE_MS)
        self._timer.timeout.connect(self._commit)

        self.setWindowTitle("Редактирование")
        self.resize(660, 720)
        self.setMinimumSize(560, 560)
        self._apply_bg()

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 12)
        root.setSpacing(10)

        # ---------- заголовок ----------
        self.title_edit = QLineEdit(self.note.title, self)
        self.title_edit.setPlaceholderText("Заголовок…")
        self.title_edit.setStyleSheet(
            "QLineEdit {"
            " background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "   stop:0 rgba(255,255,255,215), stop:1 rgba(240,250,255,195));"
            " border: 1px solid rgba(255,255,255,230);"
            " border-radius: 14px; padding: 10px 14px;"
            " font-size: 16px; font-weight: 700; color: #23405E;"
            "}"
            "QLineEdit:focus {"
            " background: rgba(255,255,255,235);"
            " border: 1.5px solid rgba(140,195,240,210);"
            "}"
        )
        self.title_edit.textChanged.connect(lambda: self._touch("title"))
        root.addWidget(self.title_edit)

        # ---------- контент по типу ----------
        if self.note.type == TYPE_LIST:
            root.addWidget(self._build_list_ui(), 1)
        elif self.note.type == TYPE_TASK:
            root.addWidget(self._build_task_meta(), 0)
            root.addWidget(self._build_text_ui(
                placeholder="Описание задачи…"), 1)
        else:
            root.addWidget(self._build_text_ui(
                placeholder="Пишите свободно — всё сохранится автоматически…"), 1)

        # ---------- картинки ----------
        root.addWidget(self._build_images_ui())

        # ---------- нижняя строка ----------
        footer = QHBoxLayout()
        self.created_label = QLabel("", self)
        self.created_label.setStyleSheet(f"color: {C.TEXT_MUTED}; font-size: 11px;")
        footer.addWidget(self.created_label)
        footer.addStretch(1)
        self.save_label = QLabel("Автосохранение включено", self)
        self.save_label.setStyleSheet(f"color: {C.TEXT_MUTED}; font-size: 11px;")
        footer.addWidget(self.save_label)
        root.addLayout(footer)

        self._update_created_label()
        self._loading = False

        self.finished.connect(self._finish)

        # первое добавление пустой строки в новый список
        if self.note.type == TYPE_LIST and not self.note.list_items():
            QTimer.singleShot(50, lambda: self._add_row(focus=True, touch=False))

    # ==================================================================
    #  Сборка интерфейса
    # ==================================================================
    def _apply_bg(self) -> None:
        # Фон рисуем вручную в paintEvent — «пузырьковое» стекло цвета
        # заметки поверх светлого неба (см. app/glass.py).
        self.setStyleSheet("NoteEditor { background: transparent; }")
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        # подложка — оттенок неба с обоев, виден в скруглённых углах
        p.fillRect(self.rect(), QColor("#DDF2F8"))
        rect = QRectF(self.rect()).adjusted(3.5, 3.5, -3.5, -3.5)
        paint_bubble_glass(
            p, rect, 18.0,
            base_rgb=C.base_rgb(self.note.color),
            body_alpha=170,         # плотнее карточек: под ним поля ввода
            reflex_alpha=45,
        )
        p.end()
        super().paintEvent(event)

    def _build_text_ui(self, placeholder: str = "") -> QTextEdit:
        self.text_edit = QTextEdit(self.note.content, self)
        self.text_edit.setPlaceholderText(placeholder)
        self.text_edit.setStyleSheet(
            "QTextEdit {"
            " background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "   stop:0 rgba(255,255,255,210), stop:1 rgba(240,250,255,195));"
            " border: 1px solid rgba(255,255,255,230);"
            " border-radius: 14px; padding: 12px;"
            " font-size: 13px; color: #2a4258;"
            "}"
            "QTextEdit:focus {"
            " background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "   stop:0 rgba(255,255,255,230), stop:1 rgba(240,250,255,215));"
            " border: 1.5px solid rgba(140,195,240,210);"
            "}"
        )
        self.text_edit.textChanged.connect(lambda: self._touch("text"))
        return self.text_edit

    def _build_task_meta(self) -> QWidget:
        frame = QFrame(self)
        frame.setStyleSheet(
            "QFrame { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            " stop:0 rgba(255,255,255,195), stop:1 rgba(240,250,255,175));"
            " border: 1px solid rgba(255,255,255,220); border-radius: 14px; }"
        )
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(10)

        self.dl_check = QCheckBox("Дедлайн:", frame)
        has_dl = bool(self.note.deadline)
        self.dl_check.setChecked(has_dl)
        self.dl_check.toggled.connect(self._on_dl_toggle)

        self.dl_edit = QDateTimeEdit(frame)
        self.dl_edit.setCalendarPopup(True)
        self.dl_edit.setDisplayFormat("dd.MM.yyyy HH:mm")
        dt = now_dt() + timedelta(days=1)
        dt = dt.replace(hour=18, minute=0, second=0, microsecond=0)
        if has_dl:
            from .formatting import parse_ts
            parsed = parse_ts(self.note.deadline)
            if parsed:
                self.dl_edit.setDateTime(QDateTime(parsed))
        else:
            self.dl_edit.setDateTime(QDateTime(dt))
        self.dl_edit.setEnabled(has_dl)
        self.dl_edit.dateTimeChanged.connect(lambda _: self._touch("deadline"))

        lay.addWidget(self.dl_check)
        lay.addWidget(self.dl_edit, 1)

        lay.addWidget(QLabel("Приоритет:", frame))
        self.prio_combo = QComboBox(frame)
        self.prio_combo.addItem("—", None)
        self.prio_combo.addItem("Высокий", "high")
        self.prio_combo.addItem("Средний", "medium")
        self.prio_combo.addItem("Низкий", "low")
        idx = {p: i + 1 for i, p in enumerate(PRIORITIES)}.get(self.note.priority or "", 0)
        self.prio_combo.setCurrentIndex(idx)
        self.prio_combo.currentIndexChanged.connect(lambda _: self._touch("priority"))
        lay.addWidget(self.prio_combo)

        self.task_done = QCheckBox("Выполнено", frame)
        self.task_done.setChecked(bool(self.note.done))
        self.task_done.toggled.connect(self._on_task_done)
        lay.addWidget(self.task_done)
        return frame

    def _build_list_ui(self) -> QWidget:
        area = QScrollArea(self)
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        holder = QWidget()
        self.list_lay = QVBoxLayout(holder)
        self.list_lay.setContentsMargins(0, 0, 0, 0)
        self.list_lay.setSpacing(5)
        self.list_lay.addStretch(1)

        for item in self.note.list_items():
            self._add_row(item.text, item.done)

        add_btn = QPushButton("+  Добавить пункт", self)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,150); border: 1px dashed"
            " rgba(120,150,180,170); border-radius: 10px; padding: 7px;"
            " color: #35506E; font-size: 12px; }"
            "QPushButton:hover { background: rgba(255,255,255,210); }"
        )
        add_btn.clicked.connect(lambda: self._add_row(focus=True))

        wrap = QVBoxLayout()
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.addWidget(area, 1)
        wrap.addWidget(add_btn)
        area.setWidget(holder)

        outer = QWidget(self)
        ol = QVBoxLayout(outer)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.addLayout(wrap)
        return outer

    def _build_images_ui(self) -> QWidget:
        group = QWidget(self)
        v = QVBoxLayout(group)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)

        head = QHBoxLayout()
        cap = QLabel("Изображения", group)
        cap.setStyleSheet(
            f"color: {C.TEXT_DARK}; font-size: 11px; font-weight: 700;"
        )
        head.addWidget(cap)
        hint = QLabel("Ctrl+Shift+V — вставить картинку из буфера", group)
        hint.setStyleSheet(f"color: {C.TEXT_MUTED}; font-size: 10px;")
        head.addStretch(1)
        head.addWidget(hint)
        v.addLayout(head)

        area = QScrollArea(group)
        area.setFixedHeight(116)
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:horizontal { height: 8px; }"
        )
        holder = QWidget()
        self.images_lay = QHBoxLayout(holder)
        self.images_lay.setContentsMargins(0, 0, 0, 0)
        self.images_lay.setSpacing(8)
        self.images_lay.addStretch(1)
        area.setWidget(holder)
        v.addWidget(area)

        QShortcut(QKeySequence("Ctrl+Shift+V"), self, self._paste_image)
        self._rebuild_images()
        return group

    # ==================================================================
    #  Список
    # ==================================================================
    def _add_row(self, text: str = "", done: bool = False, focus: bool = False,
                touch: bool = True) -> ListRow:
        row = ListRow(text, done, self)
        index = len(self._list_rows)
        row.checkbox.toggled.connect(
            lambda checked, r=row: self._on_row_toggled(r, checked))
        row.edit.textChanged.connect(lambda: self._touch("list"))
        row.edit.returnPressed.connect(lambda: self._add_row(focus=True))
        row.del_btn.clicked.connect(lambda _=False, r=row: self._remove_row(r))
        self._list_rows.append(row)
        # вставляем перед stretch
        self.list_lay.insertWidget(index, row)
        if focus:
            row.edit.setFocus()
        if not self._loading and touch:
            self._touch("list")
        return row

    def _remove_row(self, row: ListRow) -> None:
        if row in self._list_rows:
            self._list_rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self._touch("list")

    def _on_row_toggled(self, row: ListRow, checked: bool) -> None:
        if self._loading:
            return
        self._touch("item_checked")

    def _collect_items(self) -> List[ListItem]:
        return [ListItem(r.text(), r.is_done()) for r in self._list_rows]

    # ==================================================================
    #  Задача
    # ==================================================================
    def _on_dl_toggle(self, on: bool) -> None:
        self.dl_edit.setEnabled(on)
        self._touch("deadline")

    def _on_task_done(self, on: bool) -> None:
        self._touch("task_done" if on else "task_undone")

    # ==================================================================
    #  Картинки
    # ==================================================================
    def _rebuild_images(self) -> None:
        while self.images_lay.count() > 1:
            item = self.images_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        add_btn = QToolButton(self)
        add_btn.setText("+")
        add_btn.setFixedSize(QSize(92, 92))
        add_btn.setToolTip("Добавить изображение")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet(
            "QToolButton { background: rgba(255,255,255,150); border: 1px dashed"
            " rgba(120,150,180,170); border-radius: 12px; font-size: 20px;"
            " color: #35506E; } QToolButton:hover { background: rgba(255,255,255,215); }"
        )
        add_btn.clicked.connect(self._pick_image)
        self.images_lay.insertWidget(0, add_btn)

        for img_id, blob in self._image_rows:
            tile = QWidget()
            tl = QVBoxLayout(tile)
            tl.setContentsMargins(0, 0, 0, 0)
            tl.setSpacing(0)
            lab = QLabel()
            pm = QPixmap()
            pm.loadFromData(blob)
            lab.setPixmap(pm.scaled(92, 78, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            lab.setFixedSize(QSize(92, 78))
            lab.setAlignment(Qt.AlignCenter)
            lab.setStyleSheet(
                "background: rgba(255,255,255,170); border-radius: 10px;"
            )
            btn = QToolButton(tile)
            btn.setText("✕")
            btn.setFixedSize(20, 20)
            btn.setStyleSheet(
                "QToolButton { border: none; border-radius: 8px; background:"
                " rgba(255,255,255,190); color:#c94f4f; font-size: 9px; }"
                "QToolButton:hover { background: rgba(220,90,90,190); color: white; }"
            )
            btn.clicked.connect(lambda _=False, iid=img_id: self._remove_image(iid))
            tl.addWidget(lab)
            tl.addWidget(btn, 0, Qt.AlignRight | Qt.AlignTop)
            # кнопку поверх правого верхнего угла
            btn.raise_()
            self.images_lay.insertWidget(self.images_lay.count() - 1, tile)

    def _pick_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Добавить изображение", "",
            "Изображения (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;Все файлы (*)")
        if path:
            with open(path, "rb") as f:
                self._store_image(f.read())

    def _paste_image(self) -> None:
        clipboard = QApplication.clipboard()
        pm = clipboard.pixmap()
        if not pm.isNull():
            buf = QBuffer()
            buf.open(QIODevice.ReadWrite)
            pm.toImage().save(buf, "PNG")
            self._store_image(bytes(buf.data()))

    def _store_image(self, data: bytes) -> None:
        if QImage.fromData(data).isNull():
            return
        blob = compress_image(data)
        img_id = self.db.add_image(self.note.id, blob)
        self._image_rows.append((img_id, blob))
        self._rebuild_images()
        self._touch("image_added")

    def _remove_image(self, img_id: int) -> None:
        self.db.delete_image(img_id)
        self._image_rows = [(i, b) for i, b in self._image_rows if i != img_id]
        self._rebuild_images()
        self._touch("image_removed")

    # ==================================================================
    #  Автосохранение
    # ==================================================================
    def _touch(self, key: str) -> None:
        if self._loading:
            return
        self._dirty.add(key)
        self.save_label.setText("Сохранение…")
        self._timer.start()  # перезапускаем отсчёт: сохраняем через 1с тишины

    def _commit(self) -> None:
        if not self._dirty:
            return
        note = self.note
        note.title = self.title_edit.text().strip()
        if note.type == TYPE_LIST:
            items = self._collect_items()
            note.content = dump_list(items)
            note.done = bool(items) and all(i.done for i in items)
        elif note.type == TYPE_TASK:
            note.content = self.text_edit.toPlainText()
            note.deadline = (self.dl_edit.dateTime().toString("yyyy-MM-dd HH:mm:ss")
                             if self.dl_check.isChecked() else None)
            note.priority = self.prio_combo.currentData()
            note.done = self.task_done.isChecked()
        else:
            note.content = self.text_edit.toPlainText()

        new_events = [k for k in self._dirty if k not in self._logged]
        self.db.save_note(note, new_events, count_edit=not self._session_counted)
        self._logged |= self._dirty
        self._session_counted = True
        self._dirty.clear()
        self._update_created_label()
        self.save_label.setText(f"Сохранено ✓ {now_dt().strftime('%H:%M:%S')}")

    def _update_created_label(self) -> None:
        n = self.note
        times = f"Создано: {fmt_dt(n.created_at)}   ·   Изменено: {n.edit_count} " \
                f"{plural(n.edit_count, 'раз', 'раза', 'раз')}" if n.edit_count \
                else f"Создано: {fmt_dt(n.created_at)}"
        self.created_label.setText(times)

    # ==================================================================
    #  Закрытие
    # ==================================================================
    def _finish(self) -> None:
        self._commit()
        # только что созданную и оставленную пустой заметку — убираем
        if self._opened_new and self._is_empty():
            self.db.delete_note(self.note.id)
            self.deleted_on_close = True

    def _is_empty(self) -> bool:
        n = self.note
        if n.title.strip():
            return False
        if self._image_rows:
            return False
        if n.type == TYPE_LIST:
            items = self._collect_items()
            return not any(i.text.strip() for i in items)
        if n.type == TYPE_TASK:
            if n.content.strip():
                return False
            return not (self.dl_check.isChecked() or n.priority)
        return not n.content.strip()
