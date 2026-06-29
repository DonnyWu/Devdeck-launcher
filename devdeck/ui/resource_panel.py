"""Live resource table for running apps: CPU %, RAM, uptime, port, PID."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QHeaderView, QLabel,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

_COLUMNS = ["App", "CPU %", "RAM (MB)", "Uptime", "Port", "PID"]


def _fmt_uptime(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


class ResourcePanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        title = QLabel("Resources")
        title.setStyleSheet("font-size: 15px; font-weight: 600;")
        layout.addWidget(title)

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)

        self.empty = QLabel("No apps running.")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setStyleSheet("color:#7f8c8d;")
        layout.addWidget(self.empty)

    def update_data(self, data: dict) -> None:
        self.empty.setVisible(not data)
        self.table.setVisible(bool(data))

        names = sorted(data)
        self.table.setRowCount(len(names))
        for row, name in enumerate(names):
            m = data[name]
            values = [
                name,
                f"{m['cpu']:.0f}",
                f"{m['ram_mb']:.0f}",
                _fmt_uptime(m["uptime_s"]),
                str(m["port"]),
                str(m["pid"]),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col != 0:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)
