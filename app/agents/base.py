"""BaseAgent: the dormant-agent contract shared by every provider connector.

An agent runs NO loops and holds NO background tasks. Its entire lifecycle is
one bounded `wake()` call issued by the router: build a compact prompt (AST
skeleton + the single target file), make one provider API interaction, and
return a strict JSON structural-change summary parsed into AgentResult.
"""
from __future__ import annotations

import abc
import json
import logging
from dataclasses import dataclass

from app.core.events import AgentResult, CrossDomainSignal, FileChange, FileWrite, TaskRequest

log = logging.getLogger(__name__)

# JSON schema every agent must satisfy (kept strict: additionalProperties false,
# all fields required, nullable via anyOf).
RESULT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "One-paragraph structural summary of what changed and why.",
        },
        "files_changed": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "change_type": {"type": "string", "enum": ["created", "modified", "deleted", "none"]},
                    "symbols": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["path", "change_type", "symbols"],
                "additionalProperties": False,
            },
        },
        "new_content": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "description": "Full replacement content for the target file, or null for no edit.",
        },
        "file_writes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "change_type": {"type": "string", "enum": ["created", "modified"]},
                },
                "required": ["path", "content", "change_type"],
                "additionalProperties": False,
            },
            "description": (
                "Files to create or modify WITHIN your allocated domain. Each entry "
                "is the full file content (never a diff). Use this to author new files "
                "(e.g. a requested script) or rewrite existing ones."
            ),
        },
        "cross_domain_request": {
            "anyOf": [
                {"type": "null"},
                {
                    "type": "object",
                    "properties": {
                        "target_domain": {"type": "string"},
                        "request": {"type": "string"},
                        "urgency": {"type": "string", "enum": ["low", "high"]},
                    },
                    "required": ["target_domain", "request", "urgency"],
                    "additionalProperties": False,
                },
            ],
            "description": "Set ONLY if a change is needed outside your allocated domain.",
        },
    },
    "required": ["summary", "files_changed", "new_content", "file_writes", "cross_domain_request"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
You are one of several AI agents collaborating on a codebase inside CombinePro.
You are allocated a single domain (directory) — your role. Hard rules:
1. You MAY create new files and modify existing files, but ONLY within your
   allocated domain. Return every file you author in `file_writes`, each with its
   `path` (relative to the workspace root, inside your domain), full `content`,
   and `change_type` ("created" or "modified"). Write complete, runnable files.
2. If a change is needed OUTSIDE your domain, do NOT make it — describe it in
   `cross_domain_request` ({"target_domain", "request", "urgency"}) instead.
3. You see an AST skeleton of your domain plus the full text of the target file
   (if any). Never ask for more files.
4. When the task names a single target file, you may instead put its full new
   text in `new_content` (or null to leave it untouched); `file_writes` is
   preferred for new files and multi-file work.
5. Reply with ONLY the required JSON object: `summary`, `files_changed` (a short
   list describing each change; use "none" if nothing changed), `new_content`,
   `file_writes`, and `cross_domain_request`.
Prefer complete, correct implementations. If asked to generate something (e.g.
"a calculator script"), create the file(s) that fully satisfy the request.
"""


@dataclass(frozen=True)
class AgentContext:
    """Token-optimized context: skeleton + exactly one file, never the codebase."""

    skeleton: str
    target_file: str
    target_content: str


class AgentError(RuntimeError):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class BaseAgent(abc.ABC):
    provider = "base"

    def __init__(self, name: str, model: str) -> None:
        self.name = name
        self.model = model
        self.state: str = "dormant"

    @abc.abstractmethod
    async def _complete(self, system_static: str, system_skeleton: str, user: str) -> str:
        """One provider API call returning the raw JSON reply text."""

    async def wake(self, task: TaskRequest, ctx: AgentContext) -> AgentResult:
        user = self._build_user_message(task, ctx)
        try:
            raw = await self._complete(SYSTEM_PROMPT, ctx.skeleton, user)
            return self._parse_result(task, raw)
        except AgentError as exc:
            detail = str(exc) + (f" (retry after {exc.retry_after:.0f}s)" if exc.retry_after else "")
            log.warning("Agent '%s' failed: %s", self.name, detail)
            return AgentResult(agent_name=self.name, task_id=task.task_id, ok=False, error=detail, source=self.name)
        except Exception as exc:  # provider SDK surprises must not kill the router
            log.exception("Agent '%s' crashed during wake", self.name)
            return AgentResult(agent_name=self.name, task_id=task.task_id, ok=False, error=str(exc), source=self.name)

    def _build_user_message(self, task: TaskRequest, ctx: AgentContext) -> str:
        parts = [
            f"Domain: {task.domain or '(workspace root)'}",
            f"Urgency: {task.urgency}",
            f"Task: {task.description}",
        ]
        if ctx.target_file:
            parts.append(f"\n--- Target file: {ctx.target_file} ---\n{ctx.target_content}")
        else:
            parts.append("\n(No target file: respond with analysis; files_changed change_type 'none'.)")
        return "\n".join(parts)

    def _parse_result(self, task: TaskRequest, raw: str) -> AgentResult:
        try:
            data = json.loads(_strip_fences(raw))
        except json.JSONDecodeError as exc:
            return AgentResult(
                agent_name=self.name, task_id=task.task_id, ok=False,
                error=f"non-JSON reply: {exc}", source=self.name,
            )
        changes = tuple(
            FileChange(
                path=str(c.get("path", "")),
                change_type=c.get("change_type", "none"),
                symbols=tuple(str(s) for s in c.get("symbols", [])),
            )
            for c in data.get("files_changed", [])
            if isinstance(c, dict)
        )
        writes = tuple(
            FileWrite(
                path=str(w.get("path", "")),
                content=str(w.get("content", "")),
                change_type=w.get("change_type", "modified"),
            )
            for w in data.get("file_writes", [])
            if isinstance(w, dict) and str(w.get("path", "")).strip()
        )
        return AgentResult(
            agent_name=self.name,
            task_id=task.task_id,
            ok=True,
            summary=str(data.get("summary", "")),
            files_changed=changes,
            new_content=data.get("new_content"),
            file_writes=writes,
            cross_domain=self._parse_cross_domain(data.get("cross_domain_request")),
            source=self.name,
        )

    def _parse_cross_domain(self, req: object) -> CrossDomainSignal | None:
        if not isinstance(req, dict):
            return None
        target = str(req.get("target_domain", "")).strip()
        request = str(req.get("request", "")).strip()
        if not target or not request:
            return None
        urgency = req.get("urgency", "low")
        return CrossDomainSignal(
            target_domain=target,
            request=request,
            urgency=urgency if urgency in ("low", "high") else "low",
            origin_agent=self.name,
            source=self.name,
        )


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()
