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
import time
from dataclasses import replace
from pathlib import Path, PurePosixPath

from app.agents.base import AgentContext, BaseAgent
from app.agents.claude_agent import ClaudeAgent
from app.agents.gemini_agent import GeminiAgent
from app.agents.openai_agent import OpenAIAgent
from app.agents.stub_agent import StubAgent
from app import config as app_config
from app.config import AGENT_NAMES, Config
from app.context.ast_skeleton import SkeletonBuilder
from app.context.file_watcher import FileWatcher
from app.agents import providers, roles
from app.core.domain_map import DomainMap
from app.core.event_bus import EventBus
from app.core.events import (
    AgentResult,
    AgentStateChanged,
    CrossDomainSignal,
    MemoryWritten,
    PlanReady,
    SidecarStatus,
    TaskRequest,
)
from app.core.locks import LockRegistry
from app.core.agent_settings import AgentSettings
from app.core.router import LocalRouter, RuleBasedTriage
from app.memory import governance
from app.memory.knbase_client import KnbaseClient, SidecarError

log = logging.getLogger(__name__)

# Built-in agent -> the .env var holding its model id (build_agents reads these
# back through Config, so this is where a built-in's model has to be persisted).
_MODEL_ENV = {
    "claude": "CLAUDE_MODEL", "openai": "OPENAI_MODEL", "gemini": "GEMINI_MODEL",
    "kimi": "KIMI_MODEL", "glm": "GLM_MODEL",
}
_CONFIG_ATTR = {
    "ANTHROPIC_API_KEY": "anthropic_api_key", "OPENAI_API_KEY": "openai_api_key",
    "GEMINI_API_KEY": "gemini_api_key", "KIMI_API_KEY": "kimi_api_key",
    "GLM_API_KEY": "glm_api_key",
}

# The only place a Planning agent may write. Already inside IGNORE_GLOBS, so a
# plan artifact never triggers a watcher wake.
PLAN_ARTIFACT_DIR = ".combinepro/plans"
# How long a plan keeps steering router-driven wakes in the same domain.
_PLAN_TTL_SECONDS = 15 * 60


def build_agents(config: Config) -> dict[str, BaseAgent]:
    """The key-driven built-in roster. A missing key yields a StubAgent rather
    than omitting the agent, so the UI can show it as "needs a key"."""
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
    # OpenAI-protocol providers, each keeping its own badge.
    for name, key, model in (
        ("kimi", config.kimi_api_key, config.kimi_model),
        ("glm", config.glm_api_key, config.glm_model),
    ):
        spec = providers.BY_ID[name]
        agents[name] = (
            OpenAIAgent(name, model, key, base_url=spec.base_url, provider=name)
            if key else StubAgent(name, spec.env_key)
        )
    return agents


