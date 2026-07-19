"""Per-file mutexes + recent-write tracking.

Every read/write of workspace files by agents or the watcher goes through this
registry so concurrent agent wakes can't interleave writes to the same file.
`mark_written` / `recently_written` give the router echo suppression: a
watchdog delta caused by an agent's own write must not re-wake an agent.
"""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class LockRegistry:
    echo_window: float = 3.0
    _locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    _written_at: dict[str, float] = field(default_factory=dict)

    def _lock_for(self, path: str) -> asyncio.Lock:
        lock = self._locks.get(path)
        if lock is None:
            lock = self._locks[path] = asyncio.Lock()
        return lock

    @asynccontextmanager
    async def acquire(self, path: str) -> AsyncIterator[None]:
        async with self._lock_for(path):
            yield

    def mark_written(self, path: str) -> None:
        self._written_at[path] = time.monotonic()

    def recently_written(self, path: str) -> bool:
        ts = self._written_at.get(path)
        return ts is not None and (time.monotonic() - ts) < self.echo_window
