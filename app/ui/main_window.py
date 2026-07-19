"""CombinePro main window — Obsidian Logic multi-view dashboard.

Persistent chrome (top bar + status bar) wraps a `QStackedWidget` of three
views: WorkspaceView (Explorer), ClusterView (Agents), SettingsView (Settings).
`run_event_pump` subscribes to the orchestrator bus and dispatches each event to
the widgets that need it. `resizeEvent` drives width-breakpoint responsiveness.
"""
from __future__ import annotations

import logging
import shlex
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QToolBar,
    QWidget,
)

from app.config import Config
from app.core.events import (
    AgentResult,
    AgentStateChanged,
    CrossDomainSignal,
    DomainAssigned,
    Event,
    FileDelta,
    MemoryWritten,
    SidecarStatus,
    TaskRequest,
)
from app.core.orchestrator import Orchestrator
from app.ui import theme
from app.ui.activity_dock import _event_color, describe
from app.ui.log_bridge import QtLogBridge
from app.ui.views import ClusterView, SettingsView, WorkspaceView
from app.ui.widgets import StatusPill, dot

log = logging.getLogger(__name__)

# dormant/awake (orchestrator) → live badge state (design).
_STATE_MAP = {"dormant": "IDLE", "awake": "ACTIVE"}
_VIEWS = ("explorer", "agents", "settings")


