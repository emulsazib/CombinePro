"""Agents: the live roster — provider, model, domain, add and remove."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.config import AGENT_NAMES
from app.ui import theme
from app.ui.views.settings_pages.common import SettingsPage, ghost, primary
from app.ui.widgets import StateBadge, dot


class AgentsPage(SettingsPage):
    title = "Agents"
    subtitle = ("Every registered connector. Built-ins are driven by provider keys; "
                "agents you add here are stored in .combinepro/agents.json and reload "
                "on startup.")

    def __init__(self, orchestrator, on_add, on_remove) -> None:  # noqa: ANN001
        super().__init__()
        self.orchestrator = orchestrator
        self._on_add = on_add
        self._on_remove = on_remove

        add = primary("⊕  Add New Agent")
        add.clicked.connect(self._add_clicked)
        self.add_actions(add)

        holder = QWidget()
        self._list = QVBoxLayout(holder)
        self._list.setContentsMargins(0, 0, 0, 0)
        self._list.setSpacing(12)
        self.body.addWidget(holder)

        self.add_status_line()
        self.finish()
        self.refresh()

    # ------------------------------------------------------------------ build
    def refresh(self) -> None:
        """Rebuild the roster from live orchestrator state."""
        while self._list.count():
            item = self._list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # Unparent first: deleteLater alone leaves the old card painted
                # until the event loop runs, which ghosts behind the new rows.
                widget.setParent(None)
                widget.deleteLater()

        assignments = self.orchestrator.domain_map.assignments()
        for name, agent in self.orchestrator.agents.items():
            domains = [f or "workspace root" for f, owner in assignments.items() if owner == name]
            self._list.addWidget(self._agent_row(name, agent, domains))

    def _agent_row(self, name: str, agent, domains: list[str]) -> QFrame:  # noqa: ANN001
        built_in = name in AGENT_NAMES
        card = QFrame()
        card.setObjectName("panelCard")
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(10)
        title = QLabel(f'{dot(theme.ensure_agent_color(name), 11)}&nbsp; <b>{name}</b>')
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setObjectName("agentName")
        top.addWidget(title)
        kind = QLabel("BUILT-IN" if built_in else "USER-ADDED")
        kind.setProperty("chip", True)
        top.addWidget(kind)
        top.addStretch(1)
        state = "IDLE" if getattr(agent, "state", "dormant") == "dormant" else "ACTIVE"
        top.addWidget(StateBadge(state))
        v.addLayout(top)

        domain_text = ", ".join(domains) if domains else "unassigned"
        if agent.provider == "stub":
            detail = f"provider <b>stub</b>  ·  <b>no key configured</b>"
        else:
            detail = f"provider <b>{agent.provider}</b>  ·  model <b>{agent.model or '—'}</b>"
        meta = QLabel(f"{detail}  ·  domain <b>{domain_text}</b>")
        meta.setWordWrap(True)
        meta.setStyleSheet(f"color:{theme.TEXT_MUTED}; background:transparent;")
        v.addWidget(meta)

        actions = QHBoxLayout()
        actions.addStretch(1)
        if built_in:
            note = QLabel("Disable by clearing its key in API Configuration.")
            note.setProperty("muted", True)
            actions.addWidget(note)
        else:
            remove = ghost("Remove")
            remove.clicked.connect(lambda _=False, n=name: self._remove_clicked(n))
            actions.addWidget(remove)
        v.addLayout(actions)
        return card

    # ---------------------------------------------------------------- actions
    def _add_clicked(self) -> None:
        added = self._on_add()
        self.refresh()
        if added:
            self.report(f"Agent '{added}' registered.", theme.OK)

    def _remove_clicked(self, name: str) -> None:
        if self._on_remove(name):
            self.refresh()
            self.report(f"Agent '{name}' removed and its domains cleared.", theme.WARN)
        else:
            self.report(f"'{name}' is a built-in agent and cannot be removed.", theme.ERR)
