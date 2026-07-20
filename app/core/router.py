"""The Local Router: the only component allowed to wake agents.

It consumes FileDelta and CrossDomainSignal events, triages them through a
pluggable TriageModel (rule-based today, local LLM later), debounces bursts,
and issues TaskRequest wakes. Agents stay strictly dormant otherwise.
"""
from __future__ import annotations

import asyncio
import fnmatch
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal, Protocol

from app.core.domain_map import DomainMap
from app.core.event_bus import EventBus
from app.core.events import CrossDomainSignal, Event, FileDelta, TaskRequest
from app.core.locks import LockRegistry

log = logging.getLogger(__name__)

IGNORE_GLOBS: tuple[str, ...] = (
    ".git/*", ".git", "node_modules/*", ".venv/*", "venv/*", "__pycache__/*",
    "*.pyc", ".combinepro/*", ".knbase/*", "memory-bank/*", "dist/*", "build/*",
    ".DS_Store", "*.lock", "*.log", ".idea/*", ".vscode/*",
    # knbase's initProject() writes AGENTS.md at the project root; without this
    # the bootstrap would trigger a spurious wake for whoever owns the root.
    "AGENTS.md",
)


def is_ignored(rel_path: str) -> bool:
    posix = rel_path.replace("\\", "/")
    return any(
        fnmatch.fnmatch(posix, pat) or fnmatch.fnmatch(f"{posix}/", pat + "/")
        or any(fnmatch.fnmatch(part, pat) for part in posix.split("/") if "/" not in pat)
        for pat in IGNORE_GLOBS
    )


@dataclass(frozen=True)
class TriageDecision:
    action: Literal["wake", "ignore", "defer"]
    reason: str
    task: TaskRequest | None = None


class TriageModel(Protocol):
    """Pluggable triage brain. Swap RuleBasedTriage for a local-LLM impl later."""

    async def triage(self, event: Event) -> TriageDecision: ...


class RuleBasedTriage:
    """Deterministic, token-free triage. Only escalates to paid APIs when a
    watched source file inside an allocated domain actually changed, or a
    cross-domain signal names a resolvable target domain."""

    def __init__(self, domain_map: DomainMap, locks: LockRegistry) -> None:
        self.domain_map = domain_map
        self.locks = locks

    async def triage(self, event: Event) -> TriageDecision:
        if isinstance(event, FileDelta):
            return self._triage_delta(event)
        if isinstance(event, CrossDomainSignal):
            return self._triage_signal(event)
        return TriageDecision("ignore", f"unhandled event {type(event).__name__}")

    def _triage_delta(self, delta: FileDelta) -> TriageDecision:
        if is_ignored(delta.path):
            return TriageDecision("ignore", "ignored path")
        if self.locks.recently_written(delta.path):
            return TriageDecision("ignore", "echo of an agent's own write")
        if delta.change_type == "deleted":
            return TriageDecision("ignore", "deletions are recorded, not routed")
        owner = self.domain_map.owner_of(delta.path)
        if owner is None:
            return TriageDecision("ignore", "no agent allocated to this path")
        folder, agent = owner
        task = TaskRequest(
            agent_name=agent,
            domain=folder,
            description=(
                f"The file '{delta.path}' changed ({delta.change_type}). Review the delta, "
                "keep the file consistent with its domain, and report the structural change."
                + (f"\n\nUnified diff of the change:\n{delta.diff}" if delta.diff else "")
            ),
            target_file=delta.path,
            urgency="low",
            source="router",
        )
        return TriageDecision("wake", f"delta in domain '{folder or '.'}'", task)

    def _triage_signal(self, sig: CrossDomainSignal) -> TriageDecision:
        resolved = self.domain_map.folder_for_domain(sig.target_domain)
        if resolved is None:
            return TriageDecision("ignore", f"unknown target domain '{sig.target_domain}'")
        folder, agent = resolved
        if agent == sig.origin_agent:
            return TriageDecision("ignore", "signal targets the origin agent's own domain")
        task = TaskRequest(
            agent_name=agent,
            domain=folder,
            description=(
                f"Cross-domain request from agent '{sig.origin_agent}' "
                f"(urgency: {sig.urgency}): {sig.request}"
            ),
            target_file="",
            urgency=sig.urgency,
            source="router",
        )
        return TriageDecision("wake", f"cross-domain signal → '{folder or '.'}'", task)


class LocalRouter:
    """Consumes bus events, debounces file deltas, and dispatches wakes."""

    def __init__(
        self,
        bus: EventBus,
        triage: TriageModel,
        wake: Callable[[TaskRequest], Awaitable[None]],
        debounce_seconds: float = 1.5,
    ) -> None:
        self.bus = bus
        self.triage = triage
        self.wake = wake
        self.debounce_seconds = debounce_seconds
        self._queue = bus.subscribe(FileDelta, CrossDomainSignal)
        self._pending: dict[str, tuple[asyncio.Task, FileDelta]] = {}
        self._tasks: set[asyncio.Task] = set()
        self._runner: asyncio.Task | None = None

    def start(self) -> None:
        self._runner = asyncio.create_task(self._run(), name="local-router")

    async def stop(self) -> None:
        for task, _ in self._pending.values():
            task.cancel()
        if self._runner:
            self._runner.cancel()
        for t in list(self._tasks):
            t.cancel()
        self._pending.clear()

    async def _run(self) -> None:
        while True:
            event = await self._queue.get()
            if isinstance(event, FileDelta):
                self._debounce(event)
            else:
                self._spawn(self._dispatch(event))

    def _debounce(self, delta: FileDelta) -> None:
        """Coalesce rapid saves: only the latest delta per path survives the window."""
        existing = self._pending.pop(delta.path, None)
        if existing:
            existing[0].cancel()

        async def fire() -> None:
            try:
                await asyncio.sleep(self.debounce_seconds)
            except asyncio.CancelledError:
                return
            self._pending.pop(delta.path, None)
            await self._dispatch(delta)

        self._pending[delta.path] = (asyncio.create_task(fire()), delta)

    async def _dispatch(self, event: Event) -> None:
        try:
            decision = await self.triage.triage(event)
        except Exception:
            log.exception("Triage failed for %s", type(event).__name__)
            return
        if decision.action != "wake" or decision.task is None:
            log.debug("Triage: %s (%s)", decision.action, decision.reason)
            return
        log.info("Waking '%s': %s", decision.task.agent_name, decision.reason)
        self._spawn(self.wake(decision.task))

    def _spawn(self, coro: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
