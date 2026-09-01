# -*- coding: utf-8 -*-
"""Песочница — свободный холст со связями между заметками.

Открывается кнопкой-пузырём рядом с «+». На холст можно добавить
существующие заметки или создать новые, таскать их свободно мышкой.
У карточки по краям — маленькие пузырьки-порты (видны при наведении):
клик по порту → выбор «стрелка/линия» → клик по другой карточке — связь.

Раскладка хранится в data/sandbox.json, сами заметки — в общей базе.
"""
from __future__ import annotations

import json
from typing import List, Optional

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor, QCursor, QFont, QFontMetrics, QPainter, QPainterPath, QPen,
    QPixmap, QPolygonF,
)
from PySide6.QtWidgets import (
    QFrame, QMainWindow, QMenu, QScrollArea, QWidget,
)

from . import colors as C
from . import theme
from .bubbles import BubbleButton
from .db import Database, DATA_DIR
from .editor import NoteEditor
from .glass import paint_bubble_card
from .models import Note, TYPE_LIST, TYPE_TASK, TYPE_NOTE, TYPE_NAMES
from .paths import ASSETS_DIR

SANDBOX_PATH = DATA_DIR / "sandbox.json"

CANVAS_W, CANVAS_H = 2600, 1800
TYPE_EMOJI = {TYPE_NOTE: "📝", TYPE_LIST: "☑", TYPE_TASK: "🎯"}


# ---------------------------------------------------------------------------
#  Карточка на холсте
# ---------------------------------------------------------------------------

class SandboxCard(QFrame):
    W, H = 232, 128
    PORT_R = 7          # радиус пузырька-порта
    PORT_HIT = 14       # зона клика по порту

    port_clicked = Signal(object, str)   # (card, side)
    clicked_while_linking = Signal(object)
    moved = Signal()
    open_requested = Signal(object)
    remove_requested = Signal(object)

    def __init__(self, note: Note, parent: QWidget):
        super().__init__(parent)
        self.note = note
        self.setFixedSize(QSize(self.W, self.H))
        self.setMouseTracking(True)
        self.setCursor(Qt.OpenHandCursor)
        self._drag_off: Optional[QPoint] = None
        self._hover = False

    # -- геометрия портов ------------------------------------------------
    def ports(self) -> dict[str, QPointF]:
        w, h = self.width(), self.height()
        return {
            "top": QPointF(w / 2, 7),
            "bottom": QPointF(w / 2, h - 7),
            "left": QPointF(7, h / 2),
            "right": QPointF(w - 7, h / 2),
        }

    def port_scene_pos(self, side: str) -> QPointF:
        pt = self.ports()[side]
        return QPointF(self.x() + pt.x(), self.y() + pt.y())

    def _port_at(self, pos: QPoint) -> Optional[str]:
        for side, pt in self.ports().items():
            if (QPointF(pos) - pt).manhattanLength() <= self.PORT_HIT:
                return side
        return None

    # -- отрисовка ---------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        paint_bubble_card(
            p, rect, 14.0,
            base_rgb=C.base_rgb(self.note.color),
            hover=self._hover,
        )

        minimal = theme.is_minimal()
        dark = QColor(theme.MIN_TEXT) if minimal else QColor(C.TEXT_DARK)
        muted = QColor(theme.MIN_MUTED) if minimal else QColor(C.TEXT_MUTED)

        pad = 16
        f = QFont(self.font())
        f.setPixelSize(12)
        f.setBold(True)
        p.setFont(f)
        p.setPen(dark)
        fm = QFontMetrics(f)
        emoji = TYPE_EMOJI.get(self.note.type, "📝")
        title = fm.elidedText(
            f"{emoji} {self.note.display_title}", Qt.ElideRight,
            self.width() - 2 * pad,
        )
        p.drawText(QRect(pad, 12, self.width() - 2 * pad, 18), Qt.AlignLeft, title)

        f2 = QFont(self.font())
        f2.setPixelSize(10)
        p.setFont(f2)
        p.setPen(muted)
        snippet = self._snippet()
        p.drawText(
            QRect(pad, 34, self.width() - 2 * pad, self.height() - 46),
            Qt.AlignLeft | Qt.TextWordWrap, snippet,
        )

        # порты-пузырьки — только при наведении
        if self._hover:
            for side, pt in self.ports().items():
                self._draw_port(p, pt)
        p.end()

    def _draw_port(self, p: QPainter, pt: QPointF) -> None:
        r = float(self.PORT_R)
        if theme.is_minimal():
            p.setPen(QPen(QColor(theme.MIN_ACCENT), 1.4))
            p.setBrush(QColor(255, 255, 255, 240))
            p.drawEllipse(pt, r, r)
            return
        # мини-пузырёк: полупрозрачный, с холодной кромкой и бликом
        p.setPen(QPen(QColor(125, 170, 195, 200), 1.4))
        p.setBrush(QColor(236, 251, 255, 150))
        p.drawEllipse(pt, r, r)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 220))
        p.drawEllipse(QPointF(pt.x() - r * 0.3, pt.y() - r * 0.35), r * 0.3, r * 0.3)

    def _snippet(self) -> str:
        n = self.note
        if n.type == TYPE_LIST:
            items = n.list_items()[:4]
            lines = [("☑ " if i.done else "☐ ") + i.text for i in items]
            return "\n".join(lines) or "Пустой список"
        text = (n.content or "").strip().replace("\r", "")
        return text[:160] or "Пустая заметка"

    # -- мышь ---------------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        canvas = self.parent()
        if event.button() == Qt.LeftButton:
            if getattr(canvas, "pending_link", None) is not None:
                self.clicked_while_linking.emit(self)
                return
            side = self._port_at(event.position().toPoint())
            if side is not None:
                self.port_clicked.emit(self, side)
                return
            self._drag_off = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            self.raise_()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        canvas = self.parent()
        if self._drag_off is not None:
            new = self.pos() + event.position().toPoint() - self._drag_off
            x = max(0, min(canvas.width() - self.width(), new.x()))
            y = max(0, min(canvas.height() - self.height(), new.y()))
            self.move(x, y)
            canvas.update()
        elif getattr(canvas, "pending_link", None) is not None:
            canvas.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_off is not None:
            self._drag_off = None
            self.setCursor(Qt.OpenHandCursor)
            self.moved.emit()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.open_requested.emit(self)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        m = QMenu(self)
        win = self.window()
        if hasattr(win, "menu_qss"):
            m.setStyleSheet(win.menu_qss())
        m.addAction("Открыть", lambda: self.open_requested.emit(self))
        m.addAction("Убрать с холста", lambda: self.remove_requested.emit(self))
        m.exec(event.globalPos())

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)


