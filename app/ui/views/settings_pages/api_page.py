"""API Configuration: provider keys, written to .env and applied live."""
from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit

from app import config as app_config
from app.ui import theme
from app.ui.views.settings_pages.common import (
    SettingsPage,
    ghost,
    labeled_field,
    primary,
)

_SPECS = (
    ("OPENAI_API_KEY", "OpenAI API Key", "openai_api_key"),
    ("ANTHROPIC_API_KEY", "Anthropic API Key", "anthropic_api_key"),
    ("GEMINI_API_KEY", "Google API Key", "gemini_api_key"),
)


class ApiPage(SettingsPage):
    title = "API Configuration"
    subtitle = ("Provider keys are stored in .env. Leave a field blank to keep the current "
                "key. Saving reloads the connectors immediately — no restart needed.")

    def __init__(self, config, on_keys_saved) -> None:  # noqa: ANN001
        super().__init__()
        self.config = config
        self._on_keys_saved = on_keys_saved

        card = self.add_card()
        self._fields: dict[str, QLineEdit] = {}
        for env_key, label, attr in _SPECS:
            current = getattr(config, attr, "")
            wrap, field = labeled_field(
                label, placeholder=app_config.masked(current) or "Enter API key…", secret=True
            )
            status = QLabel("● Configured" if current else "○ Not set")
            status.setStyleSheet(
                f"color:{theme.OK if current else theme.TEXT_FAINT}; "
                f"font-size:11px; font-weight:600;"
            )
            head = QHBoxLayout()
            head.addStretch(1)
            head.addWidget(status)
            card.addWidget(wrap)
            card.addLayout(head)
            self._fields[env_key] = field
            self._status_labels = getattr(self, "_status_labels", {})
            self._status_labels[env_key] = status

        cancel = ghost("Cancel")
        cancel.clicked.connect(self._reset)
        save = primary("\U0001f4be  Save Config")
        save.clicked.connect(self._save)
        self.add_actions(cancel, save)
        self.add_status_line()
        self.finish()

    def _reset(self) -> None:
        for field in self._fields.values():
            field.clear()
        self.report("Changes discarded.")

    def _save(self) -> None:
        values = {k: f.text().strip() for k, f in self._fields.items() if f.text().strip()}
        if not values:
            self.report("No new keys entered — nothing to save.", theme.WARN)
            return
        try:
            app_config.update_env(values)
        except OSError as exc:
            self.report(f"Failed to write .env: {exc}", theme.ERR)
            return
        for field in self._fields.values():
            field.clear()
        for env_key, status in getattr(self, "_status_labels", {}).items():
            if env_key in values:
                status.setText("● Configured")
                status.setStyleSheet(f"color:{theme.OK}; font-size:11px; font-weight:600;")
        names = self._on_keys_saved()
        self.report(
            f"Saved {len(values)} key(s) and reloaded connectors: {', '.join(names)}.",
            theme.OK,
        )
