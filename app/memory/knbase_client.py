"""Async HTTP client for the Node.js knbase sidecar (Delta Memory writes).

Agents never talk to memory directly; the orchestrator records each completed
task's strict JSON structural summary here. All methods degrade to raising
SidecarError so callers can continue without memory when the sidecar is down.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)


class SidecarError(RuntimeError):
    pass


class KnbaseClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self._client = httpx.AsyncClient(base_url=base_url, timeout=10.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    def set_base_url(self, base_url: str) -> None:
        """Point the client at a different sidecar (Settings → Memory & MCP).

        The old client is closed in the background so the swap is synchronous
        for callers and never blocks the UI thread.
        """
        base_url = base_url.strip().rstrip("/")
        if not base_url or base_url == self.base_url:
            return
        old = self._client
        self.base_url = base_url
        self._client = httpx.AsyncClient(base_url=base_url, timeout=10.0)
        try:
            asyncio.get_running_loop().create_task(old.aclose())
        except RuntimeError:
            pass  # no loop (tests) — the old client is garbage-collected

    async def _request(
        self, method: str, path: str, *, soft_fail: bool = False, **kwargs: Any
    ) -> dict[str, Any]:
        """Issue one sidecar call.

        `soft_fail` returns the parsed error body instead of raising. Needed for
        /governance, whose rejection body carries `missingSections` but no
        `error` key — raising would collapse it to a useless "HTTP 422".
        """
        try:
            resp = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise SidecarError(f"sidecar unreachable: {exc}") from exc
        try:
            data = resp.json()
        except ValueError as exc:
            raise SidecarError(f"sidecar returned non-JSON ({resp.status_code})") from exc
        if resp.status_code >= 400 or data.get("ok") is False:
            if soft_fail:
                data.setdefault("ok", False)
                return data
            raise SidecarError(str(data.get("error", f"HTTP {resp.status_code}")))
        return data

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health")

    async def init(self, root: str) -> dict[str, Any]:
        return await self._request("POST", "/init", json={"root": root})

    async def start_session(self, root: str | None = None) -> dict[str, Any]:
        body = {"root": root} if root else {}
        return await self._request("POST", "/session/start", json=body)

    async def get_context(self, files: list[str] | None = None, full: bool = False) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if files:
            params["files"] = ",".join(files)
        if full:
            params["full"] = "1"
        return await self._request("GET", "/context", params=params)

    async def write_governance(self, key: str, content: str, summary: str) -> dict[str, Any]:
        """Author one governance document.

        Returns the response body rather than raising on rejection: a 422 means
        `content` is missing required sections, and the caller needs that list
        to log something actionable. Check `resp["ok"]`.
        """
        return await self._request(
            "POST", f"/governance/{key}",
            json={"content": content, "summary": summary},
            soft_fail=True,
        )

    async def get_governance(self, key: str) -> str:
        """Full current text of one governance document ("" when absent)."""
        data = await self.get_context(files=[key], full=True)
        for entry in data.get("fullContents", []):
            if entry.get("key") == key:
                return str(entry.get("content", ""))
        return ""

    async def begin_task(self, description: str) -> dict[str, Any]:
        return await self._request("POST", "/task/begin", json={"description": description})

    async def complete_task(self, task_id: str, summary: str) -> dict[str, Any]:
        return await self._request("POST", "/task/complete", json={"taskId": task_id, "summary": summary})

    async def append_log(self, event: str, detail: str, meta: dict[str, Any] | None = None) -> None:
        entry: dict[str, Any] = {"event": event, "detail": detail}
        if meta:
            entry["meta"] = meta
        await self._request("POST", "/log", json={"entry": entry})

    async def read_log(self, limit: int | None = None) -> list[dict[str, Any]]:
        params = {"limit": limit} if limit else {}
        data = await self._request("GET", "/log", params=params)
        return data.get("entries", [])

    async def status(self) -> dict[str, Any]:
        return await self._request("GET", "/status")
