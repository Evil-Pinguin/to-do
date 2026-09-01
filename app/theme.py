# -*- coding: utf-8 -*-
"""Темы оформления: Aero (стекло-пузыри) и Минимализм (в духе Apple).

Выбор хранится в QSettings и применяется живьём — все painter'ы
(app/glass.py) и стили (main_window._apply_style) спрашивают текущую тему.
"""
from __future__ import annotations

from PySide6.QtCore import QSettings

AERO = "aero"
MINIMAL = "minimal"

THEME_NAMES = {
    AERO: "✦ Aero",
    MINIMAL: "◻ Минимализм",
}

_current: str | None = None


def current() -> str:
    global _current
    if _current is None:
        val = QSettings("Aero Notes", "Aero Notes").value("theme", AERO)
        _current = val if val in (AERO, MINIMAL) else AERO
    return _current


def set_current(name: str) -> None:
    global _current
    if name not in (AERO, MINIMAL):
        name = AERO
    _current = name
    QSettings("Aero Notes", "Aero Notes").setValue("theme", name)


def is_minimal() -> bool:
    return current() == MINIMAL


# Палитра минимализма (подсмотрено у Apple: San Francisco-серые + системный синий)
MIN_BG = "#F5F5F7"          # фон окна (как на apple.com)
MIN_CARD = "#FFFFFF"        # карточки
MIN_TEXT = "#1D1D1F"        # основной текст
MIN_MUTED = "#86868B"       # вторичный текст
MIN_HAIRLINE = "#D2D2D7"    # тонкие границы
MIN_ACCENT = "#0071E3"      # системный синий (кнопки)
