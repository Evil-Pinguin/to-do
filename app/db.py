# -*- coding: utf-8 -*-
"""SQLite-хранилище: заметки, группы, картинки, история изменений.

Всё локально, сервер не нужен. Файл базы лежит в data/notes.db рядом
с приложением (можно переопределить через AERO_NOTES_DATA или аргумент).
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import List, Optional

from .formatting import now_str
from .models import Note, Group, dump_list, ListItem, TYPE_NOTE, TYPE_LIST, TYPE_TASK

from .paths import APP_DIR
DATA_DIR = Path(os.environ.get("AERO_NOTES_DATA") or (APP_DIR / "data"))
DEFAULT_DB_PATH = DATA_DIR / "notes.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (
    id    INTEGER PRIMARY KEY,
    name  TEXT UNIQUE NOT NULL,
    sort  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL DEFAULT '',
    type        TEXT NOT NULL DEFAULT 'note',
    color       TEXT NOT NULL DEFAULT 'yellow',
    group_id    INTEGER REFERENCES groups(id) ON DELETE SET NULL,
    pinned      INTEGER NOT NULL DEFAULT 0,
    archived    INTEGER NOT NULL DEFAULT 0,
    done        INTEGER NOT NULL DEFAULT 0,
    content     TEXT NOT NULL DEFAULT '',
    deadline    TEXT,
    priority    TEXT,
    created_at  TEXT NOT NULL,
    modified_at TEXT NOT NULL,
    edit_count  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS note_images (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id  INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    data     BLOB NOT NULL,
    added_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS history (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    ts      TEXT NOT NULL,
    event   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notes_archived ON notes(archived);
CREATE INDEX IF NOT EXISTS idx_history_note    ON history(note_id);
CREATE INDEX IF NOT EXISTS idx_images_note     ON note_images(note_id);
"""

DEFAULT_GROUPS = ["Работа", "Учёба", "Личное", "Идеи", "Покупки"]

# Тексты событий истории (ключи, которые присылает редактор)
EVENT_TEXT = {
    "created":       "создана заметка",
    "title":         "изменён заголовок",
    "text":          "изменён текст",
    "list":          "изменён список",
    "item_checked":  "отмечен пункт списка",
    "image_added":   "добавлена картинка",
    "image_removed": "удалена картинка",
    "deadline":      "изменён дедлайн",
    "priority":      "изменён приоритет",
    "task_done":     "задача отмечена выполненной",
    "task_undone":   "снята отметка выполнения",
    "color":         "изменён цвет",
    "pinned":        "заметка закреплена",
    "unpinned":      "заметка откреплена",
    "archived":      "заметка архивирована",
    "restored":      "заметка восстановлена из архива",
}


