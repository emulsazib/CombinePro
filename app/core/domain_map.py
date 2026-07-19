"""Folder → agent domain allocation, persisted to .combinepro/domains.json."""
from __future__ import annotations

import json
import logging
from pathlib import Path, PurePosixPath

from app.core.event_bus import EventBus
from app.core.events import DomainAssigned

log = logging.getLogger(__name__)


class DomainMap:
    def __init__(self, workspace: Path, bus: EventBus) -> None:
        self.workspace = workspace
        self.bus = bus
        self._map: dict[str, str] = {}  # relative folder (posix, "" = root) -> agent name
        self._path = workspace / ".combinepro" / "domains.json"
        self._load()

    def _load(self) -> None:
        try:
            self._map = json.loads(self._path.read_text("utf-8"))
        except FileNotFoundError:
            self._map = {}
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Could not load %s: %s", self._path, exc)
            self._map = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._map, indent=2, sort_keys=True), "utf-8")

    def assignments(self) -> dict[str, str]:
        return dict(self._map)

    def assign(self, folder: str, agent_name: str) -> None:
        folder = str(PurePosixPath(folder)) if folder not in ("", ".") else ""
        if agent_name:
            self._map[folder] = agent_name
        else:
            self._map.pop(folder, None)
        self._save()
        self.bus.publish(DomainAssigned(folder=folder, agent_name=agent_name, source="domain_map"))

    def owner_of(self, rel_path: str) -> tuple[str, str] | None:
        """Longest-prefix match. Returns (domain_folder, agent_name) or None."""
        parts = PurePosixPath(rel_path).parts
        best: tuple[str, str] | None = None
        best_len = -1
        for folder, agent in self._map.items():
            fparts = PurePosixPath(folder).parts if folder else ()
            if parts[: len(fparts)] == fparts and len(fparts) > best_len:
                best = (folder, agent)
                best_len = len(fparts)
        return best

    def folder_for_domain(self, domain: str) -> tuple[str, str] | None:
        """Resolve a domain name (folder prefix) to (folder, agent). Case-insensitive
        fallback on the last path component so agents can say 'Backend' for 'src/backend'."""
        domain_norm = str(PurePosixPath(domain)) if domain not in ("", ".") else ""
        if domain_norm in self._map:
            return domain_norm, self._map[domain_norm]
        lowered = domain.strip().lower()
        for folder, agent in self._map.items():
            leaf = PurePosixPath(folder).name.lower() if folder else ""
            if lowered in (folder.lower(), leaf):
                return folder, agent
        return None
