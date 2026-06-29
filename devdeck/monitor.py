"""Background resource sampler.

Runs in its own QThread so psutil calls never block the UI. For each running app
it sums CPU% and RSS memory across the whole process tree and emits a dict the
resource panel renders.
"""
from __future__ import annotations

import time

import psutil
from PySide6.QtCore import QThread, Signal

from .config import REFRESH_MS
from .manager import ProcessManager


class ResourceSampler(QThread):
    # name -> {"cpu": float, "ram_mb": float, "uptime_s": float, "port": int, "pid": int}
    sampled = Signal(dict)

    def __init__(self, manager: ProcessManager, interval_ms: int = REFRESH_MS,
                 parent=None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._interval = interval_ms
        self._stop = False
        # Keep Process objects alive between samples so cpu_percent() measures
        # the delta since the previous call rather than since process start.
        self._cache: dict[int, psutil.Process] = {}

    def _proc(self, pid: int):
        p = self._cache.get(pid)
        if p is not None and p.is_running():
            return p
        try:
            p = psutil.Process(pid)
            p.cpu_percent(None)  # prime; first real reading comes next sample
        except psutil.Error:
            self._cache.pop(pid, None)
            return None
        self._cache[pid] = p
        return p

    def _sample_app(self, app) -> dict:
        cpu = 0.0
        rss = 0
        try:
            parent = psutil.Process(app.pid)
            procs = [parent] + parent.children(recursive=True)
        except psutil.Error:
            procs = []
        for sp in procs:
            pp = self._proc(sp.pid)
            if pp is None:
                continue
            try:
                cpu += pp.cpu_percent(None)
                rss += pp.memory_info().rss
            except psutil.Error:
                continue
        return {
            "cpu": cpu,
            "ram_mb": rss / (1024 * 1024),
            "uptime_s": max(0.0, time.time() - app.started_at),
            "port": app.port,
            "pid": app.pid,
        }

    def run(self) -> None:
        while not self._stop:
            data = {name: self._sample_app(app)
                    for name, app in self._manager.snapshot().items()}
            self.sampled.emit(data)
            # Sleep in small slices so stop() is responsive.
            waited = 0
            while waited < self._interval and not self._stop:
                self.msleep(100)
                waited += 100

    def stop(self) -> None:
        self._stop = True
