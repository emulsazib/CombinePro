"""Agents view: cluster overview with stat cards, agent grid, recent activity."""
from __future__ import annotations

import time

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.agents import roles
from app.core.orchestrator import Orchestrator
from app.ui import feather, theme
from app.ui.flow_layout import FlowLayout
from app.ui.widgets import AgentCard, NavSidebar, StatCard

_MAX_ACTIVITY = 40


class ClusterView(QWidget):
    view_requested = pyqtSignal(str)
    add_agent_requested = pyqtSignal()
    configure_agent_requested = pyqtSignal(str)
    toggle_agent_requested = pyqtSignal(str, bool)

    def __init__(self, orchestrator: Orchestrator, state=None) -> None:  # noqa: ANN001
        super().__init__()
        self.orchestrator = orchestrator
        self.state = state
        if state is not None:
            # Roles and domains are rendered on the cards, so any roster or role
            # change has to repaint them.
            state.rosterChanged.connect(self.refresh_domains)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.nav = NavSidebar()
        self.nav.view_requested.connect(self.view_requested)
        root.addWidget(self.nav)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        # Per-pixel wheel steps; the default jumps a whole "line" per notch.
        scroll.verticalScrollBar().setSingleStep(12)
        root.addWidget(scroll, 1)

        body = QWidget()
        self._body = QVBoxLayout(body)
        self._body.setContentsMargins(28, 24, 28, 24)
        self._body.setSpacing(20)
        scroll.setWidget(body)

        self._build_header()
        self._build_toolbar()
        self._build_grid()
        self._build_activity()
        self._body.addStretch(1)

    # ----------------------------------------------------------------- header
    def _build_header(self) -> None:
        row = QHBoxLayout()
        row.setSpacing(16)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title = QLabel("Cluster Overview")
        title.setObjectName("h1")
        title_box.addWidget(title)
        subtitle = QLabel("System-wide AI orchestration and compute monitoring.")
        subtitle.setProperty("muted", True)
        title_box.addWidget(subtitle)
        title_box.addStretch(1)
        row.addLayout(title_box)
        row.addStretch(1)

        stats = QWidget()
        stats_flow = FlowLayout(stats, spacing=12)
        total = len(self.orchestrator.agents)
        self.stat_active = StatCard("Active Agents", f"00 /{total:02d}", theme.OK)
        self.stat_active.setFixedWidth(180)
        self.stat_tokens = StatCard("Total Tokens", "—")
        self.stat_tokens.setFixedWidth(180)
        self.stat_latency = StatCard("Avg Latency", "—", theme.TERTIARY)
        self.stat_latency.setFixedWidth(180)
        for card in (self.stat_active, self.stat_tokens, self.stat_latency):
            stats_flow.addWidget(card)
        row.addWidget(stats)

        self._body.addLayout(row)

    # ---------------------------------------------------------------- toolbar
    def _build_toolbar(self) -> None:
        row = QHBoxLayout()
        row.setSpacing(8)
        for label, glyph in (("  Filter", "filter"), ("  Sort", "sort")):
            btn = QPushButton(label)
            btn.setProperty("variant", "ghost")
            btn.setIcon(feather.icon(glyph, theme.TEXT_MUTED, 14))
            btn.setIconSize(feather.size_hint(14))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            row.addWidget(btn)
        row.addStretch(1)
        add = QPushButton("  Add New Agent")
        add.setProperty("variant", "primary")
        add.setIcon(feather.icon("plus", theme.ON_ACCENT, 15))
        add.setIconSize(feather.size_hint(15))
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        add.setToolTip("Configure and register a commercial or local LLM agent.")
        add.clicked.connect(self.add_agent_requested)
        row.addWidget(add)
        self._body.addLayout(row)

    # ------------------------------------------------------------------- grid
    def _build_grid(self) -> None:
        grid_wrap = QWidget()
        self._grid = FlowLayout(grid_wrap, spacing=16)
        self.agent_cards: dict[str, AgentCard] = {}
        for name, agent in self.orchestrator.agents.items():
            self._add_card(name, agent.provider)
        self._body.addWidget(grid_wrap)

    def _add_card(self, name: str, provider: str) -> AgentCard:
        card = AgentCard(
            name, provider, compact=False,
            domain=self._domain_for(name), role=self._role_for(name),
            enabled=self.orchestrator.is_agent_enabled(name),
        )
        card.configure_clicked.connect(self.configure_agent_requested)
        card.toggle_clicked.connect(self.toggle_agent_requested)
        self.agent_cards[name] = card
        self._grid.addWidget(card)
        return card

    def _domain_for(self, name: str) -> str:
        for folder, agent in self.orchestrator.domain_map.assignments().items():
            if agent == name:
                return folder or "workspace root"
        return "Unassigned"

    def _role_for(self, name: str) -> str:
        agent = self.orchestrator.agents.get(name)
        return roles.label(agent.role) if agent and agent.role else ""

    # --------------------------------------------------------------- activity
    def _build_activity(self) -> None:
        header = QLabel(f'{feather.label_html("activity", theme.TEXT_MUTED, 15)}&nbsp;&nbsp;Recent Activity')
        header.setTextFormat(Qt.TextFormat.RichText)
        header.setObjectName("h2")
        self._body.addWidget(header)

        self._activity_frame = QFrame()
        self._activity_frame.setObjectName("panelCard")
        self._activity_layout = QVBoxLayout(self._activity_frame)
        self._activity_layout.setContentsMargins(0, 0, 0, 0)
        self._activity_layout.setSpacing(0)
        self._empty = QLabel("  No activity yet — changes and agent results appear here.")
        self._empty.setProperty("muted", True)
        self._empty.setContentsMargins(16, 14, 16, 14)
        self._activity_layout.addWidget(self._empty)
        self._body.addWidget(self._activity_frame)

    def add_activity(self, kind: str, kind_color: str, text: str, meta: str = "") -> None:
        if self._empty is not None:
            self._activity_layout.removeWidget(self._empty)
            self._empty.setParent(None)
            self._empty.deleteLater()
            self._empty = None

        row = QFrame()
        row.setStyleSheet(f"border-bottom:1px solid {theme.BORDER};")
        h = QHBoxLayout(row)
        h.setContentsMargins(16, 12, 16, 12)
        h.setSpacing(14)

        ts = QLabel(time.strftime("%H:%M:%S"))
        ts.setFont(theme.mono_font(11))
        ts.setStyleSheet(f"color:{theme.TEXT_FAINT}; border:none;")
        h.addWidget(ts)

        badge = QLabel(kind.upper())
        badge.setStyleSheet(
            f"color:{kind_color}; font-size:10px; font-weight:700; "
            f"letter-spacing:0.05em; border:none;"
        )
        h.addWidget(badge)

        body = QLabel(text)
        body.setStyleSheet(f"color:{theme.TEXT}; border:none;")
        h.addWidget(body, 1)

        if meta:
            m = QLabel(meta)
            m.setStyleSheet(f"color:{theme.TEXT_FAINT}; border:none;")
            h.addWidget(m)

        self._activity_layout.insertWidget(0, row)
        while self._activity_layout.count() > _MAX_ACTIVITY:
            item = self._activity_layout.takeAt(self._activity_layout.count() - 1)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def add_agent_card(self, name: str, provider: str) -> None:
        """Append a card for a newly registered (user-added) agent."""
        if name in self.agent_cards:
            return
        self._add_card(name, provider)

    # ----------------------------------------------------------------- update
    def set_active_count(self, active: int) -> None:
        # Denominator is the agents eligible to run, not the whole roster —
        # "01 /05" would be misleading when three of the five are deactivated.
        self.stat_active.set_value(f"{active:02d} /{self.active_count():02d}")

    def refresh_domains(self) -> None:
        for name, card in self.agent_cards.items():
            card.set_domain(self._domain_for(name))
            card.set_role(self._role_for(name))
            card.set_enabled_state(self.orchestrator.is_agent_enabled(name))

    def active_count(self) -> int:
        """Agents that are activated (the denominator the stat card shows)."""
        return sum(1 for n in self.agent_cards if self.orchestrator.is_agent_enabled(n))