# ---------------------------------------------------------------------------
#  Холст
# ---------------------------------------------------------------------------

class SandboxCanvas(QWidget):
    changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(CANVAS_W, CANVAS_H)
        self.setMouseTracking(True)
        self.cards: List[SandboxCard] = []
        # связи: {"a": note_id, "b": note_id, "arrow": bool}
        self.links: List[dict] = []
        # незавершённая связь: (карточка, сторона, стрелка?)
        self.pending_link: Optional[tuple] = None

        self._pix: Optional[QPixmap] = None
        path = ASSETS_DIR / "backdrop.jpg"
        if path.exists():
            pm = QPixmap(str(path))
            if not pm.isNull():
                self._pix = pm

    # -- связи ----------------------------------------------------------
    def start_link(self, card: SandboxCard, side: str, arrow: bool) -> None:
        self.pending_link = (card, side, arrow)
        self.setCursor(Qt.CrossCursor)
        self.update()

    def cancel_link(self) -> None:
        self.pending_link = None
        self.unsetCursor()
        self.update()

    def finish_link(self, target: SandboxCard) -> None:
        if self.pending_link is None:
            return
        src, _side, arrow = self.pending_link
        if target is not src:
            a, b = src.note.id, target.note.id
            already = any(
                {lk["a"], lk["b"]} == {a, b} for lk in self.links
            )
            if not already:
                self.links.append({"a": a, "b": b, "arrow": arrow})
                self.changed.emit()
        self.cancel_link()

    def card_by_note(self, note_id: int) -> Optional[SandboxCard]:
        for c in self.cards:
            if c.note.id == note_id:
                return c
        return None

    def remove_card(self, card: SandboxCard) -> None:
        nid = card.note.id
        self.links = [lk for lk in self.links if nid not in (lk["a"], lk["b"])]
        self.cards.remove(card)
        card.deleteLater()
        self.update()
        self.changed.emit()

    # -- геометрия связей -------------------------------------------------
    def _endpoints(self, ca: SandboxCard, cb: SandboxCard) -> tuple[QPointF, QPointF]:
        """Ближайшие друг к другу порты двух карточек."""
        best = None
        for sa in ("top", "bottom", "left", "right"):
            pa = ca.port_scene_pos(sa)
            for sb in ("top", "bottom", "left", "right"):
                pb = cb.port_scene_pos(sb)
                d = (pa.x() - pb.x()) ** 2 + (pa.y() - pb.y()) ** 2
                if best is None or d < best[0]:
                    best = (d, pa, pb)
        return best[1], best[2]

    def _link_pen(self) -> QPen:
        if theme.is_minimal():
            return QPen(QColor(theme.MIN_MUTED), 2.0, Qt.SolidLine, Qt.RoundCap)
        return QPen(QColor(90, 140, 190, 200), 2.4, Qt.SolidLine, Qt.RoundCap)

    # -- отрисовка ----------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        rect = self.rect()
        if theme.is_minimal() or self._pix is None:
            p.fillRect(rect, QColor(theme.MIN_BG if theme.is_minimal() else "#E4F2FB"))
        else:
            pw, ph = self._pix.width(), self._pix.height()
            scale = max(rect.width() / pw, rect.height() / ph)
            tw, th = int(pw * scale), int(ph * scale)
            p.drawPixmap((rect.width() - tw) // 2, (rect.height() - th) // 2,
                         tw, th, self._pix)
            p.fillRect(rect, QColor(255, 255, 255, 40))

        p.setRenderHint(QPainter.Antialiasing)

        # связи
        for lk in self.links:
            ca = self.card_by_note(lk["a"])
            cb = self.card_by_note(lk["b"])
            if ca is None or cb is None:
                continue
            pa, pb = self._endpoints(ca, cb)
            p.setPen(self._link_pen())
            p.drawLine(pa, pb)
            if lk.get("arrow"):
                self._draw_arrow_head(p, pa, pb)

        # линия к курсору при незавершённой связи
        if self.pending_link is not None:
            card, side, arrow = self.pending_link
            src = card.port_scene_pos(side)
            cur = QPointF(self.mapFromGlobal(QCursor.pos()))
            pen = self._link_pen()
            pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.drawLine(src, cur)
            if arrow:
                self._draw_arrow_head(p, src, cur)
        p.end()

    def _draw_arrow_head(self, p: QPainter, a: QPointF, b: QPointF) -> None:
        import math
        ang = math.atan2(b.y() - a.y(), b.x() - a.x())
        L, W2 = 12.0, 5.5
        p1 = QPointF(b.x() - L * math.cos(ang) + W2 * math.sin(ang),
                     b.y() - L * math.sin(ang) - W2 * math.cos(ang))
        p2 = QPointF(b.x() - L * math.cos(ang) - W2 * math.sin(ang),
                     b.y() - L * math.sin(ang) + W2 * math.cos(ang))
        pen = self._link_pen()
        p.setBrush(pen.color())
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([b, p1, p2]))

    # -- мышь ------------------------------------------------------------
    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self.pending_link is not None:
            self.update()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self.pending_link is not None:
            # клик в пустоту — отмена
            self.cancel_link()
            return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        # правый клик рядом со связью — удалить её
        pos = QPointF(event.pos())
        hit = None
        for lk in self.links:
            ca = self.card_by_note(lk["a"])
            cb = self.card_by_note(lk["b"])
            if ca is None or cb is None:
                continue
            pa, pb = self._endpoints(ca, cb)
            if _dist_to_segment(pos, pa, pb) <= 8.0:
                hit = lk
                break
        if hit is not None:
            m = QMenu(self)
            win = self.window()
            if hasattr(win, "menu_qss"):
                m.setStyleSheet(win.menu_qss())
            m.addAction("Удалить связь", lambda: self._remove_link(hit))
            m.exec(event.globalPos())

    def _remove_link(self, lk: dict) -> None:
        if lk in self.links:
            self.links.remove(lk)
            self.update()
            self.changed.emit()


