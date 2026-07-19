"""Minimal asyncio pub/sub event bus.

Subscribers get their own asyncio.Queue filtered by event type. Nothing in the
system polls: consumers `await queue.get()` and stay suspended until an event
arrives — this is what makes lazy waking cheap.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from app.core.events import Event

log = logging.getLogger(__name__)


@dataclass
class _Subscription:
    types: tuple[type[Event], ...]
    queue: asyncio.Queue
    drop_oldest: bool = False


@dataclass
class EventBus:
    _subs: list[_Subscription] = field(default_factory=list)

    def subscribe(
        self,
        *types: type[Event],
        maxsize: int = 0,
        drop_oldest: bool = False,
    ) -> asyncio.Queue:
        """Register a subscriber for the given event types (all events if none given).

        drop_oldest=True is for lossy consumers (UI feeds); critical consumers
        (the router) keep the default unbounded queue.
        """
        sub = _Subscription(types=types, queue=asyncio.Queue(maxsize=maxsize), drop_oldest=drop_oldest)
        self._subs.append(sub)
        return sub.queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subs = [s for s in self._subs if s.queue is not queue]

    def publish(self, event: Event) -> None:
        """Fan out an event. Must be called from the event-loop thread."""
        for sub in self._subs:
            if sub.types and not isinstance(event, sub.types):
                continue
            try:
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                if sub.drop_oldest:
                    try:
                        sub.queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    sub.queue.put_nowait(event)
                else:
                    log.warning("Dropping %s for a full non-lossy queue", type(event).__name__)
