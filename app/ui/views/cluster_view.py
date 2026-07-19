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

from app.core.orchestrator import Orchestrator
from app.ui import theme
from app.ui.flow_layout import FlowLayout
from app.ui.widgets import AgentCard, NavSidebar, StatCard

_MAX_ACTIVITY = 40


class ClusterView(QWidget):
    view_requested = pyqtSignal(str)

    def __init__(self, orchestrator: Orchestrator) -> None:
        super().__init__()
        self.orchestrator = orchestrator

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.nav = NavSidebar()
        self.nav.view_requested.connect(self.view_requested)
        root.addWidget(self.nav)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
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
        for label in ("\u2261 Filter", "\u21c5 Sort"):
            btn = QPushButton(label)
            btn.setProperty("variant", "ghost")
            row.addWidget(btn)
        row.addStretch(1)
        add = QPushButton("\u2295  Add New Agent")
        add.setProperty("variant", "primary")
        add.setEnabled(False)
        add.setToolTip("Representative — agent roster is defined by API keys in Settings.")
        row.addWidget(add)
        self._body.addLayout(row)

    # ------------------------------------------------------------------- grid
    def _build_grid(self) -> None:
        grid_wrap = QWidget()
        self._grid = FlowLayout(grid_wrap, spacing=16)
        self.agent_cards: dict[str, AgentCard] = {}
        for name, agent in self.orchestrator.agents.items():
            owner = self._domain_for(name)
            card = AgentCard(name, agent.provider, compact=False, domain=owner)
            card.configure_clicked.connect(lambda n: self.view_requested.emit("settings"))
            self.agent_cards[name] = card
            self._grid.addWidget(card)
        self._body.addWidget(grid_wrap)

    def _domain_for(self, name: str) -> str:
        for folder, agent in self.orchestrator.domain_map.assignments().items():
            if agent == name:
                return folder or "workspace root"
        return "Unassigned"

    # --------------------------------------------------------------- activity
    def _build_activity(self) -> None:
        header = QLabel("\u21bb  Recent Activity")
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

    # ----------------------------------------------------------------- update
    def set_active_count(self, active: int) -> None:
        total = len(self.orchestrator.agents)
        self.stat_active.set_value(f"{active:02d} /{total:02d}")

    def refresh_domains(self) -> None:
        for name, card in self.agent_cards.items():
            card.set_domain(self._domain_for(name))
