"""Filesystem locations that differ between a source checkout and a built app.

In a PyInstaller bundle the code lives in a read-only, replaced-on-update
directory, so anything the user edits (their `.env`) must live in the per-user
application-data directory instead. Read-only assets shipped with the app
(icons, the Node sidecar) come from the bundle's resource root.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "CombinePro"

# Repo root when running from source: .../CombinePro/app/paths.py -> .../CombinePro
REPO_ROOT = Path(__file__).resolve().parent.parent


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """Root for read-only assets shipped with the app (icons, sidecar)."""
    if is_frozen():
        # onedir builds set _MEIPASS to the bundled resource root.
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return REPO_ROOT


def resource_path(*parts: str) -> Path:
    return resource_dir().joinpath(*parts)


def user_data_dir() -> Path:
    """Per-user, writable directory for settings the app persists."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_NAME


def env_path() -> Path:
    """Where the `.env` holding API keys and preferences lives.

    From source it stays next to the repo so the dev workflow is unchanged; in a
    built app it moves to the user-data directory, which is writable and
    survives upgrades.
    """
    if not is_frozen():
        return REPO_ROOT / ".env"
    path = user_data_dir() / ".env"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        # Seed from the bundled example so first launch has the key names.
        example = resource_path(".env.example")
        try:
            path.write_text(
                example.read_text("utf-8") if example.is_file() else "", "utf-8"
            )
        except OSError:
            pass
    return path
