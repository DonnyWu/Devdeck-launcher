"""Launch, monitor-by-pid and tear down project servers.

Each project is started as a background subprocess (its stdout/stderr captured to
a per-project log). Stopping kills the *entire* process tree via psutil, which is
what actually frees the port. A small state.json lets DevDeck reattach to servers
that are still alive from a previous session instead of orphaning them.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import psutil

from .config import (DEFAULT_STARTUP_TIMEOUT, STARTUP_TIMEOUTS, STATE_FILE,
                     log_path)
from .discovery import Project
from .ports import find_free_port, is_port_listening

# Detach the child from our Ctrl-C/console group so it has its own process group.
CREATE_NEW_PROCESS_GROUP = 0x00000200


class LaunchError(Exception):
    """Raised when a server fails to come up (exited early or timed out)."""


@dataclass
class RunningApp:
    name: str
    pid: int
    port: int
    url: str
    started_at: float
    log_file: str
    ptype: str = ""


def _tail(path: str | Path, n: int = 40) -> str:
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-n:]).strip()


def _python_for(root: Path) -> str:
    """Prefer the project's own venv interpreter; never use sys.executable
    (that is DevDeck.exe once frozen). Fall back to a system python."""
    venv_py = root / ".venv" / "Scripts" / "python.exe"
    if venv_py.exists():
        return str(venv_py)
    return shutil.which("python") or shutil.which("py") or "python"


class ProcessManager:
    def __init__(self) -> None:
        self._running: dict[str, RunningApp] = {}
        self._procs: dict[str, subprocess.Popen] = {}
        self._logs: dict[str, object] = {}
        self._lock = threading.Lock()

    # ---- launch command per project type (mirrors /Localhost) -------------
    def _build_command(self, project: Project, port: int):
        t = project.type
        root = project.root
        env = None  # inherit parent env unless we need to add to it
        extra_env: dict[str, str] = {}
        run_cwd = str(root)

        if t == "streamlit":
            cmd = [_python_for(root), "-m", "streamlit", "run", "app.py",
                   "--server.port", str(port), "--server.headless", "true"]
        elif t == "gradio":
            cmd = [_python_for(root), "app.py"]
            extra_env = {"GRADIO_SERVER_PORT": str(port),
                         "GRADIO_SERVER_NAME": "127.0.0.1"}
        elif t == "vite":
            cmd = ["cmd", "/c", "npm", "run", project.npm_script or "dev",
                   "--", "--port", str(port)]
        elif t == "react":
            cmd = ["cmd", "/c", "npm", "run", project.npm_script or "start"]
            # CRA reads PORT; BROWSER=none stops it auto-opening a browser.
            extra_env = {"PORT": str(port), "BROWSER": "none"}
        elif t == "dotnet":
            cmd = ["dotnet", "run", "--project", str(project.csproj),
                   "--urls", f"http://localhost:{port}"]
        elif t == "static":
            py = shutil.which("python") or shutil.which("py") or "python"
            cmd = [py, "-m", "http.server", str(port)]
        else:
            raise LaunchError(f"Don't know how to launch type '{t}'.")

        if extra_env:
            env = os.environ.copy()
            env.update(extra_env)
        return cmd, env, run_cwd

    # ---- start ------------------------------------------------------------
    def start(self, project: Project) -> RunningApp:
        """Launch the server and block until it listens (or fail). Call off the
        UI thread - it can take many seconds."""
        with self._lock:
            if project.name in self._running:
                return self._running[project.name]

        port = find_free_port(project.conventional_port)
        cmd, env, run_cwd = self._build_command(project, port)
        log_file = log_path(project.name)
        log_f = open(log_file, "w", encoding="utf-8", errors="ignore")
        log_f.write(f"$ {' '.join(cmd)}\n(cwd: {run_cwd})\n\n")
        log_f.flush()

        try:
            proc = subprocess.Popen(
                cmd, cwd=run_cwd, env=env,
                stdout=log_f, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=CREATE_NEW_PROCESS_GROUP,
            )
        except Exception as e:  # noqa: BLE001 - surface any spawn failure
            log_f.close()
            raise LaunchError(f"Could not launch: {e}")

        timeout = STARTUP_TIMEOUTS.get(project.type, DEFAULT_STARTUP_TIMEOUT)
        deadline = time.time() + timeout
        actual_port = None
        while time.time() < deadline:
            if proc.poll() is not None:
                log_f.flush()
                raise LaunchError(
                    f"Process exited early (code {proc.returncode}).\n\n"
                    f"{_tail(log_file)}")
            # Trust the port the server ACTUALLY bound, not the one we asked for.
            # Dev servers (Streamlit, Vite, ...) silently pick a different port
            # if ours was taken in a race - reporting the requested port would
            # then point the URL at whatever else holds it.
            actual_port = self._tree_listen_port(proc.pid)
            if actual_port is None and is_port_listening(port):
                actual_port = port  # fallback if per-process inspection is blocked
            if actual_port:
                break
            time.sleep(0.4)

        if not actual_port:
            # Timed out: kill what we spawned so we don't leak a half-bound port.
            self._kill_tree(proc.pid)
            log_f.close()
            raise LaunchError(
                f"Timed out after {timeout}s waiting for the server to listen.\n\n"
                f"{_tail(log_file)}")

        app = RunningApp(
            name=project.name, pid=proc.pid, port=actual_port,
            url=f"http://localhost:{actual_port}", started_at=time.time(),
            log_file=str(log_file), ptype=project.type)
        with self._lock:
            self._running[project.name] = app
            self._procs[project.name] = proc
            self._logs[project.name] = log_f
        self._save_state()
        return app

    def _tree_listen_port(self, root_pid: int) -> Optional[int]:
        """The TCP port a process tree is actually listening on (or None)."""
        try:
            root = psutil.Process(root_pid)
            procs = [root] + root.children(recursive=True)
        except psutil.Error:
            return None
        for p in procs:
            try:
                conns = p.net_connections(kind="inet")
            except psutil.Error:
                continue
            for c in conns:
                if c.status == psutil.CONN_LISTEN and c.laddr:
                    return c.laddr.port
        return None

    # ---- stop -------------------------------------------------------------
    def _kill_tree(self, pid: int) -> None:
        try:
            parent = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return
        procs = parent.children(recursive=True)
        procs.append(parent)
        for p in procs:
            try:
                p.terminate()
            except psutil.Error:
                pass
        _, alive = psutil.wait_procs(procs, timeout=5)
        for p in alive:
            try:
                p.kill()
            except psutil.Error:
                pass
        psutil.wait_procs(alive, timeout=3)

    def stop(self, name: str) -> None:
        with self._lock:
            app = self._running.get(name)
        if app is None:
            return
        self._kill_tree(app.pid)
        with self._lock:
            self._running.pop(name, None)
            self._procs.pop(name, None)
            lf = self._logs.pop(name, None)
        if lf is not None:
            try:
                lf.close()
            except Exception:  # noqa: BLE001
                pass
        self._save_state()

    def stop_all(self) -> None:
        for name in list(self.snapshot()):
            self.stop(name)

    # ---- queries ----------------------------------------------------------
    def snapshot(self) -> dict[str, RunningApp]:
        with self._lock:
            return dict(self._running)

    def is_running(self, name: str) -> bool:
        with self._lock:
            app = self._running.get(name)
        return bool(app) and psutil.pid_exists(app.pid)

    def prune(self) -> list[str]:
        """Drop apps whose process has died externally. Returns their names."""
        removed = []
        for name, app in list(self.snapshot().items()):
            if not psutil.pid_exists(app.pid):
                removed.append(name)
                with self._lock:
                    self._running.pop(name, None)
                    self._procs.pop(name, None)
                    lf = self._logs.pop(name, None)
                if lf is not None:
                    try:
                        lf.close()
                    except Exception:  # noqa: BLE001
                        pass
        if removed:
            self._save_state()
        return removed

    # ---- persistence / reattach ------------------------------------------
    def _save_state(self) -> None:
        try:
            data = {name: asdict(app) for name, app in self.snapshot().items()}
            STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _load_state(self) -> dict:
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def reattach(self) -> None:
        """Re-adopt servers from a previous session that are still alive."""
        for name, info in self._load_state().items():
            pid = info.get("pid")
            port = info.get("port")
            try:
                alive = pid and psutil.pid_exists(pid) and is_port_listening(port)
            except psutil.Error:
                alive = False
            if alive:
                with self._lock:
                    self._running[name] = RunningApp(
                        name=name, pid=pid, port=port,
                        url=info.get("url", f"http://localhost:{port}"),
                        started_at=info.get("started_at", time.time()),
                        log_file=info.get("log_file", str(log_path(name))),
                        ptype=info.get("ptype", ""))
        self._save_state()

    # ---- adopt servers started outside DevDeck ---------------------------
    @staticmethod
    def _listeners_by_cwd() -> dict[str, tuple[int, int]]:
        """Map normalised working-dir -> (listener_pid, port) for every process
        currently in LISTEN state. Lets us recognise servers DevDeck didn't
        start (e.g. launched from a terminal or via /Localhost)."""
        servers: dict[str, tuple[int, int]] = {}
        try:
            conns = psutil.net_connections(kind="inet")
        except psutil.Error:
            return servers
        for c in conns:
            if c.status != psutil.CONN_LISTEN or not c.laddr or not c.pid:
                continue
            try:
                cwd = psutil.Process(c.pid).cwd()
            except psutil.Error:
                continue
            key = cwd.lower()
            # keep the lowest port if several listeners share a working dir
            if key not in servers or c.laddr.port < servers[key][1]:
                servers[key] = (c.pid, c.laddr.port)
        return servers

    @staticmethod
    def _server_owner(listener_pid: int, root_lower: str) -> tuple[int, float]:
        """Walk up from a listener through server processes (python/node/dotnet)
        rooted in the project dir, to the topmost one - so stopping it tears down
        the whole tree. Never climbs into a shell (won't kill a user's terminal).
        Returns (pid, create_time)."""
        servery = ("python", "node", "dotnet")
        try:
            best = psutil.Process(listener_pid)
        except psutil.Error:
            return listener_pid, time.time()
        try:
            for anc in best.parents():
                try:
                    name = anc.name().lower()
                    same_root = anc.cwd().lower() == root_lower
                except psutil.Error:
                    break
                if same_root and any(name.startswith(s) for s in servery):
                    best = anc
                    continue
                break
        except psutil.Error:
            pass
        try:
            created = best.create_time()
        except psutil.Error:
            created = time.time()
        return best.pid, created

    def adopt_external(self, projects) -> list[str]:
        """Mark already-running servers as running by matching a project's root
        folder to a listening process's working dir. Returns adopted names."""
        servers = self._listeners_by_cwd()
        adopted = []
        for proj in projects:
            with self._lock:
                if proj.name in self._running:
                    continue
            root_l = str(proj.root).lower()
            hit = None
            for cwd_l, (pid, port) in servers.items():
                if cwd_l == root_l or cwd_l.startswith(root_l + os.sep):
                    hit = (pid, port)
                    break
            if not hit:
                continue
            pid, port = hit
            owner_pid, started = self._server_owner(pid, root_l)
            with self._lock:
                self._running[proj.name] = RunningApp(
                    name=proj.name, pid=owner_pid, port=port,
                    url=f"http://localhost:{port}", started_at=started,
                    log_file=str(log_path(proj.name)), ptype=proj.type)
            adopted.append(proj.name)
        if adopted:
            self._save_state()
        return adopted
