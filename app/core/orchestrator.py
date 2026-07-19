"""Composition root: wires the event bus, router, agents, watcher and memory.

Flow per wake:
  watcher delta / cross-domain signal → router triage → orchestrator._handle_wake
  → build AgentContext (AST skeleton + one file) → agent API call → apply write
  under lock → Delta Memory write to the knbase sidecar → events for the UI.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import replace
from pathlib import Path

from app.agents.base import AgentContext, BaseAgent
from app.agents.claude_agent import ClaudeAgent
from app.agents.gemini_agent import GeminiAgent
from app.agents.openai_agent import OpenAIAgent
from app.agents.stub_agent import StubAgent
from app.config import Config
from app.context.ast_skeleton import SkeletonBuilder
from app.context.file_watcher import FileWatcher
from app.core.domain_map import DomainMap
from app.core.event_bus import EventBus
from app.core.events import (
    AgentResult,
    AgentStateChanged,
    CrossDomainSignal,
    MemoryWritten,
    SidecarStatus,
    TaskRequest,
)
from app.core.locks import LockRegistry
from app.core.router import LocalRouter, RuleBasedTriage
from app.memory.knbase_client import KnbaseClient, SidecarError

log = logging.getLogger(__name__)


def build_agents(config: Config) -> dict[str, BaseAgent]:
    agents: dict[str, BaseAgent] = {}
    if config.anthropic_api_key:
        agents["claude"] = ClaudeAgent("claude", config.claude_model, config.anthropic_api_key)
    else:
        agents["claude"] = StubAgent("claude", "ANTHROPIC_API_KEY")
    if config.openai_api_key:
        agents["openai"] = OpenAIAgent("openai", config.openai_model, config.openai_api_key)
    else:
        agents["openai"] = StubAgent("openai", "OPENAI_API_KEY")
    if config.gemini_api_key:
        agents["gemini"] = GeminiAgent("gemini", config.gemini_model, config.gemini_api_key)
    else:
        agents["gemini"] = StubAgent("gemini", "GEMINI_API_KEY")
    return agents


class Orchestrator:
    def __init__(self, config: Config, workspace: Path) -> None:
        self.config = config
        self.workspace = workspace
        self.bus = EventBus()
        self.locks = LockRegistry()
        self.domain_map = DomainMap(workspace, self.bus)
        self.skeletons = SkeletonBuilder(
            byte_cap=config.skeleton_byte_cap, max_file_bytes=config.max_file_bytes
        )
        self.watcher = FileWatcher(workspace, self.bus, self.locks, config.max_file_bytes)
        self.memory = KnbaseClient(config.sidecar_url)
        self.agents = build_agents(config)
        self.router = LocalRouter(
            self.bus,
            RuleBasedTriage(self.domain_map, self.locks),
            wake=self._handle_wake,
            debounce_seconds=config.debounce_seconds,
        )
        self._agent_locks: dict[str, asyncio.Lock] = {name: asyncio.Lock() for name in self.agents}
        self.memory_ok = False

    # ------------------------------------------------------------- lifecycle

    async def start(self) -> None:
        await self._connect_memory()
        await self.watcher.start()
        self.router.start()
        log.info(
            "Orchestrator up. Agents: %s",
            {n: a.provider for n, a in self.agents.items()},
        )

    async def stop(self) -> None:
        await self.router.stop()
        await self.watcher.stop()
        await self.memory.aclose()

    async def _connect_memory(self) -> None:
        try:
            await self.memory.health()
            await self.memory.init(str(self.workspace))
            session = await self.memory.start_session()
            self.memory_ok = True
            state = session.get("state", "?")
            self.bus.publish(SidecarStatus(healthy=True, detail=f"session {state}", source="memory"))
        except SidecarError as exc:
            self.memory_ok = False
            log.warning("Memory sidecar unavailable: %s", exc)
            self.bus.publish(SidecarStatus(healthy=False, detail=str(exc), source="memory"))

    # ----------------------------------------------------------------- wakes

    async def _handle_wake(self, task: TaskRequest) -> None:
        agent = self.agents.get(task.agent_name)
        if agent is None:
            log.warning("No agent named '%s'", task.agent_name)
            return
        # Serialize wakes per agent: a busy agent queues, it never runs loops.
        async with self._agent_locks[task.agent_name]:
            await self._run_wake(agent, task)

    async def _run_wake(self, agent: BaseAgent, task: TaskRequest) -> None:
        agent.state = "awake"
        self.bus.publish(AgentStateChanged(agent_name=agent.name, state="awake", source="orchestrator"))
        remote_task_id = await self._memory_begin(task)
        try:
            ctx = await self._build_context(task)
            result = await agent.wake(task, ctx)
        finally:
            agent.state = "dormant"
            self.bus.publish(AgentStateChanged(agent_name=agent.name, state="dormant", source="orchestrator"))

        # Apply file writes BEFORE publishing the result, scoped to the agent's
        # domain (role). This lets the agent create/modify multiple files; the UI
        # opens exactly the files that landed on disk.
        applied: list = []
        if result.ok:
            for write in result.file_writes:
                if self._allowed_write(write.path, task.domain):
                    await self._apply_write(write.path, write.content)
                    applied.append(write)
                else:
                    log.warning(
                        "Agent '%s' tried to write outside its domain '%s': %s (rejected)",
                        agent.name, task.domain or "(root)", write.path,
                    )
            if result.new_content is not None and task.target_file:
                if self._allowed_write(task.target_file, task.domain):
                    await self._apply_write(task.target_file, result.new_content)

        if applied != list(result.file_writes):
            result = replace(result, file_writes=tuple(applied))

        self.bus.publish(result)
        if result.cross_domain is not None:
            log.info(
                "Cross-domain signal from '%s' → '%s'",
                result.agent_name, result.cross_domain.target_domain,
            )
            self.bus.publish(result.cross_domain)
        await self._memory_complete(remote_task_id, task, result)

    async def _build_context(self, task: TaskRequest) -> AgentContext:
        skeleton = await asyncio.to_thread(
            self.skeletons.skeleton_for_domain, self.workspace, task.domain
        )
        content = ""
        if task.target_file:
            cached = self.watcher.snapshot_content(task.target_file)
            if cached is not None:
                content = cached
            else:
                async with self.locks.acquire(task.target_file):
                    try:
                        content = await asyncio.to_thread(
                            (self.workspace / task.target_file).read_text, "utf-8"
                        )
                    except OSError as exc:
                        log.warning("Cannot read %s: %s", task.target_file, exc)
        return AgentContext(
            skeleton=skeleton or "(empty domain — no parseable source files)",
            target_file=task.target_file,
            target_content=content,
        )

    def _allowed_write(self, rel: str, domain: str) -> bool:
        """A write is allowed if it stays inside the workspace and, when the task
        has a domain (role), inside that domain."""
        rel = rel.strip()
        if not rel:
            return False
        ws = self.workspace.resolve()
        try:
            target = (self.workspace / rel).resolve()
            target.relative_to(ws)  # inside the workspace
        except (ValueError, OSError):
            return False
        if domain:
            try:
                target.relative_to((self.workspace / domain).resolve())
            except (ValueError, OSError):
                return False
        return True

    async def _apply_write(self, rel: str, content: str) -> None:
        path = self.workspace / rel
        async with self.locks.acquire(rel):
            # mark_written BEFORE the write so the watchdog echo is suppressed.
            self.locks.mark_written(rel)
            path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(path.write_text, content, "utf-8")
            self.watcher.note_agent_write(rel, content)
        log.info("Applied agent write to %s (%d bytes)", rel, len(content))

    # ---------------------------------------------------------------- memory

    async def _memory_begin(self, task: TaskRequest) -> str | None:
        if not self.memory_ok:
            return None
        try:
            resp = await self.memory.begin_task(
                f"[{task.agent_name}] {task.description[:300]}"
            )
            return resp.get("taskId")
        except SidecarError as exc:
            log.debug("begin_task unavailable (%s); will fall back to log append", exc)
            return None

    async def _memory_complete(self, remote_task_id: str | None, task: TaskRequest, result: AgentResult) -> None:
        if not self.memory_ok:
            return
        summary = json.dumps(
            {
                "agent": result.agent_name,
                "task_id": result.task_id,
                "ok": result.ok,
                "summary": result.summary or result.error,
                "files_changed": [
                    {"path": c.path, "change_type": c.change_type, "symbols": list(c.symbols)}
                    for c in result.files_changed
                ],
                "cross_domain": (
                    {
                        "target_domain": result.cross_domain.target_domain,
                        "request": result.cross_domain.request,
                        "urgency": result.cross_domain.urgency,
                    }
                    if result.cross_domain
                    else None
                ),
            },
            sort_keys=True,
        )
        try:
            if remote_task_id:
                await self.memory.complete_task(remote_task_id, summary)
            else:
                await self.memory.append_log("task_complete", f"[{result.agent_name}] delta summary", meta=json.loads(summary))
            self.bus.publish(MemoryWritten(task_id=result.task_id, detail=result.summary[:120], source="memory"))
        except SidecarError as exc:
            log.warning("Memory write failed: %s", exc)
            self.bus.publish(SidecarStatus(healthy=False, detail=str(exc), source="memory"))

    # ------------------------------------------------------------------ misc

    def prompt_agents(
        self, description: str, target_file: str = "", agent_names: list[str] | None = None
    ) -> int:
        """Wake agents on demand from a user prompt (the AI chat bar).

        Runs the real wake pipeline for each agent; the resulting
        AgentStateChanged / AgentResult / cross-domain events flow to the UI
        through the bus, exactly like router-driven wakes. Returns how many
        agents were scheduled. Must be called on the running event loop.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return 0

        plan = self._route_prompt(description, target_file, agent_names)
        scheduled = 0
        for name, domain in plan:
            if name not in self.agents:
                continue
            task = TaskRequest(
                agent_name=name, domain=domain, description=description,
                target_file=target_file, urgency="high", source="ui",
            )
            loop.create_task(self._handle_wake(task))
            scheduled += 1
        return scheduled

    def _route_prompt(
        self, description: str, target_file: str, agent_names: list[str] | None
    ) -> list[tuple[str, str]]:
        """Decide which agents handle a prompt and in which domain (role).

        - explicit agent_names → those agents (domain from the open file's owner)
        - a file is open with an assigned owner → that owner, in its domain
        - domains assigned → each assigned agent works its own domain (role-based)
        - otherwise → all agents, workspace-root scope
        """
        assignments = self.domain_map.assignments()  # folder -> agent
        owner = self.domain_map.owner_of(target_file) if target_file else None
        file_domain = owner[0] if owner else ""

        if agent_names:
            return [(n, file_domain) for n in agent_names]
        if owner:
            return [(owner[1], owner[0])]
        if assignments:
            by_agent: dict[str, str] = {}
            for folder, agent in assignments.items():
                by_agent.setdefault(agent, folder)
            return list(by_agent.items())
        return [(name, "") for name in self.agents]

    def emit_cross_domain(self, target_domain: str, request: str, urgency: str = "low") -> None:
        """Manual/simulated cross-domain signal (used by the UI debug action)."""
        self.bus.publish(CrossDomainSignal(
            target_domain=target_domain,
            request=request,
            urgency=urgency if urgency in ("low", "high") else "low",
            origin_agent="user",
            source="ui",
        ))
