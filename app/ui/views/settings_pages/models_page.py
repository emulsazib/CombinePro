"""AI Models: per-provider model IDs + token-optimization knobs, applied live."""
from __future__ import annotations

from PyQt6.QtWidgets import QDoubleSpinBox, QHBoxLayout, QLabel, QSpinBox, QWidget

from app import config as app_config
from app.ui import theme
from app.ui.views.settings_pages.common import (
    SettingsPage,
    ghost,
    labeled_field,
    primary,
)

_MODELS = (
    ("CLAUDE_MODEL", "Claude model", "claude_model"),
    ("OPENAI_MODEL", "OpenAI model", "openai_model"),
    ("GEMINI_MODEL", "Gemini model", "gemini_model"),
)


class ModelsPage(SettingsPage):
    title = "AI Models"
    subtitle = ("Model IDs per provider and the token-optimization knobs that bound every "
                "agent wake. Saving writes .env and applies to the running orchestrator.")

    def __init__(self, config, on_models_saved, on_knobs_saved) -> None:  # noqa: ANN001
        super().__init__()
        self.config = config
        self._on_models_saved = on_models_saved
        self._on_knobs_saved = on_knobs_saved

        card = self.add_card()
        self._fields = {}
        for env_key, label, attr in _MODELS:
            wrap, field = labeled_field(label, getattr(config, attr, ""))
            card.addWidget(wrap)
            self._fields[env_key] = field

        knobs = self.add_card()
        header = QLabel("TOKEN OPTIMIZATION")
        header.setProperty("caps", True)
        knobs.addWidget(header)

        self._skeleton = QSpinBox()
        self._skeleton.setRange(2_000, 200_000)
        self._skeleton.setSingleStep(1_000)
        self._skeleton.setSuffix(" B")
        self._skeleton.setValue(config.skeleton_byte_cap)
        knobs.addWidget(self._knob_row(
            "AST skeleton cap",
            "Max bytes of domain skeleton sent with each wake.",
            self._skeleton,
        ))

        self._max_file = QSpinBox()
        self._max_file.setRange(16_000, 8_000_000)
        self._max_file.setSingleStep(16_000)
        self._max_file.setSuffix(" B")
        self._max_file.setValue(config.max_file_bytes)
        knobs.addWidget(self._knob_row(
            "Max file size",
            "Files larger than this are skipped by the watcher and skeleton builder.",
            self._max_file,
        ))

        self._debounce = QDoubleSpinBox()
        self._debounce.setRange(0.1, 30.0)
        self._debounce.setSingleStep(0.5)
        self._debounce.setDecimals(1)
        self._debounce.setSuffix(" s")
        self._debounce.setValue(config.debounce_seconds)
        knobs.addWidget(self._knob_row(
            "Router debounce",
            "Rapid edits to one file coalesce into a single agent wake.",
            self._debounce,
        ))

        revert = ghost("Revert")
        revert.clicked.connect(self._revert)
        save = primary("\U0001f4be  Save & Apply")
        save.clicked.connect(self._save)
        self.add_actions(revert, save)
        self.add_status_line()
        self.finish()

    def _knob_row(self, name: str, desc: str, control: QWidget) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(16)
        text = QLabel(f"<b>{name}</b><br><span style='color:{theme.TEXT_MUTED};'>{desc}</span>")
        text.setWordWrap(True)
        h.addWidget(text, 1)
        control.setFixedWidth(150)
        h.addWidget(control)
        return row

    def _revert(self) -> None:
        for env_key, _label, attr in _MODELS:
            self._fields[env_key].setText(getattr(self.config, attr, ""))
        self._skeleton.setValue(self.config.skeleton_byte_cap)
        self._max_file.setValue(self.config.max_file_bytes)
        self._debounce.setValue(self.config.debounce_seconds)
        self.report("Reverted to the loaded configuration.")

    def _save(self) -> None:
        values = {k: f.text().strip() for k, f in self._fields.items() if f.text().strip()}
        values["SKELETON_BYTE_CAP"] = str(self._skeleton.value())
        values["MAX_FILE_BYTES"] = str(self._max_file.value())
        values["DEBOUNCE_SECONDS"] = str(self._debounce.value())
        try:
            app_config.update_env(values)
        except OSError as exc:
            self.report(f"Failed to write .env: {exc}", theme.ERR)
            return
        self._on_knobs_saved()
        names = self._on_models_saved()
        self.report(
            f"Applied live — debounce {self._debounce.value()}s, skeleton cap "
            f"{self._skeleton.value():,}B. Connectors reloaded: {', '.join(names)}.",
            theme.OK,
        )
