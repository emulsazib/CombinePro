"""Typed events carried on the internal asyncio event bus.

All events are immutable dataclasses. Agents never see these objects — they
exist only inside the orchestrator process; agents receive compact prompts and
return strict JSON (see agents/base.py).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Literal

Urgency = Literal["low", "high"]
ChangeType = Literal["created", "modified", "deleted", "none"]


def _now() -> float:
    return time.time()


@dataclass(frozen=True, slots=True, kw_only=True)
class Event:
    ts: float = field(default_factory=_now)
    source: str = "system"


@dataclass(frozen=True, slots=True, kw_only=True)
class FileDelta(Event):
    """A debounced change to one file, carried as a unified diff (never the full file)."""

    path: str  # relative to workspace root
    change_type: ChangeType
    diff: str  # unified diff body ("" for created/deleted)
    old_hash: str
    new_hash: str


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskRequest(Event):
    """The router's wake order for exactly one agent."""

    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    agent_name: str = ""
    domain: str = ""  # folder prefix owning the work
    description: str = ""
    target_file: str = ""  # relative path; the ONE file the agent may mutate
    urgency: Urgency = "low"


@dataclass(frozen=True, slots=True, kw_only=True)
class FileChange:
    path: str
    change_type: ChangeType
    symbols: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class FileWrite:
    """A concrete file the agent wants created/modified, with full content.

    Unlike FileChange (a summary), this carries the bytes the orchestrator will
    write to disk (after domain/role scoping)."""

    path: str  # relative to workspace root
    content: str
    change_type: ChangeType = "modified"


@dataclass(frozen=True, slots=True, kw_only=True)
class CrossDomainSignal(Event):
    """Spec payload: an agent needs a change outside its allocated directory."""

    target_domain: str
    request: str
    urgency: Urgency = "low"
    origin_agent: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentResult(Event):
    """Strict structural-change summary returned by a woken agent."""

    agent_name: str
    task_id: str
    ok: bool
    summary: str = ""
    files_changed: tuple[FileChange, ...] = ()
    new_content: str | None = None  # proposed content for the task's target_file
    file_writes: tuple[FileWrite, ...] = ()  # files to create/modify in-domain
    cross_domain: CrossDomainSignal | None = None
    error: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentStateChanged(Event):
    agent_name: str
    state: Literal["dormant", "awake"]


@dataclass(frozen=True, slots=True, kw_only=True)
class DomainAssigned(Event):
    folder: str  # relative folder prefix ("" clears)
    agent_name: str  # "" = unassigned


@dataclass(frozen=True, slots=True, kw_only=True)
class MemoryWritten(Event):
    task_id: str
    detail: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SidecarStatus(Event):
    healthy: bool
    detail: str = ""
