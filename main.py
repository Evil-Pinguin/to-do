# -*- coding: utf-8 -*-
"""Aero Notes — локальные заметки и задачи в духе Frutiger Aero.

Запуск:  python main.py          (база создастся в data/notes.db)
         python main.py --db ПУТЬ
"""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon, QPixmap, QColor, QPainter
from PySide6.QtWidgets import QApplication

from app.db import Database, DEFAULT_DB_PATH
from app.main_window import MainWindow


def _app_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#FFE082"))
    p.setPen(QColor(120, 140, 170, 200))
    p.drawRoundedRect(6, 6, 52, 52, 14, 14)
    p.setPen(QColor("#5A7188"))
    font = QFont("Segoe UI")
    font.setPixelSize(34)
    font.setBold(True)
    p.setFont(font)
    p.drawText(pm.rect(), Qt.AlignCenter, "✓")
    p.end()
    return QIcon(pm)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Aero Notes")
    app.setOrganizationName("Aero Notes")
    app.setStyle("Fusion")

    font = QFont("Segoe UI", 10)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)
    app.setWindowIcon(_app_icon())

    db_path = DEFAULT_DB_PATH
    if "--db" in sys.argv:
        i = sys.argv.index("--db")
        if i + 1 < len(sys.argv):
            db_path = sys.argv[i + 1]

    db = Database(db_path)
    win = MainWindow(db)
    win.show()
    rc = app.exec()
    db.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
