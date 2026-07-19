"""Central configuration: env vars, model IDs, sidecar URL, workspace root."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from app.paths import REPO_ROOT, env_path

# In a built app this resolves to the per-user data dir (writable, survives
# upgrades); from source it stays next to the repo.
ENV_PATH = env_path()
load_dotenv(ENV_PATH)

AGENT_NAMES = ("claude", "openai", "gemini")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def update_env(values: dict[str, str]) -> None:
    """Persist key/value pairs to the repo `.env`, preserving other lines.

    Used by the Settings API-key form to save provider keys. Empty values are
    written as blank assignments (which the loader treats as "no key" → stub).
    Also updates `os.environ` for the running process.
    """
    lines: list[str] = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text("utf-8").splitlines()

    remaining = dict(values)
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in remaining:
                out.append(f"{key}={remaining.pop(key)}")
                continue
        out.append(line)

    for key, value in remaining.items():
        out.append(f"{key}={value}")

    ENV_PATH.write_text("\n".join(out) + "\n", "utf-8")
    for key, value in values.items():
        os.environ[key] = value


def masked(value: str) -> str:
    """Mask a secret for display: keep nothing, show fixed-width dots, or empty."""
    if not value:
        return ""
    return "•" * 24


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    openai_api_key: str = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", ""))
    gemini_api_key: str = field(default_factory=lambda: os.environ.get("GEMINI_API_KEY", ""))

    claude_model: str = field(default_factory=lambda: os.environ.get("CLAUDE_MODEL", "claude-opus-4-8"))
    openai_model: str = field(default_factory=lambda: os.environ.get("OPENAI_MODEL", "gpt-5.1"))
    gemini_model: str = field(default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-2.5-pro"))

    sidecar_url: str = field(default_factory=lambda: os.environ.get("SIDECAR_URL", "http://127.0.0.1:8787"))
    workspace: str = field(default_factory=lambda: os.environ.get("COMBINEPRO_WORKSPACE", ""))

    # Token-optimization knobs (editable live from Settings → AI Models)
    skeleton_byte_cap: int = field(default_factory=lambda: _env_int("SKELETON_BYTE_CAP", 24_000))
    max_file_bytes: int = field(default_factory=lambda: _env_int("MAX_FILE_BYTES", 512_000))
    debounce_seconds: float = field(default_factory=lambda: _env_float("DEBOUNCE_SECONDS", 1.5))
    editor_font_size: int = field(default_factory=lambda: _env_int("EDITOR_FONT_SIZE", 13))
