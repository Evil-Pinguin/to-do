# -*- coding: utf-8 -*-
"""Модели данных Aero Notes."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional, List

# Типы заметок
TYPE_NOTE = "note"    # обычная заметка: заголовок + текст + картинки
TYPE_LIST = "list"    # список с чекбоксами
TYPE_TASK = "task"    # задача: дедлайн + приоритет

TYPE_NAMES = {
    TYPE_NOTE: "Заметка",
    TYPE_LIST: "Список",
    TYPE_TASK: "Задача",
}

PRIORITIES = ["high", "medium", "low"]
PRIORITY_NAMES = {"high": "Высокий", "medium": "Средний", "low": "Низкий"}


@dataclass
class Group:
    id: int
    name: str


@dataclass
class ListItem:
    text: str = ""
    done: bool = False

    def to_dict(self) -> dict:
        return {"t": self.text, "d": self.done}


def dump_list(items: List[ListItem]) -> str:
    return json.dumps([i.to_dict() for i in items], ensure_ascii=False)


def parse_list(content: str) -> List[ListItem]:
    try:
        raw = json.loads(content or "[]")
        if not isinstance(raw, list):
            return []
        return [ListItem(str(it.get("t", "")), bool(it.get("d", False))) for it in raw]
    except (ValueError, TypeError, AttributeError):
        return []


@dataclass
class Note:
    id: int
    title: str
    type: str
    color: str
    group_id: Optional[int]
    group_name: Optional[str]
    pinned: bool
    archived: bool
    done: bool
    content: str
    deadline: Optional[str]
    priority: Optional[str]
    created_at: str
    modified_at: str
    edit_count: int
    image_count: int = 0
    first_image: Optional[bytes] = None  # маленькая превьюшка для карточки

    # ---------- удобные аксессоры ----------

    @property
    def type_name(self) -> str:
        return TYPE_NAMES.get(self.type, self.type)

    @property
    def display_title(self) -> str:
        return self.title.strip() or "Без названия"

    def list_items(self) -> List[ListItem]:
        if self.type == TYPE_LIST:
            return parse_list(self.content)
        return []

    def plain_text(self) -> str:
        """Текст для поиска: заголовок + всё содержимое."""
        parts = [self.title]
        if self.type == TYPE_LIST:
            parts.extend(i.text for i in self.list_items())
        else:
            parts.append(self.content)
        return "\n".join(p for p in parts if p).lower()

    def is_done(self) -> bool:
        """Статус 'выполнено': задача отмечена или все пункты списка закрыты."""
        if self.type == TYPE_TASK:
            return bool(self.done)
        if self.type == TYPE_LIST:
            items = self.list_items()
            return bool(items) and all(i.done for i in items)
        return False

    def is_overdue(self) -> bool:
        from .formatting import parse_ts, now_dt
        if self.type != TYPE_TASK or self.done or not self.deadline:
            return False
        dl = parse_ts(self.deadline)
        return dl is not None and dl < now_dt()
