"""General: workspace folder (restart-scoped) and editor font size (live)."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QFileDialog, QSpinBox

from app import config as app_config
from app.ui import theme
from app.ui.views.settings_pages.common import (
    SettingsPage,
    action_row,
    ghost,
    info_row,
    primary,
)


class GeneralPage(SettingsPage):
    title = "General"
    subtitle = "Workspace and editor preferences."

    def __init__(self, config, workspace: Path, on_font_size) -> None:  # noqa: ANN001
        super().__init__()
        self.config = config
        self.workspace = workspace
        self._on_font_size = on_font_size

        # --- workspace -------------------------------------------------------
        ws_card = self.add_card(padded=False)
        browse = ghost("Change…")
        browse.clicked.connect(self._choose_workspace)
        ws_card.addWidget(action_row(
            "Workspace folder",
            "Root the file tree, watcher and agent domains are scoped to. "
            "Changing it takes effect after a restart.",
            browse,
        ))
        self._ws_row = info_row("Current", str(workspace), mono=True, last=True)
        ws_card.addWidget(self._ws_row)

        # --- editor ----------------------------------------------------------
        font_card = self.add_card()
        self._font = QSpinBox()
        self._font.setRange(9, 24)
        self._font.setSuffix(" px")
        self._font.setValue(getattr(config, "editor_font_size", 13))
        self._font.setFixedWidth(120)
        font_card.addWidget(action_row(
            "Editor font size",
            "Applies immediately to open code viewers and the system terminal.",
            None, last=True,
        ))
        font_card.addWidget(self._font)

        apply_btn = primary("Apply")
        apply_btn.clicked.connect(self._apply)
        self.add_actions(apply_btn)
        self.add_status_line()
        self.finish()

    def _choose_workspace(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose a workspace folder", str(self.workspace)
        )
        if not chosen:
            return
        try:
            app_config.update_env({"COMBINEPRO_WORKSPACE": chosen})
        except OSError as exc:
            self.report(f"Failed to write .env: {exc}", theme.ERR)
            return
        QSettings("CombinePro", "CombinePro").setValue("workspace", chosen)
        self._ws_row.deleteLater()
        self.report(
            f"Workspace set to {chosen}. Restart CombinePro to load it.", theme.WARN
        )

    def _apply(self) -> None:
        size = self._font.value()
        try:
            app_config.update_env({"EDITOR_FONT_SIZE": str(size)})
        except OSError as exc:
            self.report(f"Failed to write .env: {exc}", theme.ERR)
            return
        self._on_font_size(size)
        self.report(f"Editor font size set to {size}px and applied.", theme.OK)
