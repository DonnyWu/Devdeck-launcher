"""One project row: status light, name, type badge, on/off toggle, URL, Log."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QAbstractButton, QFrame, QHBoxLayout, QLabel,
                               QSizePolicy, QToolButton, QVBoxLayout, QWidget)

# state -> light colour
_LIGHT_COLORS = {
    "stopped": "#c0392b",   # red
    "error": "#c0392b",     # red
    "starting": "#f39c12",  # amber
    "stopping": "#f39c12",  # amber
    "running": "#27ae60",   # green
}


class StatusLight(QWidget):
    """A small glowing circle whose colour reflects the app state."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._color = QColor(_LIGHT_COLORS["stopped"])
        self.setFixedSize(18, 18)

    def set_color(self, hex_color: str) -> None:
        self._color = QColor(hex_color)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        glow = QColor(self._color)
        glow.setAlpha(70)
        p.setBrush(glow)
        p.drawEllipse(self.rect())
        p.setBrush(self._color)
        p.drawEllipse(QRectF(3, 3, 12, 12))


class ToggleSwitch(QAbstractButton):
    """A checkable on/off switch (green when on, grey when off)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(52, 28)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        enabled = self.isEnabled()
        track = QColor("#27ae60") if on else QColor("#7f8c8d")
        if not enabled:
            track.setAlpha(120)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        r = self.rect().adjusted(1, 1, -1, -1)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        # knob
        d = r.height() - 6
        x = r.right() - d - 3 if on else r.left() + 3
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(x, r.top() + 3, d, d))


class ProjectCard(QFrame):
    toggled = Signal(object, bool)   # (project, want_on)
    open_log = Signal(object)        # (project)

    def __init__(self, project, parent=None) -> None:
        super().__init__(parent)
        self.project = project
        self.state = "stopped"
        self.setObjectName("projectCard")
        self.setFrameShape(QFrame.StyledPanel)

        self.light = StatusLight()

        name = QLabel(project.name)
        name.setStyleSheet("font-size: 14px; font-weight: 600;")

        badge = QLabel(project.type_label)
        badge.setStyleSheet(
            "background:#34495e; color:#ecf0f1; border-radius:7px;"
            " padding:1px 8px; font-size:11px;")
        badge.setAlignment(Qt.AlignCenter)
        badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)

        self.info = QLabel("")
        self.info.setOpenExternalLinks(True)
        self.info.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.info.setStyleSheet("color:#7f8c8d; font-size:12px;")

        self.toggle = ToggleSwitch()
        self.toggle.clicked.connect(self._on_clicked)

        self.log_btn = QToolButton()
        self.log_btn.setText("Log")
        self.log_btn.setToolTip("Open this project's log file")
        self.log_btn.clicked.connect(lambda: self.open_log.emit(self.project))

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        top_row.addWidget(name)
        top_row.addWidget(badge)
        top_row.addStretch(1)
        text_col.addLayout(top_row)
        text_col.addWidget(self.info)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)
        layout.addWidget(self.light, 0, Qt.AlignVCenter)
        layout.addLayout(text_col, 1)
        layout.addWidget(self.log_btn, 0, Qt.AlignVCenter)
        layout.addWidget(self.toggle, 0, Qt.AlignVCenter)

        self.set_state("stopped")

    def _on_clicked(self) -> None:
        # Qt has already flipped isChecked() by the time clicked fires.
        self.toggled.emit(self.project, self.toggle.isChecked())

    def _set_checked(self, value: bool) -> None:
        self.toggle.blockSignals(True)
        self.toggle.setChecked(value)
        self.toggle.blockSignals(False)
        self.toggle.update()

    def set_state(self, state: str, url: str | None = None,
                  message: str | None = None) -> None:
        self.state = state
        self.light.set_color(_LIGHT_COLORS.get(state, "#c0392b"))

        if state == "running":
            self._set_checked(True)
            self.toggle.setEnabled(True)
            self.info.setText(f'<a href="{url}">{url}</a>')
            self.setToolTip("")
        elif state == "starting":
            self._set_checked(True)
            self.toggle.setEnabled(False)
            self.info.setText("starting…")
            self.setToolTip("")
        elif state == "stopping":
            self._set_checked(False)
            self.toggle.setEnabled(False)
            self.info.setText("stopping…")
            self.setToolTip("")
        elif state == "error":
            self._set_checked(False)
            self.toggle.setEnabled(True)
            self.info.setText("error – click Log for details")
            self.setToolTip(message or "Launch failed")
        else:  # stopped
            self._set_checked(False)
            self.toggle.setEnabled(True)
            self.info.setText("")
            self.setToolTip("")
