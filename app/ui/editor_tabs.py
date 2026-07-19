"""Tabbed code editor: a QTabBar over a QStackedWidget of CodeViewers.

Opening a file from the tree adds (or re-selects) a tab keyed by its relative
path. When a watched file changes on disk (`FileDelta`), a dedicated **"Diff
View"** tab appears showing the unified diff beside a compact **AI Analysis**
panel populated from the matching `AgentResult`.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from app.core.events import AgentResult
from app.ui import theme
from app.ui.code_viewer import CodeViewer

_DIFF_KEY = "\x00diff"  # reserved key so it never collides with a real path


class EditorTabs(QWidget):
    file_saved = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._keys: list[str] = []
        self._base_titles: dict[int, str] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._bar = QTabBar()
        self._bar.setExpanding(False)
        self._bar.setTabsClosable(True)
        self._bar.setMovable(True)
        self._bar.setDrawBase(False)
        self._bar.currentChanged.connect(self._on_current_changed)
        self._bar.tabCloseRequested.connect(self._on_close)
        layout.addWidget(self._bar)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack, 1)

        self._placeholder = QLabel("Select a file from the Explorer to view its source.")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setProperty("muted", True)
        self._stack.addWidget(self._placeholder)

        self._diff_panel: _DiffPanel | None = None

    # ------------------------------------------------------------- public API

    def open_file(self, path: Path, rel_label: str) -> None:
        key = rel_label or str(path)
        if key in self._keys:
            self._select(key)
            viewer = self._stack.widget(self._stack_index(key))
            if isinstance(viewer, CodeViewer):
                viewer.show_file(path, rel_label=rel_label)
            return
        viewer = CodeViewer()
        viewer.show_file(path, rel_label=rel_label)
        title = Path(rel_label or path).name
        self._base_titles[id(viewer)] = title
        viewer.saved.connect(self.file_saved)
        viewer.dirty_changed.connect(lambda dirty, v=viewer: self._mark_dirty(v, dirty))
        self._add_tab(key, title, viewer)

    def _mark_dirty(self, viewer: QWidget, dirty: bool) -> None:
        stack_idx = self._stack.indexOf(viewer)
        if stack_idx <= 0:
            return
        tab_idx = stack_idx - 1
        base = self._base_titles.get(id(viewer), self._bar.tabText(tab_idx))
        self._bar.setTabText(tab_idx, f"\u25cf {base}" if dirty else base)

    def show_diff(self, rel_path: str, diff: str, analysis: AgentResult | None = None) -> None:
        if self._diff_panel is None:
            self._diff_panel = _DiffPanel()
            self._add_tab(_DIFF_KEY, "Diff View", self._diff_panel)
        else:
            self._select(_DIFF_KEY)
        self._diff_panel.show_diff(rel_path, diff, analysis)

    def set_diff_analysis(self, analysis: AgentResult) -> None:
        """Refresh the AI Analysis panel of an open Diff View (no diff reload)."""
        if self._diff_panel is not None:
            self._diff_panel.set_analysis(analysis)

    def current_viewer(self) -> CodeViewer | None:
        widget = self._stack.currentWidget()
        return widget if isinstance(widget, CodeViewer) else None

    def viewers(self) -> list[CodeViewer]:
        """Every open code viewer (used to apply the editor font size live)."""
        return [
            w for i in range(self._stack.count())
            if isinstance(w := self._stack.widget(i), CodeViewer)
        ]

    def current_path(self) -> str | None:
        idx = self._bar.currentIndex()
        if 0 <= idx < len(self._keys):
            key = self._keys[idx]
            return None if key == _DIFF_KEY else key
        return None

    # -------------------------------------------------------------- internals

    def _add_tab(self, key: str, title: str, widget: QWidget) -> None:
        self._stack.addWidget(widget)
        self._keys.append(key)
        idx = self._bar.addTab(title)
        self._bar.setCurrentIndex(idx)

    def _stack_index(self, key: str) -> int:
        # +1: index 0 of the stack is the placeholder.
        return self._keys.index(key) + 1

    def _select(self, key: str) -> None:
        self._bar.setCurrentIndex(self._keys.index(key))

    def _on_current_changed(self, index: int) -> None:
        if 0 <= index < len(self._keys):
            self._stack.setCurrentIndex(index + 1)
        else:
            self._stack.setCurrentIndex(0)

    def _on_close(self, index: int) -> None:
        if not (0 <= index < len(self._keys)):
            return
        key = self._keys.pop(index)
        widget = self._stack.widget(index + 1)
        if widget is not None:
            self._stack.removeWidget(widget)
            widget.deleteLater()
        if key == _DIFF_KEY:
            self._diff_panel = None
        self._bar.removeTab(index)
        if not self._keys:
            self._stack.setCurrentIndex(0)


class _DiffPanel(QWidget):
    """Unified-diff CodeViewer beside a compact AI Analysis side panel."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)
        self._header = QLabel("  \u270e  Changes detected")
        self._header.setObjectName("panelHeader")
        lv.addWidget(self._header)
        self._viewer = CodeViewer()
        lv.addWidget(self._viewer, 1)
        splitter.addWidget(left)

        self._analysis = _AiAnalysis()
        splitter.addWidget(self._analysis)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([620, 380])
        layout.addWidget(splitter)

    def show_diff(self, rel_path: str, diff: str, analysis: AgentResult | None) -> None:
        self._header.setText(f"  \u270e  {rel_path}  ·  Changes detected")
        self._viewer.show_diff(rel_path, diff)
        self._analysis.populate(analysis)

    def set_analysis(self, analysis: AgentResult) -> None:
        self._analysis.populate(analysis)