class Database:
    def __init__(self, path: Optional[os.PathLike | str] = None):
        self.path = Path(path) if path else DEFAULT_DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._seed_first_run()

    # ------------------------------------------------------------------
    # Первичный запуск
    # ------------------------------------------------------------------
    def _seed_first_run(self) -> None:
        if self.conn.execute("SELECT COUNT(*) c FROM groups").fetchone()["c"] == 0:
            for i, name in enumerate(DEFAULT_GROUPS):
                self.conn.execute("INSERT INTO groups(name, sort) VALUES(?,?)", (name, i))
            self.conn.commit()

        if self.conn.execute("SELECT COUNT(*) c FROM notes").fetchone()["c"] == 0:
            welcome = self.create_note(
                ntype=TYPE_LIST, color="yellow", group_id=self.group_id_by_name("Личное"),
                title="Добро пожаловать в Aero Notes!",
                content=dump_list([
                    ListItem("Двойной клик по карточке — редактировать", True),
                    ListItem("Нажми ⋯ в углу — меню заметки"),
                    ListItem("Включи панель «Фильтр» слева"),
                    ListItem("Закрепи список покупок 📌"),
                ]),
            )
            self.conn.execute("UPDATE notes SET pinned=1 WHERE id=?", (welcome.id,))
            self.create_note(
                ntype=TYPE_LIST, color="green", group_id=self.group_id_by_name("Покупки"),
                title="Список покупок",
                content=dump_list([
                    ListItem("Купить кофе", True),
                    ListItem("Молоко и сыр"),
                    ListItem("Что-нибудь к чаю"),
                ]),
            )
            self.create_note(
                ntype=TYPE_TASK, color="lilac", group_id=self.group_id_by_name("Работа"),
                title="Сделать портфолио", content="Собрать лучшие работы и сверстать сайт.",
                priority="high",
            )
            self.conn.commit()

    # ------------------------------------------------------------------
    # Группы
    # ------------------------------------------------------------------
    def groups(self) -> List[Group]:
        rows = self.conn.execute("SELECT id, name FROM groups ORDER BY sort, name").fetchall()
        return [Group(r["id"], r["name"]) for r in rows]

    def group_id_by_name(self, name: str) -> Optional[int]:
        row = self.conn.execute("SELECT id FROM groups WHERE name = ?", (name,)).fetchone()
        return row["id"] if row else None

    def group_name_by_id(self, gid: Optional[int]) -> Optional[str]:
        if gid is None:
            return None
        row = self.conn.execute("SELECT name FROM groups WHERE id = ?", (gid,)).fetchone()
        return row["name"] if row else None

    def add_group(self, name: str) -> Optional[Group]:
        name = name.strip()
        if not name:
            return None
        existing = self.group_id_by_name(name)
        if existing is not None:
            return Group(existing, name)
        cur = self.conn.execute(
            "INSERT INTO groups(name, sort) VALUES(?, (SELECT COALESCE(MAX(sort),0)+1 FROM groups))",
            (name,),
        )
        self.conn.commit()
        return Group(cur.lastrowid, name)

    # ------------------------------------------------------------------
    # Заметки
    # ------------------------------------------------------------------
    def _row_to_note(self, r: sqlite3.Row) -> Note:
        img = self.conn.execute(
            "SELECT COUNT(*) c FROM note_images WHERE note_id=?", (r["id"],)
        ).fetchone()["c"]
        first = None
        if img:
            row = self.conn.execute(
                "SELECT data FROM note_images WHERE note_id=? ORDER BY id LIMIT 1", (r["id"],)
            ).fetchone()
            first = bytes(row["data"]) if row else None
        return Note(
            id=r["id"], title=r["title"], type=r["type"], color=r["color"],
            group_id=r["group_id"], group_name=self.group_name_by_id(r["group_id"]),
            pinned=bool(r["pinned"]), archived=bool(r["archived"]), done=bool(r["done"]),
            content=r["content"], deadline=r["deadline"], priority=r["priority"],
            created_at=r["created_at"], modified_at=r["modified_at"],
            edit_count=r["edit_count"], image_count=img, first_image=first,
        )

    def notes(self, archived: bool = False) -> List[Note]:
        rows = self.conn.execute(
            "SELECT * FROM notes WHERE archived = ? ORDER BY pinned DESC, modified_at DESC",
            (1 if archived else 0,),
        ).fetchall()
        return [self._row_to_note(r) for r in rows]

    def note_by_id(self, note_id: int) -> Optional[Note]:
        r = self.conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        return self._row_to_note(r) if r else None

    def create_note(
        self,
        ntype: str = TYPE_NOTE,
        color: str = "yellow",
        group_id: Optional[int] = None,
        title: str = "",
        content: str = "",
        deadline: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> Note:
        ts = now_str()
        cur = self.conn.execute(
            """INSERT INTO notes(title, type, color, group_id, content,
                                 deadline, priority, created_at, modified_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (title, ntype, color, group_id, content, deadline, priority, ts, ts),
        )
        note_id = cur.lastrowid
        self.add_history(note_id, "created", ts=ts)
        self.conn.commit()
        note = self.note_by_id(note_id)
        assert note is not None
        return note

    def save_note(self, note: Note, new_events: List[str], count_edit: bool) -> None:
        """Сохранение из редактора: обновляет текст, дату изменения и, один раз
        за сессию правок, счётчик «Изменено N раз». new_events — ключи событий,
        которых ещё не было в истории за эту сессию."""
        ts = now_str()
        if count_edit:
            note.edit_count += 1
        note.modified_at = ts
        self.conn.execute(
            """UPDATE notes SET title=?, content=?, deadline=?, priority=?, done=?,
                                modified_at=?, edit_count=? WHERE id=?""",
            (note.title, note.content, note.deadline, note.priority,
             1 if note.done else 0, ts, note.edit_count, note.id),
        )
        for key in new_events:
            self.add_history(note.id, key, ts=ts)
        self.conn.commit()

    # ------- быстрые действия из меню ⋯ (меняют метаданные, не трогая  -------
    # ------- «дату изменения» и счётчик правок — это не редактирование) -------

    def set_color(self, note_id: int, color: str) -> None:
        self.conn.execute("UPDATE notes SET color=? WHERE id=?", (color, note_id))
        self.add_history(note_id, "color")
        self.conn.commit()

    def set_pinned(self, note_id: int, pinned: bool) -> None:
        self.conn.execute("UPDATE notes SET pinned=? WHERE id=?", (1 if pinned else 0, note_id))
        self.add_history(note_id, "pinned" if pinned else "unpinned")
        self.conn.commit()

    def move_to_group(self, note_id: int, group_id: Optional[int]) -> None:
        self.conn.execute("UPDATE notes SET group_id=? WHERE id=?", (group_id, note_id))
        name = self.group_name_by_id(group_id)
        self.add_history(note_id, f"__group__:{name or 'без группы'}")
        self.conn.commit()

    def set_archived(self, note_id: int, archived: bool) -> None:
        self.conn.execute(
            "UPDATE notes SET archived=? WHERE id=?", (1 if archived else 0, note_id)
        )
        self.add_history(note_id, "archived" if archived else "restored")
        self.conn.commit()

    def duplicate(self, note_id: int) -> Optional[int]:
        src = self.note_by_id(note_id)
        if not src:
            return None
        ts = now_str()
        title = src.title
        cur = self.conn.execute(
            """INSERT INTO notes(title, type, color, group_id, pinned, done, content,
                                 deadline, priority, created_at, modified_at, edit_count)
               VALUES(?,?,?,?,0,?,?,?,?,?,?,0)""",
            (title, src.type, src.color, src.group_id, src.done, src.content,
             src.deadline, src.priority, ts, ts),
        )
        new_id = cur.lastrowid
        for row in self.conn.execute(
            "SELECT data FROM note_images WHERE note_id=?", (note_id,)
        ).fetchall():
            self.conn.execute(
                "INSERT INTO note_images(note_id, data, added_at) VALUES(?,?,?)",
                (new_id, row["data"], ts),
            )
        self.add_history(new_id, f"__copy__:{title or 'без названия'}", ts=ts)
        self.conn.commit()
        return new_id

    def delete_note(self, note_id: int) -> None:
        self.conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
        self.conn.commit()

    # ------------------------------------------------------------------
    # Картинки
    # ------------------------------------------------------------------
    def images(self, note_id: int) -> List[sqlite3.Row]:
        return self.conn.execute(
            "SELECT id, data, added_at FROM note_images WHERE note_id=? ORDER BY id",
            (note_id,),
        ).fetchall()

    def add_image(self, note_id: int, blob: bytes) -> int:
        cur = self.conn.execute(
            "INSERT INTO note_images(note_id, data, added_at) VALUES(?,?,?)",
            (note_id, blob, now_str()),
        )
        self.conn.commit()
        return cur.lastrowid

    def delete_image(self, image_id: int) -> None:
        self.conn.execute("DELETE FROM note_images WHERE id=?", (image_id,))
        self.conn.commit()

    # ------------------------------------------------------------------
    # История
    # ------------------------------------------------------------------
    def add_history(self, note_id: int, event: str, ts: Optional[str] = None) -> None:
        if event.startswith("__group__:"):
            text = f"перемещена в группу «{event.split(':', 1)[1]}»"
        elif event.startswith("__copy__:"):
            text = "создана копия заметки"
        else:
            text = EVENT_TEXT.get(event, event)
        self.conn.execute(
            "INSERT INTO history(note_id, ts, event) VALUES(?,?,?)",
            (note_id, ts or now_str(), text),
        )

    def history(self, note_id: int) -> List[sqlite3.Row]:
        return self.conn.execute(
            "SELECT ts, event FROM history WHERE note_id=? ORDER BY id", (note_id,)
        ).fetchall()

    def close(self) -> None:
        self.conn.close()
