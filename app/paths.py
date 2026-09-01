# -*- coding: utf-8 -*-
import sys
from pathlib import Path

def is_frozen() -> bool:
    return getattr(sys, "frozen", False)

if is_frozen():                      # собранный exe
    APP_DIR = Path(sys.executable).resolve().parent
else:                                # запуск из исходников
    APP_DIR = Path(__file__).resolve().parent.parent

if is_frozen():
    ASSETS_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR)).resolve() / "assets"
else:
    ASSETS_DIR = APP_DIR / "assets"