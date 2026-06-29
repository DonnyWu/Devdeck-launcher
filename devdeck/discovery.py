"""Discover runnable web projects under the base dir.

Detection mirrors the /Localhost rules (same type priority + conventional ports),
limited to projects that serve on a port. Desktop (WPF/WinForms) and CLI projects
match none of the rules below and are therefore dropped from the list.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import BASE_DIR, CONVENTIONAL_PORTS

# Directories that never contain a project root and are expensive to walk.
_SKIP_DIRS = {"node_modules", "bin", "obj", "__pycache__", ".venv", "venv",
              ".git", ".idea", ".vs", "dist", "build"}

_TYPE_LABELS = {
    "streamlit": "Streamlit",
    "gradio": "Gradio",
    "vite": "Node / Vite",
    "react": "React",
    "dotnet": "ASP.NET",
    "static": "Static",
}


@dataclass
class Project:
    name: str                       # display name = top-level folder name
    root: Path                      # runnable root (may be nested under name)
    type: str                       # streamlit|gradio|vite|react|dotnet|static
    conventional_port: int
    csproj: Optional[Path] = None   # for dotnet
    npm_script: Optional[str] = None  # for vite/react

    @property
    def type_label(self) -> str:
        return _TYPE_LABELS.get(self.type, self.type)


def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _detect_in_dir(d: Path):
    """Return (type, csproj, npm_script) for a single directory, or None."""
    if (d / "app.py").exists():
        text = ""
        for marker in ("requirements.txt", "pyproject.toml"):
            f = d / marker
            if f.exists():
                text += _read_text(f).lower()
        if "streamlit" in text or any(d.glob("streamlit*.log")):
            return ("streamlit", None, None)
        if "gradio" in text:
            return ("gradio", None, None)
        # app.py with no recognised web framework -> don't guess; keep scanning.

    pkg = d / "package.json"
    if pkg.exists():
        try:
            data = json.loads(_read_text(pkg) or "{}")
        except json.JSONDecodeError:
            data = {}
        scripts = data.get("scripts", {}) or {}
        start = str(scripts.get("start", ""))
        if "react-scripts" in start:
            return ("react", None, "start")
        if "dev" in scripts:
            return ("vite", None, "dev")
        if "start" in scripts:
            # generic node server: launch via PORT env (CRA-style).
            return ("react", None, "start")

    for csproj in sorted(d.glob("*.csproj")):
        if "Microsoft.NET.Sdk.Web" in _read_text(csproj):
            return ("dotnet", csproj, None)

    if (d / "index.html").exists():
        return ("static", None, None)

    return None


def _find_runnable_root(top: Path, max_depth: int = 2):
    """Breadth-first search so the shallowest runnable root wins."""
    queue = [(top, 0)]
    while queue:
        d, depth = queue.pop(0)
        det = _detect_in_dir(d)
        if det:
            type_, csproj, npm_script = det
            return (type_, d, csproj, npm_script)
        if depth < max_depth:
            try:
                for child in sorted(d.iterdir()):
                    if child.is_dir() and child.name not in _SKIP_DIRS \
                            and not child.name.startswith("."):
                        queue.append((child, depth + 1))
            except OSError:
                pass
    return None


def discover_projects(base: Path = BASE_DIR) -> list[Project]:
    projects: list[Project] = []
    if not base.exists():
        return projects
    for top in sorted(base.iterdir()):
        if not top.is_dir() or top.name.startswith(".") or top.name == "DevDeck":
            continue
        found = _find_runnable_root(top)
        if not found:
            continue
        type_, root, csproj, npm_script = found
        projects.append(Project(
            name=top.name,
            root=root,
            type=type_,
            conventional_port=CONVENTIONAL_PORTS.get(type_, 8000),
            csproj=csproj,
            npm_script=npm_script,
        ))
    return projects
