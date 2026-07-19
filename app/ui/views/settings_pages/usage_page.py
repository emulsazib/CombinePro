"""Usage & Diagnostics: live session counters + environment facts."""
from __future__ import annotations

import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PyQt6.QtCore import QT_VERSION_STR
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.ui import theme
from app.ui.flow_layout import FlowLayout
from app.ui.views.settings_pages.common import SettingsPage, ghost, info_row
from app.ui.widgets import StatCard


@dataclass
class SessionStats:
    """Counters incremented by MainWindow as bus events arrive."""

    wakes: int = 0
    results_ok: int = 0
    results_failed: int = 0
    deltas: int = 0
    memory_writes: int = 0
    signals: int = 0
    domains: int = 0
    tokens_by_agent: dict[str, int] = field(default_factory=dict)

    def as_tiles(self) -> list[tuple[str, str, str | None]]:
        return [
            ("Agent Wakes", f"{self.wakes:02d}", theme.ACCENT_TINT),
            ("Results OK", f"{self.results_ok:02d}", theme.OK),
            ("Results Failed", f"{self.results_failed:02d}",
             theme.ERR if self.results_failed else None),
            ("File Deltas", f"{self.deltas:02d}", None),
            ("Memory Writes", f"{self.memory_writes:02d}", theme.TEAL),
            ("Cross-Domain", f"{self.signals:02d}", theme.SECONDARY),
        ]


class UsagePage(SettingsPage):
    title = "Usage & Diagnostics"
    subtitle = "Live counters for this session, plus the environment CombinePro is running in."

    def __init__(self, config, orchestrator, workspace: Path, stats: SessionStats) -> None:  # noqa: ANN001
        super().__init__()
        self.config = config
        self.orchestrator = orchestrator
        self.workspace = workspace
        self.stats = stats

        tiles_host = QWidget()
        self._tiles_layout = FlowLayout(tiles_host, spacing=12)
        self._tiles: dict[str, StatCard] = {}
        self.body.addWidget(tiles_host)

        env_label = QLabel("ENVIRONMENT")
        env_label.setProperty("caps", True)
        self.body.addWidget(env_label)
        self._env_card = self.add_card(padded=False)
        self._env_host = QWidget()
        self._env = QVBoxLayout(self._env_host)
        self._env.setContentsMargins(0, 0, 0, 0)
        self._env.setSpacing(0)
        self._env_card.addWidget(self._env_host)

        refresh = ghost("↻  Refresh")
        refresh.clicked.connect(self.refresh)
        self.add_actions(refresh)
        self.finish()
        self.refresh()

    def refresh(self) -> None:
        for title, value, color in self.stats.as_tiles():
            card = self._tiles.get(title)
            if card is None:
                card = StatCard(title, value, color)
                card.setFixedWidth(190)
                self._tiles[title] = card
                self._tiles_layout.addWidget(card)
            else:
                card.set_value(value)
        self._render_env()

    def _render_env(self) -> None:
        while self._env.count():
            item = self._env.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        agents = self.orchestrator.agents
        live = sum(1 for a in agents.values() if a.provider != "stub")
        rows = [
            ("Python", f"{platform.python_version()} ({sys.platform})", None),
            ("Qt / PyQt6", QT_VERSION_STR, None),
            ("Workspace", str(self.workspace), None),
            ("Sidecar", self.orchestrator.memory.base_url,
             theme.OK if self.orchestrator.memory_ok else theme.ERR),
            ("Agents", f"{len(agents)} registered · {live} live · {len(agents) - live} stub",
             None),
            ("Domains assigned", str(len(self.orchestrator.domain_map.assignments())), None),
            # Read the live components, not the construction-time Config, so
            # values edited on the AI Models page show through immediately.
            ("Skeleton cap", f"{self.orchestrator.skeletons.byte_cap:,} B", None),
            ("Max file size", f"{self.orchestrator.watcher.max_file_bytes:,} B", None),
            ("Router debounce", f"{self.orchestrator.router.debounce_seconds:g} s", None),
            ("Tree-sitter", self._grammar_status(), None),
        ]
        for i, (label, value, color) in enumerate(rows):
            self._env.addWidget(
                info_row(label, value, value_color=color, mono=True, last=i == len(rows) - 1)
            )

    @staticmethod
    def _grammar_status() -> str:
        try:
            from tree_sitter_language_pack import get_parser

            get_parser("python")
            return "available (python grammar loaded)"
        except Exception as exc:  # grammar/package missing
            return f"unavailable ({type(exc).__name__})"
