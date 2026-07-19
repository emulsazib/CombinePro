"""Dynamic agent onboarding: the 'Add New Agent' configuration dialog.

Commercial (OpenAI / Anthropic / Gemini) or Local (Ollama / vLLM / custom
OpenAI-compatible) agent types, each with a dynamic, scrollable key-value grid
of environment-style configuration rows. Values that look sensitive are masked
(`QLineEdit.EchoMode.Password`) with a per-row reveal toggle. Pasting a full
`KEY=value` string into either field is split gracefully. 'Save Agent'
validates everything and exposes a clean `profile()` dict for the orchestrator.
"""
from __future__ import annotations

import re

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme

# (label, provider id, kind)
AGENT_TYPES: tuple[tuple[str, str, str], ...] = (
    ("Commercial — OpenAI", "openai", "commercial"),
    ("Commercial — Anthropic (Claude)", "anthropic", "commercial"),
    ("Commercial — Google (Gemini)", "gemini", "commercial"),
    ("Local — Ollama", "ollama", "local"),
    ("Local — vLLM", "vllm", "local"),
    ("Local — Custom (OpenAI-compatible)", "custom", "local"),
)

# Suggested model + starter env rows per provider.
TYPE_DEFAULTS: dict[str, tuple[str, tuple[tuple[str, str], ...]]] = {
    "openai": ("gpt-5.1", (("OPENAI_API_KEY", ""),)),
    "anthropic": ("claude-opus-4-8", (("ANTHROPIC_API_KEY", ""),)),
    "gemini": ("gemini-2.5-pro", (("GEMINI_API_KEY", ""),)),
    "ollama": ("llama3.1", (("LOCAL_BASE_URL", "http://localhost:11434/v1"), ("LOCAL_API_KEY", "ollama"))),
    "vllm": ("meta-llama/Llama-3.1-8B-Instruct", (("LOCAL_BASE_URL", "http://localhost:8000/v1"), ("LOCAL_API_KEY", ""))),
    "custom": ("", (("LOCAL_BASE_URL", ""), ("LOCAL_API_KEY", ""))),
}

# The one env key each provider cannot work without.
REQUIRED_KEY: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "ollama": "LOCAL_BASE_URL",
    "vllm": "LOCAL_BASE_URL",
    "custom": "LOCAL_BASE_URL",
}

_ENV_KEY_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_SENSITIVE = ("KEY", "TOKEN", "SECRET", "PASS", "CREDENTIAL")


def _is_sensitive(key: str) -> bool:
    upper = key.upper()
    return any(marker in upper for marker in _SENSITIVE)


class _KVRow:
    """One row of the config grid: key + (maskable) value + reveal + remove."""

    def __init__(self, dialog: "AddAgentDialog", key: str = "", value: str = "") -> None:
        self._dialog = dialog
        self.key_edit = QLineEdit(key)
        self.key_edit.setPlaceholderText("ENV_VAR_NAME")
        self.key_edit.setFont(theme.mono_font(12))
        self.key_edit.editingFinished.connect(self._normalize)

        self.value_edit = QLineEdit(value)
        self.value_edit.setPlaceholderText("value")
        self.value_edit.setFont(theme.mono_font(12))
        self.value_edit.editingFinished.connect(self._normalize)

        self.reveal = QPushButton("◉")
        self.reveal.setProperty("variant", "ghost")
        self.reveal.setFixedWidth(34)
        self.reveal.setCheckable(True)
        self.reveal.setToolTip("Show/hide the value")
        self.reveal.toggled.connect(self._apply_echo)

        self.remove = QPushButton("✕")
        self.remove.setProperty("variant", "ghost")
        self.remove.setFixedWidth(34)
        self.remove.setToolTip("Remove this row")
        self.remove.clicked.connect(lambda: dialog._remove_row(self))

        self._apply_echo()

    def _normalize(self) -> None:
        """Accept pasted `KEY=value` in either field; uppercase the key."""
        key_text = self.key_edit.text().strip()
        if "=" in key_text:
            key, _, val = key_text.partition("=")
            self.key_edit.setText(key.strip().upper())
            if val.strip() and not self.value_edit.text().strip():
                self.value_edit.setText(val.strip())
        else:
            self.key_edit.setText(key_text.upper())

        val_text = self.value_edit.text().strip()
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", val_text)
        if m and not self.key_edit.text().strip():
            self.key_edit.setText(m.group(1).upper())
            self.value_edit.setText(m.group(2).strip())
        self._apply_echo()

    def _apply_echo(self, *_args) -> None:
        masked = _is_sensitive(self.key_edit.text()) and not self.reveal.isChecked()
        self.value_edit.setEchoMode(
            QLineEdit.EchoMode.Password if masked else QLineEdit.EchoMode.Normal
        )
        self.reveal.setVisible(_is_sensitive(self.key_edit.text()))

    def widgets(self) -> tuple[QWidget, ...]:
        return (self.key_edit, self.value_edit, self.reveal, self.remove)

    def data(self) -> tuple[str, str]:
        # Re-run normalization so unfocused edits still split KEY=value.
        self._normalize()
        return self.key_edit.text().strip(), self.value_edit.text().strip()


