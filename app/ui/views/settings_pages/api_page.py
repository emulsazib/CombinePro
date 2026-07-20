"""API Configuration: provider keys, written to .env and applied live."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit

from app import config as app_config
from app.agents import providers
from app.ui import feather, theme
from app.ui.views.settings_pages.common import (
    SettingsPage,
    ghost,
    labeled_field,
    primary,
)


class ApiPage(SettingsPage):
    title = "API Configuration"
    subtitle = ("Provider keys are stored in .env. Each field shows the key currently in "
                "use — edit it to replace, or clear it to disable that provider. Saving "
                "reloads the connectors immediately, no restart needed.")

    def __init__(self, config, on_keys_saved) -> None:  # noqa: ANN001
        super().__init__()
        self.config = config
        self._on_keys_saved = on_keys_saved

        self._card = self.add_card()
        self._fields: dict[str, QLineEdit] = {}
        self._status_labels: dict[str, QLabel] = {}
        self._build_fields()

        cancel = ghost("Cancel", icon="x")
        cancel.clicked.connect(self._reset)
        save = primary("Save Config", icon="save")
        save.clicked.connect(self._save)
        self.add_actions(cancel, save)
        self.add_status_line()
        self.finish()

    # ------------------------------------------------------------------ build
    def _build_fields(self) -> None:
        for spec in providers.KEYED:
            current = self._current(spec.env_key)
            # Populate with the real key rather than a masked placeholder: the
            # reveal toggle has nothing to reveal on an empty field, which is
            # what made "Show" look broken.
            wrap, field = labeled_field(
                f"{spec.label} API Key", current,
                placeholder="Enter API key…", secret=True,
            )
            status = QLabel()
            head = QHBoxLayout()
            head.addStretch(1)
            head.addWidget(status)
            self._card.addWidget(wrap)
            self._card.addLayout(head)
            self._fields[spec.env_key] = field
            self._status_labels[spec.env_key] = status
            self._set_status(spec.env_key, bool(current))

    def _current(self, env_key: str) -> str:
        """The key in force right now, from the live Config."""
        attr = _CONFIG_ATTR.get(env_key, "")
        return str(getattr(self.config, attr, "") or "") if attr else ""

    def _set_status(self, env_key: str, configured: bool) -> None:
        label = self._status_labels[env_key]
        tint = theme.OK if configured else theme.TEXT_FAINT
        glyph = feather.label_html("check-circle" if configured else "circle", tint, 12)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setText(
            f'{glyph}&nbsp;&nbsp;<span style="color:{tint}; font-size:11px; '
            f'font-weight:600;">{"Configured" if configured else "Not set"}</span>'
        )

    # ---------------------------------------------------------------- actions
    def refresh(self) -> None:
        """Re-read every field from the live Config (after an external change)."""
        for env_key, field in self._fields.items():
            current = self._current(env_key)
            field.setText(current)
            self._set_status(env_key, bool(current))

    def _reset(self) -> None:
        self.refresh()
        self.report("Changes discarded.")

    def _save(self) -> None:
        # Include cleared fields: writing a blank is how a provider gets
        # disabled (the loader treats "" as no key and falls back to a stub).
        values = {
            env_key: field.text().strip()
            for env_key, field in self._fields.items()
            if field.text().strip() != self._current(env_key)
        }
        if not values:
            self.report("No changes to save.", theme.WARN)
            return
        try:
            app_config.update_env(values)
        except OSError as exc:
            self.report(f"Failed to write .env: {exc}", theme.ERR)
            return

        names = self._on_keys_saved()  # rebuilds Config and pushes it to self.config
        self.refresh()
        cleared = [k for k, v in values.items() if not v]
        detail = f"Saved {len(values) - len(cleared)} key(s)"
        if cleared:
            detail += f", cleared {len(cleared)}"
        self.report(f"{detail}. Connectors reloaded: {', '.join(names)}.", theme.OK)


# env var -> Config attribute / provider id, kept next to the registry it mirrors.
_CONFIG_ATTR = {
    "ANTHROPIC_API_KEY": "anthropic_api_key",
    "OPENAI_API_KEY": "openai_api_key",
    "GEMINI_API_KEY": "gemini_api_key",
    "KIMI_API_KEY": "kimi_api_key",
    "GLM_API_KEY": "glm_api_key",
}
