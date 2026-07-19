"""Event formatting helpers shared by the Thought Stream and Recent Activity.

Once a QDockWidget, this module is now purely presentational glue: `describe()`
turns a bus `Event` into a one-line human string, and `_event_color()` maps it
to a semantic token from `theme.py`. Both are reused by `ThoughtStream`,
`LogTerminal`, and the ClusterView "Recent Activity" list.
"""
from __future__ import annotations

from app.core.events import (
    AgentResult,
    AgentStateChanged,
    CrossDomainSignal,
    DomainAssigned,
    Event,
    FileDelta,
    MemoryWritten,
    SidecarStatus,
    TaskRequest,
)
from app.ui import theme


def _event_color(event: Event) -> str:
    """Line color by event type — mirrors the semantic tokens in theme.py."""
    if isinstance(event, FileDelta):
        return theme.TEXT_FAINT if event.change_type == "deleted" else theme.INFO
    if isinstance(event, TaskRequest):
        return theme.ACCENT_TINT
    if isinstance(event, AgentStateChanged):
        return theme.WARN if event.state == "awake" else theme.TEXT_FAINT
    if isinstance(event, AgentResult):
        return theme.OK if event.ok else theme.ERR
    if isinstance(event, CrossDomainSignal):
        return theme.PURPLE
    if isinstance(event, MemoryWritten):
        return theme.TEAL
    if isinstance(event, DomainAssigned):
        return theme.TEXT_MUTED
    if isinstance(event, SidecarStatus):
        return theme.OK if event.healthy else theme.ERR
    return theme.TEXT_MUTED


def describe(event: Event) -> str:
    if isinstance(event, FileDelta):
        extra = f" ({len(event.diff)}B diff)" if event.diff else ""
        return f"Δ {event.change_type}: {event.path}{extra}"
    if isinstance(event, TaskRequest):
        return f"wake → {event.agent_name} [{event.domain or '.'}] {event.description[:80]}"
    if isinstance(event, AgentStateChanged):
        icon = "☀" if event.state == "awake" else "☾"
        return f"{icon} agent '{event.agent_name}' is {event.state}"
    if isinstance(event, AgentResult):
        if not event.ok:
            return f"✗ {event.agent_name} failed: {event.error[:120]}"
        changed = ", ".join(f"{c.path}[{c.change_type}]" for c in event.files_changed) or "no files"
        return f"✓ {event.agent_name}: {event.summary[:100]} — {changed}"
    if isinstance(event, CrossDomainSignal):
        return (f"⇄ cross-domain [{event.urgency}] {event.origin_agent} → "
                f"'{event.target_domain}': {event.request[:100]}")
    if isinstance(event, MemoryWritten):
        return f"🧠 memory delta written (task {event.task_id}): {event.detail}"
    if isinstance(event, DomainAssigned):
        target = event.agent_name or "(unassigned)"
        return f"⚑ domain '{event.folder or '.'}' → {target}"
    if isinstance(event, SidecarStatus):
        return f"{'●' if event.healthy else '○'} sidecar {'healthy' if event.healthy else 'DOWN'}: {event.detail}"
    return f"{type(event).__name__}"
