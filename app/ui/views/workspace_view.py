"""Explorer view: [nav + file tree | tabbed editor + terminal | agent cluster].

The IDE-style workspace. The left rail hosts the shared NavSidebar with the
project file tree; the center stacks the tabbed code editor over the system
terminal; the right panel is the live Agent Cluster (compact cards + AI Thought
Stream + Cluster Load). Right-clicking a folder assigns an agent domain.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QDir, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QFileSystemModel
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QSplitter,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from app.core.orchestrator import Orchestrator
from app.ui import feather, theme
from app.ui.editor_tabs import EditorTabs
from app.ui.widgets import (
    AgentCard,
    ClusterLoadChart,
    LogTerminal,
    NavSidebar,
    PromptBar,
    ThoughtStream,
)


# How many agent cards the cluster roster shows before it starts scrolling.
_VISIBLE_AGENT_CARDS = 3


class WorkspaceView(QWidget):
    view_requested = pyqtSignal(str)

    def __init__(self, workspace: Path, orchestrator: Orchestrator) -> None:
        super().__init__()
        self.workspace = workspace
        self.orchestrator = orchestrator

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(1)
        root.addWidget(self.splitter)

        self._build_left()
        self._build_center()
        self._build_right()

        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([240, 900, 340])
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)

    # -------------------------------------------------------------- left rail
    def _build_left(self) -> None:
        self.nav = NavSidebar()
        self.nav.view_requested.connect(self.view_requested)
        self.nav.setFixedWidth(260)

        self._fs_model = QFileSystemModel(self)
        self._fs_model.setRootPath(str(self.workspace))
        self._fs_model.setFilter(
            QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot
        )
        self.tree = QTreeView()
        self.tree.setModel(self._fs_model)
        self.tree.setRootIndex(self._fs_model.index(str(self.workspace)))
        for col in range(1, self._fs_model.columnCount()):
            self.tree.hideColumn(col)
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(True)
        self.tree.setVerticalScrollMode(QTreeView.ScrollMode.ScrollPerPixel)
        self.tree.setHorizontalScrollMode(QTreeView.ScrollMode.ScrollPerPixel)
        self.tree.setIndentation(14)
        self.tree.clicked.connect(self._tree_clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_context_menu)

        tree_wrap = QWidget()
        tv = QVBoxLayout(tree_wrap)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(0)
        header = QLabel(f'&nbsp;{feather.label_html("folder", theme.TEXT_MUTED, 14)}&nbsp;&nbsp;EXPLORER')
        header.setTextFormat(Qt.TextFormat.RichText)
        header.setObjectName("panelHeader")
        tv.addWidget(header)
        tv.addWidget(self.tree, 1)

        self.nav.set_fill(tree_wrap)
        self.splitter.addWidget(self.nav)

    # ----------------------------------------------------------------- center
    def _build_center(self) -> None:
        center = QSplitter(Qt.Orientation.Vertical)
        center.setHandleWidth(1)

        editor_wrap = QWidget()
        ev = QVBoxLayout(editor_wrap)
        ev.setContentsMargins(0, 0, 0, 0)
        ev.setSpacing(0)
        self.editor = EditorTabs()
        ev.addWidget(self.editor, 1)
        self.prompt_bar = PromptBar()
        ev.addWidget(self.prompt_bar)
        center.addWidget(editor_wrap)

        self.terminal = LogTerminal("SYSTEM TERMINAL")
        self.terminal.set_cwd(self.workspace)
        center.addWidget(self.terminal)

        center.setStretchFactor(0, 3)
        center.setStretchFactor(1, 1)
        center.setSizes([620, 200])
        self.splitter.addWidget(center)

    # ------------------------------------------------------------------ right
    def _build_right(self) -> None:
        self.right_panel = QFrame()
        self.right_panel.setObjectName("navSidebar")
        self.right_panel.setMinimumWidth(300)
        rv = QVBoxLayout(self.right_panel)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)

        header = QLabel(f'&nbsp;{feather.label_html("cpu", theme.TEXT_MUTED, 14)}&nbsp;&nbsp;AGENT CLUSTER')
        header.setTextFormat(Qt.TextFormat.RichText)
        header.setObjectName("panelHeader")
        rv.addWidget(header)

        cards_wrap = QWidget()
        self._cards_layout = QVBoxLayout(cards_wrap)
        self._cards_layout.setContentsMargins(12, 12, 12, 12)
        self._cards_layout.setSpacing(10)
        self.agent_cards: dict[str, AgentCard] = {}
        for name, agent in self.orchestrator.agents.items():
            card = AgentCard(name, agent.provider, compact=True)
            self.agent_cards[name] = card
            self._cards_layout.addWidget(card)
        # Trailing stretch: the scroll area resizes its widget to the viewport,
        # and without somewhere for the slack to go a QVBoxLayout pads the cards
        # themselves — a one-line card would inflate to match a two-line one.
        self._cards_layout.addStretch(1)

        # Cap the roster at a few cards and scroll the rest: the roster grows
        # with every agent added, and without a bound it would keep squeezing
        # the thought stream below it.
        self._cards_scroll = QScrollArea()
        self._cards_scroll.setWidgetResizable(True)
        self._cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._cards_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._cards_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._cards_scroll.setWidget(cards_wrap)
        self._cards_scroll.verticalScrollBar().setSingleStep(12)
        rv.addWidget(self._cards_scroll)
        self.refresh_cards_viewport()

        stream_header = QLabel(f'&nbsp;{feather.label_html("message", theme.TEXT_MUTED, 14)}&nbsp;&nbsp;AI THOUGHT STREAM')
        stream_header.setTextFormat(Qt.TextFormat.RichText)
        stream_header.setObjectName("panelHeader")
        rv.addWidget(stream_header)
        self.thought = ThoughtStream()
        rv.addWidget(self.thought, 1)

        load_wrap = QWidget()
        lv = QVBoxLayout(load_wrap)
        lv.setContentsMargins(12, 10, 12, 12)
        lv.setSpacing(8)
        load_label = QLabel(f'{feather.label_html("activity", theme.TEXT_FAINT, 12)}&nbsp;&nbsp;CLUSTER LOAD')
        load_label.setTextFormat(Qt.TextFormat.RichText)
        load_label.setProperty("caps", True)
        lv.addWidget(load_label)
        self.cluster_load = ClusterLoadChart()
        self.cluster_load.setFixedHeight(64)
        lv.addWidget(self.cluster_load)
        rv.addWidget(load_wrap)

        self.splitter.addWidget(self.right_panel)

    # ------------------------------------------------------------- tree logic
    def _tree_clicked(self, index) -> None:  # noqa: ANN001
        path = Path(self._fs_model.filePath(index))
        if path.is_file():
            rel = self._rel(path)
            self.editor.open_file(path, rel_label=rel or str(path))

    def _tree_context_menu(self, position) -> None:  # noqa: ANN001
        index = self.tree.indexAt(position)
        if not index.isValid():
            return
        path = Path(self._fs_model.filePath(index))
        folder = path if path.is_dir() else path.parent
        rel = self._rel(folder)
        if rel is None:
            return
        menu = QMenu(self)
        assign = menu.addMenu("Assign Agent")
        for name in self.orchestrator.agents:  # includes user-added agents
            act = QAction(name, self)
            act.triggered.connect(lambda _=False, n=name, f=rel: self._assign(f, n))
            assign.addAction(act)
        clear = QAction("Clear assignment", self)
        clear.triggered.connect(lambda: self._assign(rel, ""))
        menu.addAction(clear)
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _assign(self, folder: str, agent: str) -> None:
        self.orchestrator.domain_map.assign(folder, agent)

    def _rel(self, path: Path) -> str | None:
        try:
            rel = path.resolve().relative_to(self.workspace.resolve()).as_posix()
            return "" if rel == "." else rel
        except ValueError:
            return None

    def add_agent_card(self, name: str, provider: str) -> None:
        """Append a compact cluster card for a newly registered agent."""
        if name in self.agent_cards:
            return
        card = AgentCard(name, provider, compact=True)
        self.agent_cards[name] = card
        # Insert before the trailing stretch, not after it.
        self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)
        self.refresh_cards_viewport()

    def refresh_cards_viewport(self) -> None:
        """Size the roster to at most `_VISIBLE_AGENT_CARDS`, then scroll.

        Measured from the tallest card rather than a constant, so a two-line
        description (and any font or DPI scaling) is never clipped. With fewer
        cards than the cap the panel shrinks to fit instead of padding.
        """
        cards = list(self.agent_cards.values())
        if not cards:
            self._cards_scroll.setFixedHeight(0)
            return
        shown = min(len(cards), _VISIBLE_AGENT_CARDS)
        width = max(1, self._cards_scroll.viewport().width()
                    - self._cards_layout.contentsMargins().left()
                    - self._cards_layout.contentsMargins().right())
        tallest = max(
            (c.heightForWidth(width) if c.sizePolicy().hasHeightForWidth() else 0)
            or c.sizeHint().height()
            for c in cards
        )
        margins = self._cards_layout.contentsMargins()
        self._cards_scroll.setFixedHeight(
            tallest * shown
            + self._cards_layout.spacing() * (shown - 1)
            + margins.top() + margins.bottom()
        )

    def resizeEvent(self, event) -> None:  # noqa: ANN001
        # Card height depends on wrapped text, so it changes with panel width.
        super().resizeEvent(event)
        self.refresh_cards_viewport()

    def current_path(self) -> str | None:
        return self.editor.current_path()

    def refresh_tree(self) -> None:
        """Force the file tree to re-read the workspace (after agent writes)."""
        self._fs_model.setRootPath("")
        self._fs_model.setRootPath(str(self.workspace))
        self.tree.setRootIndex(self._fs_model.index(str(self.workspace)))