def _dist_to_segment(p: QPointF, a: QPointF, b: QPointF) -> float:
    ax, ay, bx, by, px, py = a.x(), a.y(), b.x(), b.y(), p.x(), p.y()
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


# ---------------------------------------------------------------------------
#  Окно песочницы
# ---------------------------------------------------------------------------

class SandboxWindow(QMainWindow):
    def __init__(self, db: Database, main_window=None):
        super().__init__(main_window)
        self.db = db
        self.main_window = main_window
        self.setWindowTitle("Песочница — связи заметок")
        self.resize(1080, 720)
        self.setMinimumSize(420, 340)
        self.setWindowFlag(Qt.Window, True)

        self.canvas = SandboxCanvas()
        self.canvas.changed.connect(self._save)

        self.scroll = QScrollArea(self)
        self.scroll.setWidget(self.canvas)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.setCentralWidget(self.scroll)

        # кнопка «+» — добавить на холст
        self.fab = BubbleButton(self, glyph="plus", size=64)
        self.fab.setToolTip("Добавить на холст")
        menu = QMenu(self.fab)
        self._fab_menu = menu
        menu.aboutToShow.connect(self._rebuild_fab_menu)
        self.fab.setMenu(menu)

        if self.main_window is not None:
            self.setStyleSheet(self.main_window.styleSheet())

        self._load()

    def menu_qss(self) -> str:
        if self.main_window is not None:
            return self.main_window._menu_qss()
        return ""

    # -- меню «+» -----------------------------------------------------------
    def _rebuild_fab_menu(self) -> None:
        m = self._fab_menu
        m.clear()
        m.setStyleSheet(self.menu_qss())
        m.addAction("✚ Новая заметка", lambda: self._create_new(TYPE_NOTE))
        m.addAction("✚ Новый список", lambda: self._create_new(TYPE_LIST))
        m.addAction("✚ Новая задача", lambda: self._create_new(TYPE_TASK))
        m.addSeparator()
        on_canvas = {c.note.id for c in self.canvas.cards}
        notes = [n for n in self.db.notes(archived=False) if n.id not in on_canvas]
        if not notes:
            act = m.addAction("Все заметки уже на холсте")
            act.setEnabled(False)
            return
        sub = m.addMenu("Из существующих")
        sub.setStyleSheet(self.menu_qss())
        for n in notes[:40]:
            emoji = TYPE_EMOJI.get(n.type, "📝")
            title = n.display_title
            if len(title) > 40:
                title = title[:40] + "…"
            sub.addAction(f"{emoji} {title}",
                          lambda _=False, nid=n.id: self._add_existing(nid))

    def _create_new(self, ntype: str) -> None:
        import random
        color = random.choice(list(C.PALETTE.keys()))
        note = self.db.create_note(ntype, color=color)
        editor = NoteEditor(self.db, note.id, self)
        editor.exec()
        fresh = self.db.note_by_id(note.id)
        if fresh is not None:
            self._place_card(fresh)
            self._save()
        self._notify_main()

    def _add_existing(self, note_id: int) -> None:
        note = self.db.note_by_id(note_id)
        if note is not None and self.canvas.card_by_note(note_id) is None:
            self._place_card(note)
            self._save()

    # -- карточки -------------------------------------------------------------
    def _place_card(self, note: Note, x: int | None = None,
                    y: int | None = None) -> SandboxCard:
        card = SandboxCard(note, self.canvas)
        if x is None or y is None:
            # видимая область скролла + смещение по числу карточек
            i = len(self.canvas.cards)
            bx = self.scroll.horizontalScrollBar().value()
            by = self.scroll.verticalScrollBar().value()
            x = bx + 60 + (i % 4) * 60
            y = by + 60 + (i % 6) * 44
        card.move(int(x), int(y))
        card.port_clicked.connect(self._on_port_clicked)
        card.clicked_while_linking.connect(self.canvas.finish_link)
        card.moved.connect(self._save)
        card.open_requested.connect(self._open_card)
        card.remove_requested.connect(self.canvas.remove_card)
        card.show()
        self.canvas.cards.append(card)
        self.canvas.update()
        return card

    def _on_port_clicked(self, card: SandboxCard, side: str) -> None:
        m = QMenu(self)
        m.setStyleSheet(self.menu_qss())
        m.addAction("→ Стрелка",
                    lambda: self.canvas.start_link(card, side, arrow=True))
        m.addAction("— Линия",
                    lambda: self.canvas.start_link(card, side, arrow=False))
        pt = card.port_scene_pos(side)
        m.exec(self.canvas.mapToGlobal(QPoint(int(pt.x()), int(pt.y()))))

    def _open_card(self, card: SandboxCard) -> None:
        editor = NoteEditor(self.db, card.note.id, self)
        editor.exec()
        fresh = self.db.note_by_id(card.note.id)
        if fresh is None:                       # заметку удалили в редакторе
            self.canvas.remove_card(card)
        else:
            card.note = fresh
            card.update()
        self._notify_main()

    def _notify_main(self) -> None:
        if self.main_window is not None:
            self.main_window.refresh()

    # -- сохранение / загрузка ----------------------------------------------
    def _save(self) -> None:
        data = {
            "items": [
                {"id": c.note.id, "x": c.x(), "y": c.y()}
                for c in self.canvas.cards
            ],
            "links": self.canvas.links,
        }
        try:
            SANDBOX_PATH.parent.mkdir(parents=True, exist_ok=True)
            SANDBOX_PATH.write_text(
                json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        except OSError:
            pass

    def _load(self) -> None:
        if not SANDBOX_PATH.exists():
            return
        try:
            data = json.loads(SANDBOX_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for item in data.get("items", []):
            note = self.db.note_by_id(item.get("id"))
            if note is not None:
                self._place_card(note, item.get("x", 60), item.get("y", 60))
        ids = {c.note.id for c in self.canvas.cards}
        self.canvas.links = [
            lk for lk in data.get("links", [])
            if lk.get("a") in ids and lk.get("b") in ids
        ]
        self.canvas.update()

    # -- размещение кнопки ------------------------------------------------
    def resizeEvent(self, event) -> None:  # noqa: N802
        self.fab.move(self.width() - self.fab.width() - 22,
                      self.height() - self.fab.height() - 22)
        self.fab.raise_()
        super().resizeEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._save()
        self._notify_main()
        super().closeEvent(event)
