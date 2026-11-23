"""Filesystem layout and environment configuration."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "mc-craft"


def home() -> Path:
    """Root for all managed state. Override with MCC_HOME."""
    raw = os.environ.get("MCC_HOME")
    if raw:
        base = Path(raw).expanduser()
    else:
        anchor = os.environ.get("LOCALAPPDATA") or str(Path.home())
        base = Path(anchor) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base.resolve()


def runtime_dir() -> Path:
    """Shared Minecraft main-dir: versions, libraries, assets, natives."""
    p = home() / "runtime"
    p.mkdir(parents=True, exist_ok=True)
    return p


def instances_dir() -> Path:
    p = home() / "instances"
    p.mkdir(parents=True, exist_ok=True)
    return p


def projects_dir() -> Path:
    p = home() / "projects"
    p.mkdir(parents=True, exist_ok=True)
    return p


def exports_dir() -> Path:
    p = home() / "exports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def java_home_candidates() -> list[Path]:
    """Known JDK locations, newest first, environment override first."""
    out: list[Path] = []
    env = os.environ.get("MCC_JAVA_HOME") or os.environ.get("JAVA_HOME")
    if env and Path(env).exists():
        out.append(Path(env))
    for base in (
        Path(r"D:\scoop\apps"),
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Eclipse Adoptium",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Java",
    ):
        if not base.exists():
            continue
        for child in sorted(base.glob("*"), reverse=True):
            for candidate in (child / "current", child):
                if (candidate / "bin" / "java.exe").exists():
                    out.append(candidate)
    return out