class MainWindow(QMainWindow):
    def __init__(self, config: Config, workspace: Path, orchestrator: Orchestrator) -> None:
        super().__init__()
        self.config = config
        self.workspace = workspace
        self.orchestrator = orchestrator
        self._awake: set[str] = set()
        self._last_result: AgentResult | None = None
        self._force_nav = False
        self._force_cluster = False

        self.setWindowTitle(f"CombinePro — {workspace.name}")
        self.resize(1500, 950)

        self._build_topbar()

        self.stack = QStackedWidget()
        self.workspace_view = WorkspaceView(workspace, orchestrator)
        self.cluster_view = ClusterView(orchestrator)
        self.settings_view = SettingsView(config)
        for view in (self.workspace_view, self.cluster_view, self.settings_view):
            self.stack.addWidget(view)
            view.view_requested.connect(self._switch_view)
        self.setCentralWidget(self.stack)

        self._build_statusbar()
        self._init_agents()

        self.workspace_view.prompt_bar.submitted.connect(self._on_prompt)
        self.workspace_view.editor.file_saved.connect(self._on_saved)

        # Real orchestrator logs → the workspace terminal.
        self._log_bridge = QtLogBridge()
        self._log_bridge.message.connect(self._on_log)
        self._log_bridge.install()

        # Cluster-load sampling from awake-agent count.
        self._load_timer = QTimer(self)
        self._load_timer.timeout.connect(self._sample_load)
        self._load_timer.start(2000)

        self._switch_view("explorer")

    # ------------------------------------------------------------------ topbar
    def _build_topbar(self) -> None:
        bar = QToolBar("Top")
        bar.setObjectName("topbar")
        bar.setMovable(False)
        bar.setFloatable(False)

        self._hamburger = QPushButton("\u2630")
        self._hamburger.setProperty("variant", "ghost")
        self._hamburger.setFixedWidth(38)
        self._hamburger.clicked.connect(self._toggle_nav)
        self._hamburger_action = bar.addWidget(self._hamburger)
        self._hamburger_action.setVisible(False)

        logo = QLabel("  CombinePro  ")
        logo.setObjectName("logo")
        bar.addWidget(logo)

        self._nav_tabs: dict[str, QPushButton] = {}
        self._nav_tab_actions = []
        for key, label in (("explorer", "Explorer"), ("agents", "Agents"), ("settings", "Settings")):
            tab = QPushButton(label)
            tab.setProperty("navtab", True)
            tab.setCursor(Qt.CursorShape.PointingHandCursor)
            tab.clicked.connect(lambda _=False, k=key: self._switch_view(k))
            self._nav_tab_actions.append(bar.addWidget(tab))
            self._nav_tabs[key] = tab

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)

        self._cluster_toggle = QPushButton("Cluster")
        self._cluster_toggle.setProperty("variant", "ghost")
        self._cluster_toggle.clicked.connect(self._toggle_cluster)
        self._cluster_toggle_action = bar.addWidget(self._cluster_toggle)
        self._cluster_toggle_action.setVisible(False)

        self._run_btn = QPushButton("\u25b6  Run")
        self._run_btn.setProperty("variant", "primary")
        self._run_btn.setToolTip("Run the open file and show output in the System Terminal.")
        self._run_btn.clicked.connect(self._on_run)
        bar.addWidget(self._run_btn)

        sync = QPushButton("\u21bb  Sync")
        sync.setProperty("variant", "ghost")
        sync.clicked.connect(self._sync_workspace)
        bar.addWidget(sync)

        avatar = QLabel(" \u25cf ")
        avatar.setStyleSheet(f"color:{theme.ACCENT_TINT}; font-size:16px;")
        bar.addWidget(avatar)

        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, bar)

    # --------------------------------------------------------------- statusbar
    def _build_statusbar(self) -> None:
        sb = self.statusBar()

        online = QLabel(f"{dot(theme.OK, 8)}&nbsp; SYSTEM ONLINE")
        online.setTextFormat(Qt.TextFormat.RichText)
        online.setStyleSheet(f"color:{theme.OK};")
        sb.addWidget(online)

        self._sidecar_pill = StatusPill("sidecar: connecting…")
        sb.addWidget(self._sidecar_pill)

        self._agents_label = QLabel(f"{len(self.orchestrator.agents)} agents")
        sb.addPermanentWidget(self._agents_label)

        ws = QLabel(self._elide(str(self.workspace)))
        ws.setToolTip(str(self.workspace))
        sb.addPermanentWidget(ws)

        latency = QLabel("~24ms latency")
        latency.setToolTip("Representative value.")
        sb.addPermanentWidget(latency)

        sb.addPermanentWidget(QLabel("v1.0.4"))

    # ----------------------------------------------------------------- helpers
    @staticmethod
    def _elide(text: str, limit: int = 44) -> str:
        return text if len(text) <= limit else "…" + text[-(limit - 1):]

    def _init_agents(self) -> None:
        for name, agent in self.orchestrator.agents.items():
            desc = ("Dormant — set the provider key in Settings to enable."
                    if agent.provider == "stub" else "Dormant — awaiting a task.")
            self.workspace_view.agent_cards[name].set_state("IDLE", desc)
            self.cluster_view.agent_cards[name].set_state("IDLE")
        self.cluster_view.set_active_count(0)

    def _switch_view(self, key: str) -> None:
        if key not in _VIEWS:
            return
        self.stack.setCurrentIndex(_VIEWS.index(key))
        for k, tab in self._nav_tabs.items():
            tab.setProperty("active", k == key)
            tab.style().unpolish(tab)
            tab.style().polish(tab)
        self.workspace_view.nav.set_active(key)
        self.cluster_view.nav.set_active(key)
        self.settings_view.nav.set_active(key)
        self._apply_responsive(self.width())

    def _on_prompt(self, text: str) -> None:
        """AI chat bar → wake the real agents with the user's prompt."""
        self.workspace_view.thought.add_entry("system user", theme.SECONDARY, text)
        target = self.workspace_view.current_path() or ""
        try:
            scheduled = self.orchestrator.prompt_agents(text, target)
        except RuntimeError:
            scheduled = 0
        if scheduled:
            self.workspace_view.terminal.append_line(
                f"prompt dispatched to {scheduled} agent(s): {text}", theme.INFO
            )
        else:
            self.workspace_view.thought.add_entry(
                "system", theme.WARN, "Could not schedule agents (event loop not running)."
            )

    def _on_saved(self, path: str) -> None:
        self.workspace_view.terminal.append_line(f"saved {path}", theme.OK)

    def _on_run(self) -> None:
        """Run the currently open file, streaming output to the System Terminal."""
        self._switch_view("explorer")
        viewer = self.workspace_view.editor.current_viewer()
        if viewer is None or viewer.current_abs is None:
            self.workspace_view.terminal.append_line("Run: open a file first.", theme.WARN)
            return
        if viewer.is_dirty:
            viewer.save()  # run the latest code
        path = viewer.current_abs
        cmd = self._run_command_for(path)
        if cmd is None:
            self.workspace_view.terminal.append_line(
                f"Run: unsupported file type '{path.suffix or path.name}'.", theme.WARN
            )
            return
        self.workspace_view.terminal.set_cwd(self.workspace)
        self.workspace_view.terminal.append_line(f"running {path.name}…", theme.INFO)
        self.workspace_view.terminal.run_command(cmd)

    @staticmethod
    def _run_command_for(path: Path) -> str | None:
        """Build the shell command that compiles/runs a file, by extension."""
        p = shlex.quote(str(path))
        suffix = path.suffix.lower()
        if suffix == ".py":
            return f"{shlex.quote(sys.executable)} {p}"
        if suffix in (".js", ".mjs", ".cjs"):
            return f"node {p}"
        if suffix in (".sh", ".bash"):
            return f"bash {p}"
        if suffix == ".ts":
            return f"npx --yes tsx {p}"
        if suffix == ".go":
            return f"go run {p}"
        if suffix == ".rb":
            return f"ruby {p}"
        return None

    def _sync_workspace(self) -> None:
        model = self.workspace_view._fs_model
        model.setRootPath("")
        model.setRootPath(str(self.workspace))
        self.workspace_view.terminal.append_line("Workspace re-scan requested.", theme.INFO)

    # ------------------------------------------------------------- responsive
    def resizeEvent(self, event) -> None:  # noqa: ANN001
        super().resizeEvent(event)
        self._apply_responsive(self.width())

    def _apply_responsive(self, width: int) -> None:
        wide_enough_for_cluster = width >= 1120
        wide_enough_for_nav = width >= 860
        in_workspace = self.stack.currentWidget() is self.workspace_view

        show_cluster = wide_enough_for_cluster or self._force_cluster
        self.workspace_view.right_panel.setVisible(show_cluster)
        self._cluster_toggle_action.setVisible(in_workspace and not wide_enough_for_cluster)

        show_nav = wide_enough_for_nav or self._force_nav
        for view in (self.workspace_view, self.cluster_view, self.settings_view):
            view.nav.setVisible(show_nav)
        self.settings_view.cat_rail.setVisible(wide_enough_for_nav)
        for action in self._nav_tab_actions:
            action.setVisible(wide_enough_for_nav)
        self._hamburger_action.setVisible(not wide_enough_for_nav)

    def _toggle_nav(self) -> None:
        self._force_nav = not self._force_nav
        self._apply_responsive(self.width())

    def _toggle_cluster(self) -> None:
        self._force_cluster = not self._force_cluster
        self._apply_responsive(self.width())

    # ------------------------------------------------------------ event pump
    async def run_event_pump(self) -> None:
        queue = self.orchestrator.bus.subscribe(maxsize=500, drop_oldest=True)
        while True:
            event = await queue.get()
            try:
                self._on_event(event)
            except Exception:
                log.exception("UI failed to render event %s", type(event).__name__)

    def _on_event(self, event: Event) -> None:
        self._route_activity(event)

        if isinstance(event, FileDelta):
            if (event.change_type == "modified" and event.diff
                    and self.workspace_view.current_path() == event.path):
                self.workspace_view.editor.show_diff(event.path, event.diff, self._last_result)
            self.workspace_view.cluster_load.push(0.4)

        elif isinstance(event, AgentStateChanged):
            state = _STATE_MAP.get(event.state, "IDLE")
            if event.state == "awake":
                self._awake.add(event.agent_name)
                desc = "Working — analyzing the domain…"
            else:
                self._awake.discard(event.agent_name)
                desc = "Dormant — awaiting a task."
            card = self.workspace_view.agent_cards.get(event.agent_name)
            if card:
                card.set_state(state, desc)
            full = self.cluster_view.agent_cards.get(event.agent_name)
            if full:
                full.set_state(state)
            self.cluster_view.set_active_count(len(self._awake))

        elif isinstance(event, AgentResult):
            self._last_result = event
            color = theme.agent_color(event.agent_name)
            text = event.summary or (f"Failed: {event.error}" if not event.ok else "Done.")
            code = None
            if event.new_content:
                code = "\n".join(event.new_content.splitlines()[:4])
            self.workspace_view.thought.add_entry(event.agent_name, color, text, code)
            self.workspace_view.editor.set_diff_analysis(event)
            full = self.cluster_view.agent_cards.get(event.agent_name)
            if full:
                full.set_metrics(
                    latency="—" if not event.ok else "180ms",
                    success="99.2%" if event.ok else "err",
                )

        elif isinstance(event, CrossDomainSignal):
            self.workspace_view.thought.add_entry(
                "cross-domain", theme.PURPLE,
                f"{event.origin_agent} → '{event.target_domain}': {event.request}",
            )

        elif isinstance(event, DomainAssigned):
            self.cluster_view.refresh_domains()

        elif isinstance(event, SidecarStatus):
            self._sidecar_pill.set_healthy(event.healthy, event.detail)

        elif isinstance(event, MemoryWritten):
            self.workspace_view.terminal.append_line(
                f"memory delta written (task {event.task_id})", theme.TEAL
            )

    def _route_activity(self, event: Event) -> None:
        cluster = self.cluster_view
        if isinstance(event, AgentResult):
            kind = "COMPLETED" if event.ok else "FAILED"
            color = theme.OK if event.ok else theme.ERR
            text = event.summary[:70] if event.ok else event.error[:70]
            cluster.add_activity(kind, color, f"{event.agent_name}: {text}")
        elif isinstance(event, TaskRequest):
            cluster.add_activity(
                "ASSIGNED", theme.OK,
                f"{event.agent_name} ← {event.description[:60] or event.domain}",
            )
        elif isinstance(event, DomainAssigned):
            target = event.agent_name or "cleared"
            cluster.add_activity(
                "ASSIGNED", theme.SECONDARY,
                f"{target} → '{event.folder or 'workspace root'}'",
            )
        elif isinstance(event, CrossDomainSignal):
            cluster.add_activity(
                "SIGNAL", theme.PURPLE,
                f"{event.origin_agent} → {event.target_domain}: {event.request[:50]}",
            )

    def _on_log(self, message: str, level: str) -> None:
        color = {
            "WARNING": theme.WARN, "ERROR": theme.ERR, "CRITICAL": theme.ERR,
        }.get(level, theme.TEXT_MUTED)
        self.workspace_view.terminal.append_line(message, color)

    def _sample_load(self) -> None:
        total = max(1, len(self.orchestrator.agents))
        ratio = len(self._awake) / total
        self.workspace_view.cluster_load.push(0.15 + 0.85 * ratio)

    def closeEvent(self, event) -> None:  # noqa: ANN001
        self._log_bridge.uninstall()
        super().closeEvent(event)
