# -*- coding: utf-8 -*-
"""Пастельная палитра карточек в духе Frutiger Aero."""
from __future__ import annotations

def _rgb(hexstr: str) -> tuple[int, int, int]:
    h = hexstr.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


# key -> (человеческое имя, базовый цвет)
PALETTE: dict[str, tuple[str, str]] = {
    "yellow": ("Жёлтый",  "#FFE082"),
    "pink":   ("Розовый", "#F8BBD0"),
    "blue":   ("Голубой", "#90CAF9"),
    "green":  ("Зелёный", "#A5D6A7"),
    "lilac":  ("Сиреневый", "#CE93D8"),
    "gray":   ("Серый",   "#BDBDBD"),
    "orange": ("Оранжевый", "#FFCC80"),
    "mint":   ("Мятный",  "#80CBC4"),
}

DEFAULT_COLOR = "yellow"
PALETTE_ORDER = list(PALETTE.keys())


def color_name(key: str) -> str:
    return PALETTE.get(key, PALETTE[DEFAULT_COLOR])[0]


def base_rgb(key: str) -> tuple[int, int, int]:
    return _rgb(PALETTE.get(key, PALETTE[DEFAULT_COLOR])[1])


def rgba(key: str, alpha: int = 230) -> str:
    r, g, b = base_rgb(key)
    return f"rgba({r},{g},{b},{alpha})"


def border_rgba(key: str, alpha: int = 190) -> str:
    """Более тёмная рамка того же оттенка."""
    r, g, b = base_rgb(key)
    k = 0.72
    r, g, b = int(r * k), int(g * k), int(b * k)
    return f"rgba({r},{g},{b},{alpha})"


def color_index(key: str) -> int:
    try:
        return PALETTE_ORDER.index(key)
    except ValueError:
        return len(PALETTE_ORDER)


# Приоритеты задач
PRIORITY_COLORS = {
    "high":   ("Высокий", "#E57373"),
    "medium": ("Средний", "#FFB74D"),
    "low":    ("Низкий",  "#90A4AE"),
}

# Общий тёмно-синий текст на пастельных карточках
TEXT_DARK = "#23405E"
TEXT_MUTED = "#5A7188"