class AddAgentDialog(QDialog):
    """Modal 'Add New Agent' form. Call `profile()` after an accepted exec()."""

    def __init__(self, existing: set[str], parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._existing = {e.lower() for e in existing}
        self._rows: list[_KVRow] = []
        self._profile: dict | None = None

        self.setWindowTitle("Add New Agent")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setObjectName("agentDialog")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        title = QLabel("ADD NEW AGENT")
        title.setProperty("caps", True)
        root.addWidget(title)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        form.addWidget(self._label("Agent name"), 0, 0)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. ollama-local, reviewer, codex-2")
        form.addWidget(self.name_edit, 0, 1)

        form.addWidget(self._label("Agent type"), 1, 0)
        self.type_combo = QComboBox()
        for label, _provider, _kind in AGENT_TYPES:
            self.type_combo.addItem(label)
        self.type_combo.currentIndexChanged.connect(self._type_changed)
        form.addWidget(self.type_combo, 1, 1)

        form.addWidget(self._label("Model"), 2, 0)
        self.model_edit = QLineEdit()
        self.model_edit.setFont(theme.mono_font(12))
        form.addWidget(self.model_edit, 2, 1)
        form.setColumnStretch(1, 1)
        root.addLayout(form)

        env_head = QHBoxLayout()
        env_label = QLabel("ENVIRONMENT CONFIGURATION")
        env_label.setProperty("caps", True)
        env_head.addWidget(env_label)
        env_head.addStretch(1)
        add_row = QPushButton("+ Add Row")
        add_row.setProperty("variant", "ghost")
        add_row.clicked.connect(lambda: self._add_row())
        env_head.addWidget(add_row)
        root.addLayout(env_head)

        hint = QLabel("Rows accept KEY=value pastes (e.g. OPENAI_API_KEY=sk-proj-…). "
                      "Sensitive values are masked.")
        hint.setProperty("muted", True)
        hint.setWordWrap(True)
        root.addWidget(hint)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setMinimumHeight(150)
        self._scroll.setMaximumHeight(260)
        grid_host = QWidget()
        self._grid = QGridLayout(grid_host)
        self._grid.setContentsMargins(0, 0, 8, 0)
        self._grid.setHorizontalSpacing(8)
        self._grid.setVerticalSpacing(8)
        self._grid.setColumnStretch(0, 2)
        self._grid.setColumnStretch(1, 3)
        outer = QWidget()
        ov = QVBoxLayout(outer)
        ov.setContentsMargins(0, 0, 0, 0)
        ov.addWidget(grid_host)
        ov.addStretch(1)
        self._scroll.setWidget(outer)
        root.addWidget(self._scroll, 1)

        self._error = QLabel("")
        self._error.setStyleSheet(f"color:{theme.ERR};")
        self._error.setWordWrap(True)
        self._error.hide()
        root.addWidget(self._error)

        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setProperty("variant", "ghost")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        save = QPushButton("Save Agent")
        save.setProperty("variant", "primary")
        save.clicked.connect(self._save)
        btns.addWidget(save)
        root.addLayout(btns)

        self._type_changed(0)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty("muted", True)
        return lbl

    def _current_type(self) -> tuple[str, str]:
        _label, provider, kind = AGENT_TYPES[self.type_combo.currentIndex()]
        return provider, kind

    # ---------------------------------------------------------------- grid ops
    def _type_changed(self, _index: int) -> None:
        provider, _kind = self._current_type()
        model, env_rows = TYPE_DEFAULTS[provider]
        self.model_edit.setText(model)
        self._clear_rows()
        for key, value in env_rows:
            self._add_row(key, value)

    def _add_row(self, key: str = "", value: str = "") -> None:
        row = _KVRow(self, key, value)
        self._rows.append(row)
        r = self._grid.rowCount()
        for col, widget in enumerate(row.widgets()):
            self._grid.addWidget(widget, r, col)
        row.key_edit.setFocus()

    def _remove_row(self, row: _KVRow) -> None:
        if row not in self._rows:
            return
        self._rows.remove(row)
        for widget in row.widgets():
            self._grid.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()

    def _clear_rows(self) -> None:
        for row in list(self._rows):
            self._remove_row(row)

    # ------------------------------------------------------------------- save
    def _fail(self, message: str) -> None:
        self._error.setText(message)
        self._error.show()

    def _save(self) -> None:
        self._error.hide()
        provider, kind = self._current_type()

        name = self.name_edit.text().strip().lower()
        if not _NAME_RE.match(name):
            return self._fail("Agent name must be 1–32 chars: letters, digits, '-' or '_', "
                              "starting with a letter.")
        if name in self._existing:
            return self._fail(f"An agent named '{name}' already exists.")

        model = self.model_edit.text().strip()
        if not model:
            return self._fail("Model is required (e.g. gpt-5.1, llama3.1).")

        env: dict[str, str] = {}
        for row in self._rows:
            key, value = row.data()
            if not key and not value:
                continue  # ignore fully empty rows
            if not _ENV_KEY_RE.match(key):
                return self._fail(f"Invalid variable name '{key or '(empty)'}' — use "
                                  "UPPER_SNAKE_CASE (letters, digits, underscores).")
            if key in env:
                return self._fail(f"Duplicate variable '{key}'.")
            env[key] = value

        required = REQUIRED_KEY[provider]
        if not env.get(required):
            return self._fail(f"'{required}' is required for this agent type.")
        if kind == "local":
            url = env.get("LOCAL_BASE_URL", "")
            if not re.match(r"^https?://", url):
                return self._fail("LOCAL_BASE_URL must be an http(s) URL "
                                  "(e.g. http://localhost:11434/v1).")

        self._profile = {
            "name": name,
            "kind": kind,
            "provider": provider,
            "model": model,
            "env": env,
        }
        self.accept()

    def profile(self) -> dict:
        if self._profile is None:
            raise RuntimeError("profile() is only valid after the dialog was accepted")
        return dict(self._profile)
