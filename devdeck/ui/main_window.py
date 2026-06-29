"""DevDeck main window: project list (left) + live resource panel (right)."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QMainWindow, QMessageBox,
                               QPushButton, QScrollArea, QSplitter, QVBoxLayout,
                               QWidget)

from ..config import REFRESH_MS, log_path
from ..discovery import discover_projects
from ..manager import LaunchError, ProcessManager
from ..monitor import ResourceSampler
from .project_card import ProjectCard
from .resource_panel import ResourcePanel


class _StartWorker(QThread):
    ok = Signal(str, object)    # name, RunningApp
    err = Signal(str, str)      # name, message

    def __init__(self, manager: ProcessManager, project) -> None:
        super().__init__()
        self.manager = manager
        self.project = project

    def run(self) -> None:
        try:
            app = self.manager.start(self.project)
            self.ok.emit(self.project.name, app)
        except LaunchError as e:
            self.err.emit(self.project.name, str(e))
        except Exception as e:  # noqa: BLE001
            self.err.emit(self.project.name, f"Unexpected error: {e}")


class _StopWorker(QThread):
    done = Signal(str)

    def __init__(self, manager: ProcessManager, name: str) -> None:
        super().__init__()
        self.manager = manager
        self.name = name

    def run(self) -> None:
        self.manager.stop(self.name)
        self.done.emit(self.name)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DevDeck")
        self.resize(880, 600)

        self.manager = ProcessManager()
        self.manager.reattach()

        self._cards: dict[str, ProjectCard] = {}
        self._workers: set[QThread] = set()

        # ---- layout ----
        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(10, 10, 10, 10)
        self.cards_layout.setSpacing(8)
        self.cards_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.cards_container)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self._build_toolbar())
        left_layout.addWidget(scroll, 1)

        self.resource_panel = ResourcePanel()

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.resource_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self.setCentralWidget(splitter)

        self._populate_cards()

        # ---- background sampler + liveness reconcile ----
        self.sampler = ResourceSampler(self.manager, REFRESH_MS)
        self.sampler.sampled.connect(self.resource_panel.update_data)
        self.sampler.start()

        self._reconcile_timer = QTimer(self)
        self._reconcile_timer.timeout.connect(self._reconcile)
        self._reconcile_timer.start(REFRESH_MS)

    # ---- UI construction --------------------------------------------------
    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 10, 10, 0)
        title = QLabel("Projects")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        row.addWidget(title)
        row.addStretch(1)
        rescan = QPushButton("Rescan")
        rescan.clicked.connect(self._populate_cards)
        stop_all = QPushButton("Stop all")
        stop_all.clicked.connect(self._stop_all)
        row.addWidget(rescan)
        row.addWidget(stop_all)
        return bar

    def _populate_cards(self) -> None:
        # Clear existing cards (keep the trailing stretch).
        for card in self._cards.values():
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        projects = discover_projects()
        # Recognise servers already running outside DevDeck so they show green.
        self.manager.adopt_external(projects)
        running = self.manager.snapshot()
        for project in projects:
            card = ProjectCard(project)
            card.toggled.connect(self._on_card_toggled)
            card.open_log.connect(self._open_log)
            if project.name in running:
                card.set_state("running", url=running[project.name].url)
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)
            self._cards[project.name] = card

        if not projects:
            placeholder = QLabel("No runnable web projects found.")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("color:#7f8c8d; padding:20px;")
            self.cards_layout.insertWidget(0, placeholder)

    # ---- card actions -----------------------------------------------------
    def _on_card_toggled(self, project, want_on: bool) -> None:
        card = self._cards[project.name]
        if want_on:
            card.set_state("starting")
            worker = _StartWorker(self.manager, project)
            worker.ok.connect(self._on_started)
            worker.err.connect(self._on_start_failed)
            self._run_worker(worker)
        else:
            card.set_state("stopping")
            worker = _StopWorker(self.manager, project.name)
            worker.done.connect(self._on_stopped)
            self._run_worker(worker)

    def _run_worker(self, worker: QThread) -> None:
        self._workers.add(worker)
        worker.finished.connect(lambda w=worker: self._workers.discard(w))
        worker.start()

    def _on_started(self, name: str, app) -> None:
        card = self._cards.get(name)
        if card:
            card.set_state("running", url=app.url)

    def _on_start_failed(self, name: str, message: str) -> None:
        card = self._cards.get(name)
        if card:
            card.set_state("error", message=message)

    def _on_stopped(self, name: str) -> None:
        card = self._cards.get(name)
        if card:
            card.set_state("stopped")

    def _open_log(self, project) -> None:
        path = log_path(project.name)
        if path.exists():
            os.startfile(str(path))  # noqa: S606 - intentional, user-driven
        else:
            QMessageBox.information(
                self, "No log yet",
                f"No log for {project.name} yet - start it first.")

    def _stop_all(self) -> None:
        for name in list(self.manager.snapshot()):
            card = self._cards.get(name)
            if card:
                card.set_state("stopping")
            worker = _StopWorker(self.manager, name)
            worker.done.connect(self._on_stopped)
            self._run_worker(worker)

    def _reconcile(self) -> None:
        """Reflect servers that died on their own as stopped."""
        for name in self.manager.prune():
            card = self._cards.get(name)
            if card and card.state == "running":
                card.set_state("stopped")

    # ---- shutdown ---------------------------------------------------------
    def closeEvent(self, event) -> None:
        # Leave servers running so they survive a DevDeck restart (reattach).
        self._reconcile_timer.stop()
        self.sampler.stop()
        self.sampler.wait(2000)
        for worker in list(self._workers):
            worker.wait(3000)
        super().closeEvent(event)
