# -*- coding: utf-8 -*-
"""Ambient — окружение Liquid Glass, зависящее от времени суток.

Меняется только «среда» (фон, свечения, рефлексы стекла) —
пользовательские заметки остаются как есть.

    Утро   06–11  бело-голубое стекло, тёплые солнечные блики
    День   11–17  cyan / sky blue
    Вечер  17–22  lavender / peach
    Ночь   22–06  глубокое сине-фиолетовое стекло
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

MORNING, DAY, EVENING, NIGHT = "morning", "day", "evening", "night"

_override: Optional[str] = None   # для тестов/скриншотов


def set_override(period: Optional[str]) -> None:
    global _override
    _override = period


def period(now: Optional[datetime] = None) -> str:
    if _override is not None:
        return _override
    h = (now or datetime.now()).hour
    if 6 <= h < 11:
        return MORNING
    if 11 <= h < 17:
        return DAY
    if 17 <= h < 22:
        return EVENING
    return NIGHT


# Каждая палитра:
#   sky        — вертикальный градиент фона (top, bottom)
#   blobs      — большие размытые световые пятна: (r,g,b,a, cx,cy, radius)
#                cx, cy, radius — доли от ширины/высоты окна
#   reflex     — цвет нижнего рефлекса стекла (rgb)
#   haze_boost — добавка белой дымки на карточках (читаемость ночью)
#   veil       — белая вуаль поверх фона (alpha)
PALETTES = {
    MORNING: dict(
        sky=("#EAF6FD", "#F4FBF2"),
        blobs=[
            (255, 250, 225, 130, 0.06, 0.02, 0.55),   # тёплое солнце слева-сверху
            (205, 240, 250, 95, 0.88, 0.22, 0.48),    # cyan справа
            (255, 255, 255, 80, 0.50, 0.52, 0.60),    # белое свечение в центре
            (231, 226, 250, 55, 0.22, 0.96, 0.50),    # лаванда снизу
        ],
        reflex=(196, 232, 222),
        haze_boost=0,
        veil=26,
    ),
    DAY: dict(
        sky=("#DDF1FB", "#EDFBF8"),
        blobs=[
            (255, 255, 245, 110, 0.10, 0.04, 0.50),
            (185, 235, 250, 120, 0.86, 0.28, 0.55),   # выраженный cyan
            (255, 255, 255, 85, 0.48, 0.55, 0.62),
            (205, 235, 250, 60, 0.30, 0.95, 0.52),
        ],
        reflex=(184, 230, 228),
        haze_boost=0,
        veil=22,
    ),
    EVENING: dict(
        sky=("#ECE9F8", "#FBEFE6"),
        blobs=[
            (255, 226, 202, 120, 0.10, 0.06, 0.52),   # персиковое солнце
            (219, 208, 248, 105, 0.86, 0.24, 0.52),   # лаванда справа
            (255, 244, 235, 85, 0.50, 0.58, 0.60),
            (235, 214, 235, 65, 0.24, 0.96, 0.50),
        ],
        reflex=(228, 212, 222),
        haze_boost=14,
        veil=18,
    ),
    NIGHT: dict(
        sky=("#454F74", "#333D5E"),
        blobs=[
            (140, 160, 235, 70, 0.10, 0.05, 0.55),    # синее свечение
            (165, 140, 225, 60, 0.86, 0.25, 0.52),    # фиолет справа
            (200, 210, 250, 45, 0.50, 0.55, 0.62),
            (120, 150, 220, 45, 0.25, 0.95, 0.50),
        ],
        reflex=(150, 168, 216),
        haze_boost=72,
        veil=0,
    ),
}


def palette() -> dict:
    return PALETTES[period()]
