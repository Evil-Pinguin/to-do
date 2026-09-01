# -*- coding: utf-8 -*-
"""Темы оформления: Aero (стекло-пузыри) и Минимализм (в духе Apple).

Выбор хранится в QSettings и применяется живьём — все painter'ы
(app/glass.py) и стили (main_window._apply_style) спрашивают текущую тему.
"""
from __future__ import annotations

from PySide6.QtCore import QSettings

AERO = "aero"
FROSTED = "frosted"
MINIMAL = "minimal"

THEME_NAMES = {
    AERO: "✦ Aero",
    FROSTED: "❄ Жидкое стекло",
    MINIMAL: "◻ Минимализм",
}

_current: str | None = None


def current() -> str:
    global _current
    if _current is None:
        val = QSettings("Aero Notes", "Aero Notes").value("theme", AERO)
        _current = val if val in THEME_NAMES else AERO
    return _current


def set_current(name: str) -> None:
    global _current
    if name not in THEME_NAMES:
        name = AERO
    _current = name
    QSettings("Aero Notes", "Aero Notes").setValue("theme", name)


def is_minimal() -> bool:
    return current() == MINIMAL


def is_frosted() -> bool:
    return current() == FROSTED


# --- цвета текста, зависящие от темы -------------------------------------

def text_primary() -> str:
    if is_frosted():
        return "#FFFFFF"
    if is_minimal():
        return MIN_TEXT
    return "#23405E"


def text_muted() -> str:
    if is_frosted():
        return "rgba(255,255,255,166)"
    if is_minimal():
        return MIN_MUTED
    return "#5A7188"


def chip_style() -> str:
    """Стеклянный бейдж (тип заметки, группа) под текущую тему."""
    if is_frosted():
        return (
            "color: #FFFFFF; background: rgba(255,255,255,45);"
            "border: 1px solid rgba(255,255,255,70);"
        )
    if is_minimal():
        return (
            f"color: {MIN_TEXT}; background: #FFFFFF;"
            f"border: 1px solid {MIN_HAIRLINE};"
        )
    return (
        "color: #23405E; background: rgba(255,255,255,130);"
        "border: 1px solid rgba(255,255,255,180);"
    )


# Палитра Frosted (глубокое стекло: синий #1E3A8A → фиолет #7C3AED)
FR_BG_TOP = "#243B77"
FR_BG_BOTTOM = "#5B2FA8"
FR_ACCENT = "#3B82F6"
FR_PINK = "#EC4899"


# Палитра минимализма (подсмотрено у Apple: San Francisco-серые + системный синий)
MIN_BG = "#F5F5F7"          # фон окна (как на apple.com)
MIN_CARD = "#FFFFFF"        # карточки
MIN_TEXT = "#1D1D1F"        # основной текст
MIN_MUTED = "#86868B"       # вторичный текст
MIN_HAIRLINE = "#D2D2D7"    # тонкие границы
MIN_ACCENT = "#0071E3"      # системный синий (кнопки)
