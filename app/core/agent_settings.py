"""Per-agent settings the user assigns from the UI: role and on/off state.

Persisted to `.combinepro/agent_settings.json` as
`{"claude": {"role": "planning", "enabled": true}, ...}`.

Why these live outside the agent objects: built-in agents (claude/openai/…) are
rebuilt from `Config` by `build_agents()` and thrown away on every
`reload_agents()`, so anything stored on the instance is lost the moment a key
or model changes. This store is an orchestrator attribute that reload never
touches, which is what makes a role or a deactivation survive.

A sibling of `DomainMap`, which owns the orthogonal question of *where* an agent
may write.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.agents import roles
from app.core.event_bus import EventBus
from app.core.events import AgentEnabledChanged, RoleAssigned

log = logging.getLogger(__name__)


class AgentSettings:
    def __init__(self, workspace: Path, bus: EventBus) -> None:
        self.workspace = workspace
        self.bus = bus
        self._map: dict[str, dict] = {}  # agent name -> {"role": str, "enabled": bool}
        self._dir = workspace / ".combinepro"
        self._path = self._dir / "agent_settings.json"
        self._legacy_path = self._dir / "roles.json"
        self._load()

    # ------------------------------------------------------------------- io
    def _load(self) -> None:
        raw = self._read(self._path)
        if raw is None:
            # Roles used to live in a flat {name: role} file; carry them over.
            legacy = self._read(self._legacy_path)
            raw = {n: {"role": r} for n, r in (legacy or {}).items() if isinstance(r, str)}
            if raw:
                log.info("Migrated %d agent role(s) from roles.json", len(raw))
        for name, value in (raw or {}).items():
            if isinstance(value, str):  # tolerate a hand-edited flat entry
                value = {"role": value}
            if not isinstance(value, dict):
                continue
            self._map[str(name)] = {
                "role": roles.normalize(value.get("role", "")),
                "enabled": bool(value.get("enabled", True)),
            }

    def _read(self, path: Path) -> dict | None:
        try:
            data = json.loads(path.read_text("utf-8"))
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Could not load %s: %s", path, exc)
            return None
        return data if isinstance(data, dict) else None

    def _save(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._map, indent=2, sort_keys=True), "utf-8")

    def _entry(self, agent_name: str) -> dict:
        return self._map.setdefault(agent_name, {"role": "", "enabled": True})

    def _prune(self, agent_name: str) -> None:
        """Drop an entry that no longer says anything (default role + enabled)."""
        entry = self._map.get(agent_name)
        if entry and not entry["role"] and entry["enabled"]:
            self._map.pop(agent_name, None)

    # ---------------------------------------------------------------- roles
    def all(self) -> dict[str, dict]:
        return {name: dict(entry) for name, entry in self._map.items()}

    def role_of(self, agent_name: str) -> str:
        return self._map.get(agent_name, {}).get("role", roles.DEFAULT_ROLE)

    def agents_with(self, role: str) -> list[str]:
        """Every agent holding `role`, in stable (insertion) order."""
        wanted = roles.normalize(role)
        return [n for n, e in self._map.items() if e.get("role") == wanted]

    def assign(self, agent_name: str, role: str) -> None:
        """Set (or clear, with a falsy/unknown role) one agent's role."""
        normalized = roles.normalize(role)
        self._entry(agent_name)["role"] = normalized
        self._prune(agent_name)
        self._save()
        self.bus.publish(
            RoleAssigned(agent_name=agent_name, role=normalized, source="agent_settings")
        )

    # -------------------------------------------------------------- on/off
    def is_enabled(self, agent_name: str) -> bool:
        return bool(self._map.get(agent_name, {}).get("enabled", True))

    def disabled_agents(self) -> list[str]:
        return [n for n, e in self._map.items() if not e.get("enabled", True)]

    def set_enabled(self, agent_name: str, enabled: bool) -> bool:
        """Activate or deactivate an agent. Returns the state now in force."""
        enabled = bool(enabled)
        self._entry(agent_name)["enabled"] = enabled
        self._prune(agent_name)
        self._save()
        self.bus.publish(
            AgentEnabledChanged(agent_name=agent_name, enabled=enabled, source="agent_settings")
        )
        return enabled

    # --------------------------------------------------------------- roster
    def forget(self, agent_name: str) -> None:
        """Drop all settings for an agent removed from the roster."""
        if self._map.pop(agent_name, None) is not None:
            self._save()
