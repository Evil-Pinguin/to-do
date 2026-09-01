# -*- coding: utf-8 -*-
"""Форматирование дат и вспомогательные штуки."""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional

MONTHS_GEN = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
              "июля", "августа", "сентября", "октября", "ноября", "декабря"]
WEEKDAYS_FULL = ["понедельник", "вторник", "среда", "четверг",
                 "пятница", "суббота", "воскресенье"]

TS_FORMAT = "%Y-%m-%d %H:%M:%S"


def now_dt() -> datetime:
    return datetime.now()


def now_str() -> str:
    return datetime.now().strftime(TS_FORMAT)


def parse_ts(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.strptime(s, TS_FORMAT)
    except ValueError:
        return None


def fmt_dt(s: Optional[str]) -> str:
    """31.08.2026, 20:14 — для «Сведений»."""
    dt = parse_ts(s)
    if not dt:
        return "—"
    return dt.strftime("%d.%m.%Y, %H:%M")


def fmt_deadline(s: Optional[str]) -> str:
    """5 сентября, 18:00 (год добавляется, если не текущий)."""
    dt = parse_ts(s)
    if not dt:
        return "—"
    today = date.today()
    if dt.year != today.year:
        return f"{dt.day} {MONTHS_GEN[dt.month]} {dt.year}, {dt.strftime('%H:%M')}"
    return f"{dt.day} {MONTHS_GEN[dt.month]}, {dt.strftime('%H:%M')}"


def fmt_history_ts(s: str) -> str:
    """Время для списка истории: 20:14 сегодня, иначе 31.08, 20:14."""
    dt = parse_ts(s)
    if not dt:
        return s
    today = date.today()
    if dt.date() == today:
        return dt.strftime("%H:%M")
    return dt.strftime("%d.%m, %H:%M")


def fmt_short(s: Optional[str]) -> str:
    """Короткая метка времени на карточке: сегодня 23:37 / вчера 09:12 / 31.08, 23:37."""
    dt = parse_ts(s)
    if not dt:
        return ""
    today = date.today()
    d = dt.date()
    if d == today:
        return dt.strftime("сегодня %H:%M")
    if (today - d).days == 1:
        return dt.strftime("вчера %H:%M")
    if dt.year != today.year:
        return dt.strftime("%d.%m.%Y, %H:%M")
    return dt.strftime("%d.%m, %H:%M")


def fmt_clock(dt: datetime) -> str:
    """Суббота, 01.09.2026 — 14:03:27 (для часов в углу)."""
    wd = WEEKDAYS_FULL[dt.weekday()].capitalize()
    return f"{wd}, {dt.strftime('%d.%m.%Y')}  ·  {dt.strftime('%H:%M:%S')}"


def plural(n: int, one: str, few: str, many: str) -> str:
    """Русская плюрализация: 1 раз / 2 раза / 5 раз / 21 раз."""
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many
