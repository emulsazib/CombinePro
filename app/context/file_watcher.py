"""watchdog-based file sync: emits unified-diff deltas, never full-file reads.

watchdog runs its own OS thread; raw events are marshalled onto the asyncio
loop with call_soon_threadsafe, lightly coalesced per path, then diffed against
an in-memory snapshot so downstream consumers (router → agents) only ever see
the delta of a change.
"""
from __future__ import annotations

import asyncio
import difflib
import hashlib
import logging
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.core.event_bus import EventBus
from app.core.events import FileDelta
from app.core.locks import LockRegistry
from app.core.router import is_ignored

log = logging.getLogger(__name__)

_COALESCE_SECONDS = 0.35


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


class _Handler(FileSystemEventHandler):
    def __init__(self, watcher: "FileWatcher") -> None:
        self._watcher = watcher

    def _push(self, change_type: str, src_path: str) -> None:
        # Runs on the watchdog thread — marshal onto the asyncio loop.
        self._watcher.loop.call_soon_threadsafe(self._watcher.enqueue, change_type, src_path)

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._push("created", str(event.src_path))

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._push("modified", str(event.src_path))

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._push("deleted", str(event.src_path))

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._push("deleted", str(event.src_path))
            self._push("created", str(event.dest_path))


class FileWatcher:
    def __init__(
        self,
        workspace: Path,
        bus: EventBus,
        locks: LockRegistry,
        max_file_bytes: int = 512_000,
    ) -> None:
        self.workspace = workspace
        self.bus = bus
        self.locks = locks
        self.max_file_bytes = max_file_bytes
        self.loop: asyncio.AbstractEventLoop = None  # set in start()
        self._observer: Observer | None = None
        self._snapshot: dict[str, tuple[str, str]] = {}  # rel path -> (hash, content)
        self._pending: dict[str, tuple[asyncio.Task, str]] = {}

    async def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        await asyncio.to_thread(self._prime_snapshot)
        self._observer = Observer()
        self._observer.schedule(_Handler(self), str(self.workspace), recursive=True)
        self._observer.daemon = True
        self._observer.start()
        log.info("Watching %s (%d files primed)", self.workspace, len(self._snapshot))

    async def stop(self) -> None:
        for task, _ in self._pending.values():
            task.cancel()
        self._pending.clear()
        if self._observer:
            self._observer.stop()
            await asyncio.to_thread(self._observer.join, 3)
            self._observer = None

    # ------------------------------------------------------------ event path

    def enqueue(self, change_type: str, src_path: str) -> None:
        """Called on the loop thread. Coalesces bursts per path, then processes."""
        rel = self._rel(src_path)
        if rel is None or is_ignored(rel):
            return
        existing = self._pending.pop(rel, None)
        if existing:
            existing[0].cancel()
            # A create followed by rapid modifies must still surface as "created".
            if existing[1] == "created" and change_type == "modified":
                change_type = "created"

        async def fire(ct: str = change_type, path: str = rel) -> None:
            try:
                await asyncio.sleep(_COALESCE_SECONDS)
            except asyncio.CancelledError:
                return
            self._pending.pop(path, None)
            try:
                await self._process(ct, path)
            except Exception:
                log.exception("Failed to process %s %s", ct, path)

        self._pending[rel] = (asyncio.create_task(fire()), change_type)

    async def _process(self, change_type: str, rel: str) -> None:
        old = self._snapshot.get(rel)
        if change_type == "deleted":
            if old is None:
                return
            del self._snapshot[rel]
            self.bus.publish(FileDelta(
                path=rel, change_type="deleted", diff="",
                old_hash=old[0], new_hash="", source="watcher",
            ))
            return

        async with self.locks.acquire(rel):
            content = await asyncio.to_thread(self._read, self.workspace / rel)
        if content is None:
            return
        new_hash = _hash(content)
        if old is not None and old[0] == new_hash:
            return  # touch without change
        self._snapshot[rel] = (new_hash, content)

        if old is None:
            self.bus.publish(FileDelta(
                path=rel, change_type="created", diff="",
                old_hash="", new_hash=new_hash, source="watcher",
            ))
            return

        diff = "".join(difflib.unified_diff(
            old[1].splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=f"a/{rel}", tofile=f"b/{rel}", n=3,
        ))
        self.bus.publish(FileDelta(
            path=rel, change_type="modified", diff=diff,
            old_hash=old[0], new_hash=new_hash, source="watcher",
        ))

    # ------------------------------------------------------------- internals

    def _rel(self, src_path: str) -> str | None:
        try:
            return Path(src_path).resolve().relative_to(self.workspace.resolve()).as_posix()
        except ValueError:
            return None

    def _read(self, path: Path) -> str | None:
        try:
            if path.stat().st_size > self.max_file_bytes:
                return None
            data = path.read_bytes()
        except OSError:
            return None
        if b"\0" in data[:8192]:
            return None
        return data.decode("utf-8", errors="replace")

    def _prime_snapshot(self) -> None:
        """Build the initial snapshot without publishing (no startup flood)."""
        for path in self.workspace.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(self.workspace).as_posix()
            if is_ignored(rel):
                continue
            content = self._read(path)
            if content is not None:
                self._snapshot[rel] = (_hash(content), content)

    def snapshot_content(self, rel: str) -> str | None:
        entry = self._snapshot.get(rel)
        return entry[1] if entry else None

    def note_agent_write(self, rel: str, content: str) -> None:
        """Update the snapshot after the orchestrator applies an agent's write,
        so the resulting watchdog event diffs as a no-op."""
        self._snapshot[rel] = (_hash(content), content)
