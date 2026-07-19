"""Memory & MCP: the knbase sidecar — URL, live health, connection test, log."""
from __future__ import annotations

import asyncio

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QPlainTextEdit

from app import config as app_config
from app.memory.knbase_client import SidecarError
from app.ui import theme
from app.ui.views.settings_pages.common import (
    SettingsPage,
    ghost,
    info_row,
    labeled_field,
    primary,
)
from app.ui.widgets import dot


class MemoryPage(SettingsPage):
    title = "Memory & MCP"
    subtitle = ("CombinePro's Delta Memory runs through the local knbase sidecar. Agents "
                "never share chat logs — each completed task writes a structural JSON "
                "summary here.")

    def __init__(self, config, orchestrator) -> None:  # noqa: ANN001
        super().__init__()
        self.config = config
        self.orchestrator = orchestrator

        card = self.add_card()
        wrap, self._url = labeled_field(
            "Sidecar URL", config.sidecar_url, placeholder="http://127.0.0.1:8787"
        )
        card.addWidget(wrap)

        self._health = QLabel()
        self._health.setTextFormat(Qt.TextFormat.RichText)
        card.addWidget(self._health)
        self.set_health(orchestrator.memory_ok, "" if orchestrator.memory_ok else "not connected")

        status_card = self.add_card(padded=False)
        self._rows_parent = status_card
        self._detail_rows: list = []
        status_card.addWidget(info_row("Project root", str(orchestrator.workspace), mono=True))
        self._state_row = info_row("Session state", "— (run Test Connection)", last=True)
        status_card.addWidget(self._state_row)

        log_label = QLabel("RECENT MEMORY LOG")
        log_label.setProperty("caps", True)
        self.body.addWidget(log_label)
        self._log = QPlainTextEdit()
        self._log.setObjectName("terminal")
        self._log.setReadOnly(True)
        self._log.setFont(theme.mono_font(11))
        self._log.setMinimumHeight(150)
        self._log.setPlaceholderText("Run Test Connection to load the latest knbase entries.")
        self.body.addWidget(self._log)

        save = ghost("Save URL")
        save.clicked.connect(self._save_url)
        test = primary("Test Connection")
        test.clicked.connect(self._test)
        self.add_actions(save, test)
        self.add_status_line()
        self.finish()

    # ------------------------------------------------------------------ health
    def set_health(self, healthy: bool, detail: str = "") -> None:
        color = theme.OK if healthy else theme.ERR
        label = "SIDECAR ONLINE" if healthy else "SIDECAR OFFLINE"
        self._health.setText(f'{dot(color, 9)}&nbsp; <span style="color:{color};">{label}</span>'
                             + (f' <span style="color:{theme.TEXT_MUTED};">— {detail}</span>'
                                if detail else ""))

    # ----------------------------------------------------------------- actions
    def _save_url(self) -> None:
        url = self._url.text().strip()
        if not url.startswith(("http://", "https://")):
            self.report("Sidecar URL must start with http:// or https://.", theme.ERR)
            return
        try:
            app_config.update_env({"SIDECAR_URL": url})
        except OSError as exc:
            self.report(f"Failed to write .env: {exc}", theme.ERR)
            return
        self.orchestrator.memory.set_base_url(url)
        self.report(f"Sidecar URL set to {url} and applied live.", theme.OK)

    def _test(self) -> None:
        try:
            asyncio.get_running_loop().create_task(self._test_async())
        except RuntimeError:
            self.report("No running event loop — start the app to test.", theme.ERR)

    async def _test_async(self) -> None:
        client = self.orchestrator.memory
        self.report("Testing…")
        try:
            await client.health()
        except SidecarError as exc:
            self.set_health(False, str(exc))
            self.report(f"Sidecar unreachable: {exc}", theme.ERR)
            return

        self.set_health(True, client.base_url)
        try:
            status = await client.status()
            state = status.get("state", "?")
            missing = status.get("missing") or []
            self._state_row.deleteLater()
            self._state_row = info_row(
                "Session state", f"{state}" + (f" · {len(missing)} governance file(s) missing"
                                               if missing else " · governance complete"),
                value_color=theme.OK if not missing else theme.WARN, last=True,
            )
            self._rows_parent.addWidget(self._state_row)
        except SidecarError as exc:
            self.report(f"Connected, but /status failed: {exc}", theme.WARN)
            return

        try:
            entries = await client.read_log(limit=12)
            self._log.clear()
            for entry in entries:
                ts = str(entry.get("ts", ""))[11:19]
                self._log.appendPlainText(
                    f"{ts}  {entry.get('event', '?'):<18} {entry.get('detail', '')}"
                )
        except SidecarError:
            pass
        self.report("Connection healthy — session and log loaded.", theme.OK)