class _AiAnalysis(QScrollArea):
    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMinimumWidth(200)

        wrap = QWidget()
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QLabel("  \u25c6  AI Analysis")
        header.setObjectName("panelHeader")
        outer.addWidget(header)

        self._body = QWidget()
        self._layout = QVBoxLayout(self._body)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(14)
        outer.addWidget(self._body, 1)
        self.setWidget(wrap)

        self.populate(None)

    def populate(self, result: AgentResult | None) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        if result is None:
            hint = QLabel("No agent analysis yet for this change. When an agent "
                          "reviews the diff, its rationale appears here.")
            hint.setWordWrap(True)
            hint.setProperty("muted", True)
            self._layout.addWidget(hint)
            self._layout.addStretch(1)
            return

        self._layout.addWidget(self._section("Change Rationale"))
        rationale = QLabel(result.summary or result.error or "(no summary)")
        rationale.setWordWrap(True)
        rationale.setStyleSheet(f"color:{theme.TEXT_MUTED};")
        self._layout.addWidget(rationale)

        verified = QFrame()
        verified.setStyleSheet(
            f"background:{theme.ACCENT_SOFT}; border:1px solid {theme.BORDER};"
        )
        vv = QVBoxLayout(verified)
        vv.setContentsMargins(12, 10, 12, 10)
        vv.setSpacing(4)
        title = QLabel(
            f'<span style="color:{theme.OK}; font-weight:700;">&#10003; '
            f'{"Verified" if result.ok else "Attention"}</span>'
        )
        title.setTextFormat(Qt.TextFormat.RichText)
        vv.addWidget(title)
        changed = ", ".join(c.path for c in result.files_changed) or "no files reported"
        detail = QLabel(f"Agent: {result.agent_name} · files: {changed}")
        detail.setWordWrap(True)
        detail.setStyleSheet(f"color:{theme.TEXT_MUTED};")
        vv.addWidget(detail)
        self._layout.addWidget(verified)

        self._layout.addWidget(self._section("Suggested Next Steps"))
        steps = ["Run docstring validation", "Update unit tests in tests/"]
        if result.cross_domain is not None:
            steps.insert(0, f"Cross-domain: {result.cross_domain.request[:80]}")
        for i, step in enumerate(steps, 1):
            row = QLabel(f'<span style="color:{theme.SECONDARY};">{i}.</span> '
                         f'{step}')
            row.setTextFormat(Qt.TextFormat.RichText)
            row.setWordWrap(True)
            row.setStyleSheet(f"color:{theme.TEXT};")
            self._layout.addWidget(row)

        self._layout.addStretch(1)

    def _section(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color:{theme.TEXT}; font-size:14px; font-weight:600;")
        return lbl
