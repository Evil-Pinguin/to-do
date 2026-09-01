# -*- coding: utf-8 -*-
"""Пути к ресурсам и данным: работает и из исходников, и из PyInstaller --onefile."""
from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


if is_frozen():
    # exe-сборка: данные рядом с exe, ресурсы во временной распаковке
    APP_DIR = Path(sys.executable).resolve().parent
    ASSETS_DIR = Path(sys._MEIPASS) / "assets"  # type: ignore[attr-defined]
else:
    APP_DIR = Path(__file__).resolve().parent.parent
    ASSETS_DIR = APP_DIR / "assets"
