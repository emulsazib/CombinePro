"""Async HTTP client for the Node.js knbase sidecar (Delta Memory writes).

Agents never talk to memory directly; the orchestrator records each completed
task's strict JSON structural summary here. All methods degrade to raising
SidecarError so callers can continue without memory when the sidecar is down.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)


class SidecarError(RuntimeError):
    pass


class KnbaseClient:
    def __init__(self, base_url: str) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=10.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            resp = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise SidecarError(f"sidecar unreachable: {exc}") from exc
        try:
            data = resp.json()
        except ValueError as exc:
            raise SidecarError(f"sidecar returned non-JSON ({resp.status_code})") from exc
        if resp.status_code >= 400 or data.get("ok") is False:
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
