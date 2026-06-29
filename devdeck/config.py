"""Configuration and well-known paths for DevDeck."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "DevDeck"


def _default_base_dir() -> Path:
    """Folder holding the projects to manage.

    Set the DEVDECK_BASE_DIR environment variable to override. Otherwise default
    to the folder that contains this DevDeck install (DevDeck lives inside the
    projects folder), so no machine-specific path is baked into the source.
    """
    override = os.environ.get("DEVDECK_BASE_DIR")
    if override:
        return Path(override)
    anchor = Path(sys.executable if getattr(sys, "frozen", False)
                  else __file__).resolve()
    # The packaged app nests a second "DevDeck" folder (dist\DevDeck\DevDeck.exe),
    # so take the OUTERMOST parent named DevDeck (the project folder).
    base = None
    for parent in anchor.parents:
        if parent.name == APP_NAME:
            base = parent.parent
    if base is not None:
        return base
    return Path.home() / "Documents" / "Git"


BASE_DIR = _default_base_dir()

# Conventional starting port per detected project type. The manager increments
# from here until it finds a free one (same idea as the /Localhost skill).
CONVENTIONAL_PORTS = {
    "streamlit": 8501,
    "gradio": 7860,
    "vite": 5173,
    "react": 3000,
    "dotnet": 5000,
    "static": 8000,
}

# How long to wait for a freshly launched server to start listening on its port
# before declaring an error. .NET/React need longer (build / first compile).
STARTUP_TIMEOUTS = {
    "streamlit": 60,
    "gradio": 90,
    "vite": 60,
    "react": 90,
    "dotnet": 120,
    "static": 15,
}
DEFAULT_STARTUP_TIMEOUT = 60

# Resource-panel refresh interval.
REFRESH_MS = 2000


def _appdata_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


APPDATA_DIR = _appdata_dir()
STATE_FILE = APPDATA_DIR / "state.json"
LOGS_DIR = APPDATA_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)


def log_path(project_name: str) -> Path:
    """Per-project log file (captured stdout/stderr of the launched server)."""
    safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in project_name)
    return LOGS_DIR / f"{safe}.log"