class Orchestrator:
    def __init__(self, config: Config, workspace: Path) -> None:
        self.config = config
        self.workspace = workspace
        self.bus = EventBus()
        self.locks = LockRegistry()
        self.domain_map = DomainMap(workspace, self.bus)
        self.agent_settings = AgentSettings(workspace, self.bus)
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
        # knbase holds exactly ONE active task per session, so every multi-call
        # memory sequence runs under this lock. It never wraps an agent API call
        # — agents stay parallel; only the bookkeeping serializes.
        self._memory_lock = asyncio.Lock()
        self._memory_batch_open = False
        self.governance_ok = False
        # domain -> (monotonic timestamp, plan text). Lets a file-save wake
        # respect the active plan without paying for a new planning call.
        self._recent_plans: dict[str, tuple[float, str]] = {}
        self._profiles_path = workspace / ".combinepro" / "agents.json"
        self._profiles: list[dict] = []
        self._load_dynamic_agents()
        self._apply_agent_settings()

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
            init = await self.memory.init(str(self.workspace))
            root = str(init.get("root", "") or "")
            if root and Path(root).resolve() != self.workspace.resolve():
                # knbase resolved a different project root (it walks up for
                # .knbase, then falls back to the nearest .git). Governance docs
                # would land outside the workspace.
                log.error("knbase root %s != workspace %s — memory-bank/ is outside the workspace",
                          root, self.workspace)
            session = await self.memory.start_session()
            self.memory_ok = True

            state = session.get("state", "?")
            if state == "NEEDS_BOOTSTRAP":
                session = await self._bootstrap_governance(session.get("missing", []))
                state = session.get("state", state)
            self.governance_ok = state == "CONTEXT_LOADED"

            detail = f"session {state}" if self.governance_ok else f"session {state} (delta log only)"
            self.bus.publish(SidecarStatus(healthy=True, detail=detail, source="memory"))
        except SidecarError as exc:
            self.memory_ok = False
            self.governance_ok = False
            log.warning("Memory sidecar unavailable: %s", exc)
            self.bus.publish(SidecarStatus(healthy=False, detail=str(exc), source="memory"))

    async def _bootstrap_governance(self, missing: list[str]) -> dict:
        """Author the governance docs knbase needs to leave NEEDS_BOOTSTRAP.

        Code templates rather than agent-authored: this runs at startup before
        any prompt, so it must work with zero API keys, and knbase's section
        validation is a hard gate a nondeterministic author could fail forever.
        Writes are per-key and idempotent, so a partial run self-corrects next
        start. Failure never degrades below the pre-existing append_log path.
        """
        stack = self._detect_stack()
        for key in missing:
            if key not in governance.REQUIRED_SECTIONS:
                log.warning("knbase asked for unknown governance doc %r — skipping", key)
                continue
            content = governance.render_bootstrap(key, project=self.workspace.name, stack=stack)
            gaps = governance.validate_sections(key, content)
            if gaps or governance.is_placeholder(content):
                # Caught locally, before the network call.
                log.error("bootstrap template %r invalid (missing=%s, placeholder=%s)",
                          key, gaps, governance.is_placeholder(content))
                return {"state": "NEEDS_BOOTSTRAP"}
            resp = await self.memory.write_governance(key, content, f"bootstrapped {key}")
            if not resp.get("ok"):
                log.error("knbase rejected governance %r: missing sections %s",
                          key, resp.get("missingSections"))
                return {"state": "NEEDS_BOOTSTRAP"}
            log.info("Bootstrapped governance doc '%s' (%s bytes)", key, resp.get("bytes", "?"))
        # Re-arm session.contextChecksums. get_context does NOT do this — only
        # start_session and complete_task write them — so without this the next
        # begin_task fails the contextMatchesDisk gate.
        return await self.memory.start_session()

    def _detect_stack(self) -> str:
        """A one-line tech-stack guess for the bootstrap architecture doc."""
        markers = (
            ("pyproject.toml", "Python"), ("requirements.txt", "Python"),
            ("package.json", "Node.js"), ("Cargo.toml", "Rust"),
            ("go.mod", "Go"), ("pom.xml", "Java"), ("Gemfile", "Ruby"),
        )
        found = [label for name, label in markers if (self.workspace / name).is_file()]
        return ", ".join(dict.fromkeys(found)) or "Not yet detected."

    # ----------------------------------------------------------------- wakes

    async def _handle_wake(self, task: TaskRequest) -> AgentResult | None:
        """Router entry point: one wake wrapped in its own memory batch."""
        batch_id = await self._memory_begin_batch(f"[{task.agent_name}] {task.description[:300]}")
        results: list[AgentResult] = []
        try:
            result = await self._wake(task)
            if result is not None:
                results.append(result)
            return result
        finally:
            await self._memory_finish_batch(batch_id, task.description, results)

    async def _wake(self, task: TaskRequest) -> AgentResult | None:
        """Wake one agent. Holds no memory state — the caller owns the batch."""
        agent = self.agents.get(task.agent_name)
        if agent is None:
            log.warning("No agent named '%s'", task.agent_name)
            return None
        if not agent.enabled:
            # Deactivated from the cluster overview. Checked here as well as at
            # routing so the file-watcher path is covered too.
            log.info("Agent '%s' is deactivated — skipping wake", agent.name)
            return None
        # Router-driven wakes never run the planning phase (it would double the
        # cost of every file save), but they do inherit a still-fresh plan.
        if not task.plan and task.phase != "plan":
            cached = self._plan_for_domain(task.domain)
            if cached:
                task = replace(task, plan=cached)
        # Serialize wakes per agent: a busy agent queues, it never runs loops.
        async with self._agent_locks[task.agent_name]:
            return await self._run_wake(agent, task)

    async def _run_wake(self, agent: BaseAgent, task: TaskRequest) -> AgentResult:
        agent.state = "awake"
        self.bus.publish(AgentStateChanged(agent_name=agent.name, state="awake", source="orchestrator"))
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
                if not self._write_policy_ok(agent, task, write.path):
                    log.warning(
                        "Agent '%s' (role=%s) may only write plans under %s/: %s (rejected)",
                        agent.name, agent.role or "unassigned", PLAN_ARTIFACT_DIR, write.path,
                    )
                elif self._allowed_write(write.path, task.domain):
                    await self._apply_write(write.path, write.content)
                    applied.append(write)
                else:
                    log.warning(
                        "Agent '%s' tried to write outside its domain '%s': %s (rejected)",
                        agent.name, task.domain or "(root)", write.path,
                    )
            if result.new_content is not None and task.target_file:
                # The role gate has to cover this branch too: without it a
                # planner could mutate the open file through new_content while
                # its file_writes were being rejected.
                if not self._write_policy_ok(agent, task, task.target_file):
                    log.warning(
                        "Agent '%s' (role=%s) may not rewrite %s (rejected)",
                        agent.name, agent.role or "unassigned", task.target_file,
                    )
                elif self._allowed_write(task.target_file, task.domain):
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
        return result

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
            governance=await self._governance_excerpt(),
        )

    async def _governance_excerpt(self) -> str:
        """knbase's compact context (mind map + current phase), if available."""
        if not self.memory_ok or not self.governance_ok:
            return ""
        try:
            data = await self.memory.get_context()
        except SidecarError as exc:
            log.debug("governance context unavailable: %s", exc)
            return ""
        compact = data.get("compact")
        if isinstance(compact, dict):
            compact = json.dumps(compact, indent=2, sort_keys=True)
        text = str(compact or "").strip()
        return text[: self.config.skeleton_byte_cap // 4]

    def _write_policy_ok(self, agent: BaseAgent, task: TaskRequest, rel: str) -> bool:
        """Role gate, composed with (not replacing) the domain sandbox.

        A Planning agent produces plans, not code: it may write only markdown
        under `.combinepro/plans/`. Enforced here as well as in the prompt, so a
        model that ignores its role still cannot touch source.
        """
        if not (roles.is_planner(agent.role) or task.phase == "plan"):
            return True
        path = PurePosixPath(rel.strip().replace("\\", "/"))
        return (
            str(path).startswith(f"{PLAN_ARTIFACT_DIR}/")
            and path.suffix.lower() == ".md"
            and ".." not in path.parts
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

    async def _ensure_memory(self) -> bool:
        """Reconnect if the sidecar came up late (it binds its port after the
        flat startup wait in main.py, so a slow start would otherwise be ignored
        for the whole process lifetime)."""
        if self.memory_ok:
            return True
        try:
            await self.memory.health()
        except SidecarError:
            return False
        await self._connect_memory()
        return self.memory_ok

    async def _memory_begin_batch(self, description: str) -> str | None:
        """Open one knbase task covering a whole prompt (all its agents).

        Returns a task id, or None to signal "use the append_log fallback".
        Deliberately NOT per-agent: a knbase session holds exactly one active
        task, so per-agent begins would 409 the moment two agents run at once.
        """
        if not await self._ensure_memory() or not self.governance_ok:
            return None
        async with self._memory_lock:
            if self._memory_batch_open:
                # A router wake fired inside an open batch. Fall back rather than
                # queue: blocking here would serialize agent work behind memory.
                return None
            task_id = await self._begin_with_recovery(description)
            self._memory_batch_open = task_id is not None
            return task_id

    async def _begin_with_recovery(self, description: str) -> str | None:
        """begin_task with a single retry for the two recoverable states.

        Both are cured by start_session: it rewrites session.json wholesale with
        activeTask=None and fresh contextChecksums. There is no abort_task route.
        """
        for attempt in (1, 2):
            try:
                resp = await self.memory.begin_task(description)
                return resp.get("taskId")
            except SidecarError as exc:
                text = str(exc).lower()
                recoverable = "changed since context" in text or "already active" in text
                if attempt == 2 or not recoverable:
                    log.debug("begin_task unavailable (%s); falling back to log append", exc)
                    return None
                log.info("knbase session stale (%s) — restarting session", exc)
                try:
                    await self.memory.start_session()
                except SidecarError:
                    return None
        return None

    async def _memory_finish_batch(
        self, batch_id: str | None, description: str, results: list[AgentResult]
    ) -> None:
        """Close the batch: record the delta in memory.md, then complete_task.

        The governance write is mandatory, not decorative — completeTask rejects
        the call outright unless memory.md's checksum changed during the task.
        """
        if not self.memory_ok:
            return
        summary = self._delta_summary(description, results)
        try:
            if batch_id is None:
                await self.memory.append_log(
                    "task_complete", f"[{self._agents_of(results)}] delta summary",
                    meta=json.loads(summary),
                )
            else:
                async with self._memory_lock:
                    await self._close_batch(batch_id, summary, results)
            task_id = results[0].task_id if results else ""
            detail = (results[0].summary[:120] if results else description[:120])
            self.bus.publish(MemoryWritten(task_id=task_id, detail=detail, source="memory"))
        except SidecarError as exc:
            log.warning("Memory write failed: %s", exc)
            self.bus.publish(SidecarStatus(healthy=False, detail=str(exc), source="memory"))
        finally:
            if batch_id is not None:
                self._memory_batch_open = False

    async def _close_batch(self, batch_id: str, summary: str, results: list[AgentResult]) -> None:
        try:
            doc = await self.memory.get_governance("memory")
            entry = self._delta_entry(results)
            resp = await self.memory.write_governance(
                "memory", governance.record_change(doc, entry), entry[:120]
            )
            if resp.get("ok"):
                await self.memory.complete_task(batch_id, summary)
            else:
                # Skip complete_task: it would 409 on the memory-unchanged gate.
                log.error("governance write rejected (missing %s) — logging delta instead",
                          resp.get("missingSections"))
                await self.memory.append_log("task_complete", entry, meta=json.loads(summary))
        finally:
            # Always re-arm checksums and release the task slot, so a failure
            # here cannot wedge every subsequent begin_task.
            try:
                await self.memory.start_session()
            except SidecarError as exc:
                log.warning("Could not restart knbase session: %s", exc)

    @staticmethod
    def _agents_of(results: list[AgentResult]) -> str:
        return ", ".join(dict.fromkeys(r.agent_name for r in results)) or "none"

    def _delta_entry(self, results: list[AgentResult]) -> str:
        """One human-readable bullet for memory.md's Recent Changes."""
        if not results:
            return "task completed with no agent result"
        paths = [c.path for r in results for c in r.files_changed if c.change_type != "none"]
        touched = ", ".join(list(dict.fromkeys(paths))[:6])
        head = f"{self._agents_of(results)}: {results[0].summary or results[0].error}"
        return f"{head} ({touched})" if touched else head

    def _delta_summary(self, description: str, results: list[AgentResult]) -> str:
        """The strict JSON structural summary handed to knbase."""
        return json.dumps(
            {
                "request": description[:300],
                "agents": [
                    {
                        "agent": r.agent_name,
                        "task_id": r.task_id,
                        "ok": r.ok,
                        "summary": r.summary or r.error,
                        "files_changed": [
                            {"path": c.path, "change_type": c.change_type, "symbols": list(c.symbols)}
                            for c in r.files_changed
                        ],
                        "cross_domain": (
                            {
                                "target_domain": r.cross_domain.target_domain,
                                "request": r.cross_domain.request,
                                "urgency": r.cross_domain.urgency,
                            }
                            if r.cross_domain
                            else None
                        ),
                    }
                    for r in results
                ],
            },
            sort_keys=True,
        )

    # -------------------------------------------------------- dynamic agents

    def _load_dynamic_agents(self) -> None:
        """Register user-added agent profiles persisted in .combinepro/agents.json."""
        try:
            profiles = json.loads(self._profiles_path.read_text("utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return
        if not isinstance(profiles, list):
            return
        self._profiles = [p for p in profiles if isinstance(p, dict) and p.get("name")]
        for profile in self._profiles:
            try:
                self._register_profile(profile)
            except Exception:
                log.exception("Could not register agent profile %r", profile.get("name"))

    def _profile_for(self, name: str) -> dict:
        return next((p for p in self._profiles if p.get("name") == name), {})

    def profile_for(self, name: str) -> dict:
        """Public read of a user-added agent's stored profile ({} for built-ins)."""
        return dict(self._profile_for(name))

    def reconfigure_agent(self, changes: dict) -> dict:
        """Apply the Configure modal's edits to one agent.

        Built-ins are key-driven, so their model is persisted to .env (where
        build_agents reads it); user-added agents have their profile rewritten.
        Roles always go to AgentSettings, whichever kind of agent it is.
        Returns what was applied, with flags telling the UI what to refresh.
        """
        old = str(changes.get("original_name") or changes["name"])
        new = str(changes["name"])
        if old not in self.agents:
            raise ValueError(f"no agent named '{old}'")
        built_in = old in AGENT_NAMES
        if built_in and new != old:
            raise ValueError("built-in agents cannot be renamed")
        if new != old and new in self.agents:
            raise ValueError(f"an agent named '{new}' already exists")

        provider = str(changes.get("provider") or "")
        model = str(changes.get("model") or "")
        role = roles.normalize(changes.get("role", ""))
        role_changed = role != self.agent_settings.role_of(old)
        keys_changed = False
        was_enabled = self.agent_settings.is_enabled(old) if new != old else None

        if built_in:
            # Persist the model where build_agents() will read it back.
            env_var = _MODEL_ENV.get(old)
            if env_var and model and model != getattr(self.agents[old], "model", ""):
                app_config.update_env({env_var: model})
                keys_changed = True
            self.agents = build_agents(Config())
            for name in self.agents:
                self._agent_locks.setdefault(name, asyncio.Lock())
            for profile in self._profiles:
                try:
                    self._register_profile(profile)
                except Exception:
                    log.exception("Could not re-register agent profile %r", profile.get("name"))
        else:
            profile = dict(self._profile_for(old))
            spec = providers.get(provider)
            env = dict(profile.get("env", {}))
            # Carry the credential over when the provider changes, so switching
            # e.g. OpenAI → Kimi doesn't silently downgrade the agent to a stub.
            if spec is not None and not env.get(spec.env_key):
                inherited = getattr(self.config, _CONFIG_ATTR.get(spec.env_key, ""), "")
                if inherited:
                    env[spec.env_key] = str(inherited)
            profile.update({
                "name": new, "provider": provider, "model": model, "role": role,
                "kind": spec.kind if spec else profile.get("kind", "commercial"),
                "env": env,
            })
            if new != old:
                self.agents.pop(old, None)
                self._agent_locks.pop(old, None)
                self.agent_settings.forget(old)
            self._profiles = [p for p in self._profiles if p.get("name") not in (old, new)]
            self._profiles.append(profile)
            self._persist_profiles()
            self._register_profile(profile)

        self.agent_settings.assign(new, role)
        # Renaming forgets the old entry, so an agent the user had deactivated
        # would come back active under its new name unless we carry it over.
        if was_enabled is not None:
            self.agent_settings.set_enabled(new, was_enabled)
        self._apply_agent_settings()
        agent = self.agents[new]
        # Report what the user CONFIGURED, not what the connector fell back to:
        # a StubAgent overwrites model with "stub", which would otherwise show
        # up in the UI as if their chosen version had been discarded.
        stubbed = agent.provider == "stub"
        log.info("Reconfigured agent '%s' (provider=%s, model=%s, role=%s)%s",
                 new, provider, model, role or "unassigned",
                 " — no key, running as stub" if stubbed else "")
        return {
            "name": new,
            "provider": provider or agent.provider,
            "model": model or agent.model,
            "role": role,
            "role_changed": role_changed,
            "keys_changed": keys_changed,
            # Set when the agent has no usable credential and fell back to a stub.
            "needs_key": (spec.env_key if (spec := providers.get(provider)) else "") if stubbed else "",
        }

    def _persist_profiles(self) -> None:
        self._profiles_path.parent.mkdir(parents=True, exist_ok=True)
        self._profiles_path.write_text(json.dumps(self._profiles, indent=2), "utf-8")

    def _apply_agent_settings(self) -> None:
        """Re-stamp every live agent's role and on/off state.

        Must run after anything that rebuilds connector objects — `build_agents`
        discards the old instances, and both `role` and `enabled` live on the
        instance. AgentSettings wins over the persisted profile so the UI can
        override a user-added agent's role without rewriting agents.json.
        """
        for name, agent in self.agents.items():
            agent.role = self.agent_settings.role_of(name) or roles.normalize(
                self._profile_for(name).get("role", "")
            )
            agent.enabled = self.agent_settings.is_enabled(name)

    def set_agent_role(self, name: str, role: str) -> str:
        """Assign a role at runtime (Settings → Agents, or the Configure modal)."""
        self.agent_settings.assign(name, role)
        self._apply_agent_settings()
        applied = self.agents[name].role if name in self.agents else roles.normalize(role)
        log.info("Agent '%s' role set to '%s'", name, applied or "unassigned")
        return applied

    def set_agent_enabled(self, name: str, enabled: bool) -> bool:
        """Activate or deactivate an agent (the cluster card's toggle).

        A deactivated agent keeps its configuration and stays in the roster; it
        is simply never woken — not by a prompt, not by a file change, and not
        as the planner. Returns the state now in force.
        """
        applied = self.agent_settings.set_enabled(name, enabled)
        self._apply_agent_settings()
        log.info("Agent '%s' %s", name, "activated" if applied else "deactivated")
        return applied

    def is_agent_enabled(self, name: str) -> bool:
        agent = self.agents.get(name)
        return agent.enabled if agent is not None else self.agent_settings.is_enabled(name)

    def active_agents(self) -> dict[str, BaseAgent]:
        """The agents eligible to be woken right now."""
        return {n: a for n, a in self.agents.items() if a.enabled}

    def planner_name(self) -> str | None:
        """The active agent holding the Planning role, or None.

        Deterministic when several are assigned: settings order, then
        alphabetical. Two planners are never run for one prompt. A deactivated
        planner is skipped, so the pipeline degrades to plain routing.
        """
        planners = [
            n for n in self.agent_settings.agents_with(roles.PLANNING)
            if n in self.agents and self.agents[n].enabled
        ]
        if not planners:
            return None
        if len(planners) > 1:
            planners.sort()
            log.warning("Multiple Planning agents (%s) — using '%s'",
                        ", ".join(planners), planners[0])
        return planners[0]

    def apply_runtime_config(self, config: Config) -> None:
        """Push editable knobs onto the live components (Settings → AI Models).

        Every target is a plain mutable attribute and the router re-reads its
        debounce at fire time, so changes take effect on the next event without
        restarting anything.
        """
        self.config = config
        self.router.debounce_seconds = config.debounce_seconds
        self.skeletons.byte_cap = config.skeleton_byte_cap
        self.skeletons.max_file_bytes = config.max_file_bytes
        self.watcher.max_file_bytes = config.max_file_bytes
        self.memory.set_base_url(config.sidecar_url)
        log.info(
            "Runtime config applied (debounce=%.2fs, skeleton_cap=%dB, max_file=%dB)",
            config.debounce_seconds, config.skeleton_byte_cap, config.max_file_bytes,
        )

    def reload_agents(self, config: Config) -> dict[str, BaseAgent]:
        """Rebuild every connector from a fresh Config, then re-register the
        persisted user-added profiles. Used after keys/models change in Settings."""
        self.config = config
        self.agents = build_agents(config)
        for name in self.agents:
            self._agent_locks.setdefault(name, asyncio.Lock())
        for profile in self._profiles:
            try:
                self._register_profile(profile)
            except Exception:
                log.exception("Could not re-register agent profile %r", profile.get("name"))
        # build_agents() replaced every connector instance, so roles — which live
        # on the instance — must be re-stamped or built-ins would lose them.
        self._apply_agent_settings()
        for name in self.agents:
            self.bus.publish(
                AgentStateChanged(agent_name=name, state="dormant", source="orchestrator")
            )
        log.info("Agents reloaded: %s", {n: a.provider for n, a in self.agents.items()})
        return self.agents

    def remove_agent(self, name: str) -> bool:
        """Remove a user-added agent and clear any domain assigned to it.

        Built-in agents (claude/openai/gemini) are key-driven and cannot be
        removed here — disable them by clearing their key instead.
        """
        if name not in self.agents or name in AGENT_NAMES:
            return False
        self.agents.pop(name, None)
        self._agent_locks.pop(name, None)
        self._profiles = [p for p in self._profiles if p.get("name") != name]
        self._persist_profiles()
        for folder, owner in list(self.domain_map.assignments().items()):
            if owner == name:
                self.domain_map.assign(folder, "")
        self.agent_settings.forget(name)
        log.info("Removed agent '%s'", name)
        return True

    def add_agent(self, profile: dict) -> BaseAgent:
        """Register a user-configured agent (Add New Agent dialog) and persist it."""
        agent = self._register_profile(profile)
        self._profiles = [p for p in self._profiles if p.get("name") != agent.name]
        self._profiles.append(profile)
        self._persist_profiles()
        self.bus.publish(
            AgentStateChanged(agent_name=agent.name, state="dormant", source="orchestrator")
        )
        log.info("Registered agent '%s' (%s, model=%s)", agent.name, agent.provider, agent.model)
        return agent

    def _register_profile(self, profile: dict) -> BaseAgent:
        name = str(profile["name"])
        provider = str(profile.get("provider", "custom"))
        model = str(profile.get("model", ""))
        env = {str(k): str(v) for k, v in dict(profile.get("env", {})).items()}

        agent: BaseAgent
        spec = providers.get(provider)
        key = env.get(spec.env_key) if spec else ""

        if provider == "anthropic" and key:
            agent = ClaudeAgent(name, model, key)
        elif provider == "gemini" and key:
            agent = GeminiAgent(name, model, key)
        elif spec is not None and spec.kind == "commercial" and key:
            # OpenAI, plus the OpenAI-protocol providers (Kimi, GLM). Passing
            # provider keeps their own badge instead of labelling them "local".
            agent = OpenAIAgent(name, model, key, base_url=spec.base_url or None,
                                provider=spec.id)
        elif env.get("LOCAL_BASE_URL"):
            # Ollama / vLLM / any OpenAI-compatible server.
            agent = OpenAIAgent(
                name, model,
                api_key=env.get("LOCAL_API_KEY") or "local",
                base_url=env["LOCAL_BASE_URL"],
            )
        else:
            missing = spec.env_key if spec else "a credential or LOCAL_BASE_URL"
            agent = StubAgent(name, missing_key=missing)

        agent.role = self.agent_settings.role_of(name) or roles.normalize(profile.get("role", ""))
        self.agents[name] = agent
        self._agent_locks.setdefault(name, asyncio.Lock())
        return agent

    # ------------------------------------------------------------------ misc

    def prompt_agents(
        self, description: str, target_file: str = "", agent_names: list[str] | None = None
    ) -> int:
        """Wake agents on demand from a user prompt (the AI chat bar).

        When an agent holds the Planning role, this runs a two-phase pipeline:
        the planner authors a plan, then the acting agents implement it with the
        plan in context. With no planner assigned it behaves exactly as before —
        every routed agent wakes concurrently.

        Returns how many agents were scheduled. Must be called on the running
        event loop; the work itself is one background task so the Qt thread
        never blocks.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return 0

        planner = self._select_planner(agent_names)
        actors = [
            (name, domain)
            for name, domain in self._route_prompt(description, target_file, agent_names)
            if name in self.agents and name != planner
        ]
        if planner is None and not actors:
            return 0
        loop.create_task(
            self._run_prompt_pipeline(planner, actors, description, target_file)
        )
        return len(actors) + (1 if planner else 0)

    def _select_planner(self, agent_names: list[str] | None) -> str | None:
        """The planner for this prompt, or None to skip the planning phase.

        Explicit agent_names means the user targeted specific agents — do not
        inject one they did not ask for.
        """
        if agent_names:
            return None
        return self.planner_name()

    async def _run_prompt_pipeline(
        self,
        planner: str | None,
        actors: list[tuple[str, str]],
        description: str,
        target_file: str,
    ) -> None:
        """Plan → Act, under a single knbase task covering the whole prompt."""
        batch_id = await self._memory_begin_batch(f"[prompt] {description[:300]}")
        results: list[AgentResult] = []
        try:
            plan_text = ""
            if planner is not None:
                plan_result = await self._wake(TaskRequest(
                    agent_name=planner, domain="", description=description,
                    target_file=target_file, urgency="high", source="ui", phase="plan",
                ))
                if plan_result is not None:
                    results.append(plan_result)
                    if plan_result.ok:
                        plan_text = plan_result.summary
                # A failed planner degrades to no plan; it never blocks the work.
                if plan_text:
                    self.bus.publish(PlanReady(
                        agent_name=planner, plan=plan_text, source="orchestrator"
                    ))
                else:
                    log.warning("Planning agent '%s' produced no usable plan", planner)

            now = time.monotonic()
            acted = await asyncio.gather(*[
                self._wake(TaskRequest(
                    agent_name=name, domain=domain, description=description,
                    target_file=target_file, urgency="high", source="ui",
                    phase="act", plan=plan_text,
                ))
                for name, domain in actors
            ], return_exceptions=True)
            for outcome in acted:
                if isinstance(outcome, AgentResult):
                    results.append(outcome)
                elif isinstance(outcome, BaseException):
                    log.exception("Action-phase wake failed", exc_info=outcome)

            if plan_text:
                # Let router-driven wakes in these domains reuse the plan rather
                # than paying for a new planning call on every file save.
                for _name, domain in actors:
                    self._recent_plans[domain] = (now, plan_text)
        finally:
            await self._memory_finish_batch(batch_id, description, results)

    def _plan_for_domain(self, domain: str) -> str:
        """A recent plan covering `domain`, if one is still fresh."""
        entry = self._recent_plans.get(domain)
        if entry is None:
            return ""
        created, plan = entry
        if time.monotonic() - created > _PLAN_TTL_SECONDS:
            self._recent_plans.pop(domain, None)
            return ""
        return plan

    def _route_prompt(
        self, description: str, target_file: str, agent_names: list[str] | None
    ) -> list[tuple[str, str]]:
        """Decide which agents handle a prompt and in which domain (role).

        - explicit agent_names → those agents (domain from the open file's owner)
        - a file is open with an assigned owner → that owner, in its domain
        - domains assigned → each assigned agent works its own domain (role-based)
        - otherwise → all agents, workspace-root scope

        Deactivated agents are filtered out of every branch, so the scheduled
        count the UI reports matches what actually runs.
        """
        assignments = self.domain_map.assignments()  # folder -> agent
        owner = self.domain_map.owner_of(target_file) if target_file else None
        file_domain = owner[0] if owner else ""

        if agent_names:
            plan = [(n, file_domain) for n in agent_names]
        elif owner:
            plan = [(owner[1], owner[0])]
        elif assignments:
            by_agent: dict[str, str] = {}
            for folder, agent in assignments.items():
                by_agent.setdefault(agent, folder)
            plan = list(by_agent.items())
        else:
            plan = [(name, "") for name in self.agents]
        return [(n, d) for n, d in plan if self.is_agent_enabled(n)]

    def emit_cross_domain(self, target_domain: str, request: str, urgency: str = "low") -> None:
        """Manual/simulated cross-domain signal (used by the UI debug action)."""
        self.bus.publish(CrossDomainSignal(
            target_domain=target_domain,
            request=request,
            urgency=urgency if urgency in ("low", "high") else "low",
            origin_agent="user",
            source="ui",
        ))
