"""Centralized configuration-change signals for the UI.

Two buses, split by what they carry:

- `EventBus` (app/core/event_bus.py) carries *runtime* events on the asyncio
  side — wakes, deltas, results, memory writes.
- `AppState` carries *configuration* changes on the Qt side — an agent was
  added, its role or model changed, a key was saved.

Before this existed, config changes propagated through an ad-hoc mesh of
per-view signals and plain-attribute callbacks, so adding an agent in the
cluster overview left the Settings pages stale until they were re-entered.
Everything that mutates the roster now emits here, and every view that displays
roster state subscribes.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal


class AppState(QObject):
    """Application-wide configuration signals. Owned by MainWindow."""

    # An agent joined the roster (name).
    agentAdded = pyqtSignal(str)
    # An existing agent's name/provider/model/role changed (name).
    agentUpdated = pyqtSignal(str)
    # An agent left the roster (name).
    agentRemoved = pyqtSignal(str)
    # Any role assignment changed.
    rolesChanged = pyqtSignal()
    # Provider keys were written to .env and connectors reloaded.
    keysChanged = pyqtSignal()
    # Catch-all: the roster changed shape and every view should reconcile.
    rosterChanged = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # Every specific roster signal also raises the catch-all, so a
        # subscriber that just wants "something changed" connects once.
        for signal in (self.agentAdded, self.agentUpdated, self.agentRemoved):
            signal.connect(lambda _name: self.rosterChanged.emit())
        for signal in (self.rolesChanged, self.keysChanged):
            signal.connect(self.rosterChanged.emit)

    # -- emit helpers: named methods read better at call sites than .emit() --
    def agent_added(self, name: str) -> None:
        self.agentAdded.emit(name)

    def agent_updated(self, name: str) -> None:
        self.agentUpdated.emit(name)

    def agent_removed(self, name: str) -> None:
        self.agentRemoved.emit(name)

    def roles_changed(self) -> None:
        self.rolesChanged.emit()

    def keys_changed(self) -> None:
        self.keysChanged.emit()
