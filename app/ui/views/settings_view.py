"""Settings view: [shared nav | category rail | page stack].

A thin shell. Every page is real and lives in `settings_pages/`; this class only
owns navigation and the callbacks that let pages reach live runtime state
(agent roster, orchestrator knobs, memory client).
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import Config
from app.core.orchestrator import Orchestrator
from app.ui.views.settings_pages import (
    AgentsPage,
    ApiPage,
    GeneralPage,
    GitPage,
    MemoryPage,
    ModelsPage,
    SessionStats,
    UsagePage,
)
from app.ui.widgets import NavButton, NavSidebar

_CATEGORIES = (
    ("api", "API Configuration"),
    ("general", "General"),
    ("models", "AI Models"),
    ("agents", "Agents"),
    ("memory", "Memory & MCP"),
    ("git", "Git & PRs"),
    ("usage", "Usage & Diagnostics"),
)


class SettingsView(QWidget):
    view_requested = pyqtSignal(str)
    # Raised when the agent roster changes so the main window can resync cards.
    agents_changed = pyqtSignal()
    # Raised when a page needs the app to reload Config from the environment.
    config_reload_requested = pyqtSignal()

    def __init__(
        self,
        config: Config,
        orchestrator: Orchestrator,
        workspace: Path,
        stats: SessionStats | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.orchestrator = orchestrator
        self.workspace = workspace
        self.stats = stats or SessionStats()
        # Set by MainWindow: () -> str|None opening the Add-Agent dialog.
        self.add_agent_handler = None
        # Set by MainWindow: (int) -> None applying an editor font size.
        self.font_size_handler = None

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.nav = NavSidebar()
        self.nav.view_requested.connect(self.view_requested)
        root.addWidget(self.nav)

        self.cat_rail = self._build_category_rail()
        root.addWidget(self.cat_rail)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self.api_page = ApiPage(config, self._reload_agents)
        self.general_page = GeneralPage(config, workspace, self._apply_font_size)
        self.models_page = ModelsPage(config, self._reload_agents, self._apply_knobs)
        self.agents_page = AgentsPage(orchestrator, self._add_agent, self._remove_agent)
        self.memory_page = MemoryPage(config, orchestrator)
        self.git_page = GitPage(workspace)
        self.usage_page = UsagePage(config, orchestrator, workspace, self.stats)

        self._pages = {
            "api": self.api_page,
            "general": self.general_page,
            "models": self.models_page,
            "agents": self.agents_page,
            "memory": self.memory_page,
            "git": self.git_page,
            "usage": self.usage_page,
        }
        for key, _ in _CATEGORIES:
            self.stack.addWidget(self._pages[key])

        self._select("api")

    # ----------------------------------------------------------- category rail
    def _build_category_rail(self) -> QWidget:
        rail = QFrame()
        rail.setObjectName("navSidebar")
        rail.setFixedWidth(240)
        v = QVBoxLayout(rail)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        head = QWidget()
        hb = QVBoxLayout(head)
        hb.setContentsMargins(16, 18, 16, 12)
        hb.setSpacing(2)
        who = QLabel("CombinePro Identity")
        who.setStyleSheet("font-weight:600;")
        hb.addWidget(who)
        plan = QLabel("LOCAL WORKSPACE")
        plan.setProperty("caps", True)
        hb.addWidget(plan)
        v.addWidget(head)

        self._cat_buttons: dict[str, NavButton] = {}
        for key, label in _CATEGORIES:
            btn = NavButton("•", label)
            btn.clicked.connect(lambda _=False, k=key: self._select(k))
            v.addWidget(btn)
            self._cat_buttons[key] = btn
        v.addStretch(1)
        return rail

    def _select(self, key: str) -> None:
        keys = [k for k, _ in _CATEGORIES]
        if key not in keys:
            return
        self.stack.setCurrentIndex(keys.index(key))
        for k, btn in self._cat_buttons.items():
            btn.set_active(k == key)
        # Pages that show live state refresh on entry.
        if key == "agents":
            self.agents_page.refresh()
        elif key == "usage":
            self.usage_page.refresh()

    # ------------------------------------------------------------- page hooks
    def _fresh_config(self) -> Config:
        """Rebuild Config from the (just-updated) environment and push it to the
        pages that hold a reference, so Revert and status reads stay accurate."""
        self.config = Config()
        for page in (self.api_page, self.general_page, self.models_page,
                     self.memory_page, self.usage_page):
            page.config = self.config
        return self.config

    def _reload_agents(self) -> list[str]:
        config = self._fresh_config()
        agents = self.orchestrator.reload_agents(config)
        self.agents_page.refresh()
        self.agents_changed.emit()
        return list(agents)

    def _apply_knobs(self) -> None:
        self.orchestrator.apply_runtime_config(self._fresh_config())

    def _apply_font_size(self, size: int) -> None:
        if self.font_size_handler is not None:
            self.font_size_handler(size)

    def _add_agent(self) -> str | None:
        if self.add_agent_handler is None:
            return None
        name = self.add_agent_handler()
        if name:
            self.agents_changed.emit()
        return name

    def _remove_agent(self, name: str) -> bool:
        removed = self.orchestrator.remove_agent(name)
        if removed:
            self.agents_changed.emit()
        return removed

    # ------------------------------------------------------------ live updates
    def set_sidecar_health(self, healthy: bool, detail: str = "") -> None:
        self.memory_page.set_health(healthy, detail)
