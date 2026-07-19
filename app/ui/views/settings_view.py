"""Settings view: [shared nav | settings categories | settings panels].

The API Configuration panel is **real** — it reads which provider keys are
present (masked) and Save writes them to `.env` via `config.update_env`. The
other categories are styled, honestly-labeled representative panels.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import config as app_config
from app.config import Config
from app.ui import theme
from app.ui.widgets import NavButton, NavSidebar, SectionHeader

_CATEGORIES = (
    ("api", "API Configuration"),
    ("general", "General Settings"),
    ("models", "AI Models"),
    ("mcp", "MCP Servers"),
    ("plugins", "Plugins & Extensions"),
    ("git", "Git & PRs"),
    ("plan", "Plan & Usage"),
)


class SettingsView(QWidget):
    view_requested = pyqtSignal(str)

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.nav = NavSidebar()
        self.nav.view_requested.connect(self.view_requested)
        root.addWidget(self.nav)

        self.cat_rail = self._build_category_rail()
        root.addWidget(self.cat_rail)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self._panels: dict[str, QWidget] = {}
        self._panels["api"] = self._build_api_panel()
        for key, label in _CATEGORIES:
            if key == "api":
                continue
            self._panels[key] = self._build_static_panel(label)
        for key, _ in _CATEGORIES:
            self.stack.addWidget(self._panels[key])

        self._select("api")

    # ----------------------------------------------------------- category rail
    def _build_category_rail(self) -> QWidget:
        rail = QFrame()
        rail.setObjectName("navSidebar")
        rail.setFixedWidth(240)
        v = QVBoxLayout(rail)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        head = QWidget()
        hb = QVBoxLayout(head)
        hb.setContentsMargins(16, 18, 16, 12)
        hb.setSpacing(2)
        who = QLabel("Nexus Identity")
        who.setStyleSheet(f"color:{theme.TEXT}; font-weight:600;")
        hb.addWidget(who)
        plan = QLabel("ENTERPRISE PLAN")
        plan.setProperty("caps", True)
        hb.addWidget(plan)
        v.addWidget(head)

        self._cat_buttons: dict[str, NavButton] = {}
        for key, label in _CATEGORIES:
            btn = NavButton("\u2022", label)
            btn.clicked.connect(lambda _=False, k=key: self._select(k))
            v.addWidget(btn)
            self._cat_buttons[key] = btn
        v.addStretch(1)
        return rail

    def _select(self, key: str) -> None:
        keys = [k for k, _ in _CATEGORIES]
        self.stack.setCurrentIndex(keys.index(key))
        for k, btn in self._cat_buttons.items():
            btn.set_active(k == key)

    # ------------------------------------------------------------- API panel
    def _build_api_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)
        scroll.setWidget(body)

        title = QLabel("API Configuration")
        title.setObjectName("h1")
        layout.addWidget(title)
        subtitle = QLabel("Provider keys are stored in .env. Leave a field blank to keep the current key.")
        subtitle.setProperty("muted", True)
        layout.addWidget(subtitle)

        card = QFrame()
        card.setObjectName("panelCard")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(24, 24, 24, 24)
        cv.setSpacing(18)

        self._fields: dict[str, QLineEdit] = {}
        specs = (
            ("OPENAI_API_KEY", "OpenAI API Key", self.config.openai_api_key),
            ("ANTHROPIC_API_KEY", "Anthropic API Key", self.config.anthropic_api_key),
            ("GEMINI_API_KEY", "Google API Key", self.config.gemini_api_key),
        )
        for env_key, label, current in specs:
            cv.addLayout(self._key_field(env_key, label, current))
        layout.addWidget(card)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setProperty("variant", "ghost")
        cancel.clicked.connect(self._reset_fields)
        save = QPushButton("\U0001f4be  Save Config")
        save.setProperty("variant", "primary")
        save.clicked.connect(self._save)
        actions.addWidget(cancel)
        actions.addWidget(save)
        layout.addLayout(actions)

        self._save_note = QLabel("")
        self._save_note.setProperty("muted", True)
        layout.addWidget(self._save_note)

        layout.addStretch(1)
        return scroll

    def _key_field(self, env_key: str, label: str, current: str):
        box = QVBoxLayout()
        box.setSpacing(6)
        header = QHBoxLayout()
        header.addWidget(SectionHeader(label))
        header.addStretch(1)
        status = QLabel("● Configured" if current else "○ Not set")
        status.setStyleSheet(
            f"color:{theme.OK if current else theme.TEXT_FAINT}; font-size:11px; font-weight:600;"
        )
        header.addWidget(status)
        box.addLayout(header)

        row = QHBoxLayout()
        row.setSpacing(6)
        field = QLineEdit()
        field.setEchoMode(QLineEdit.EchoMode.Password)
        field.setPlaceholderText(app_config.masked(current) or "Enter API key…")
        row.addWidget(field, 1)
        eye = QPushButton("\U0001f441")
        eye.setProperty("variant", "ghost")
        eye.setCheckable(True)
        eye.setFixedWidth(40)
        eye.toggled.connect(
            lambda on, f=field: f.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        row.addWidget(eye)
        box.addLayout(row)
        self._fields[env_key] = field
        return box

    def _reset_fields(self) -> None:
        for field in self._fields.values():
            field.clear()
        self._save_note.setText("Changes discarded.")

    def _save(self) -> None:
        values = {k: f.text().strip() for k, f in self._fields.items() if f.text().strip()}
        if not values:
            self._save_note.setText("No new keys entered — nothing to save.")
            return
        try:
            app_config.update_env(values)
        except OSError as exc:
            self._save_note.setStyleSheet(f"color:{theme.ERR};")
            self._save_note.setText(f"Failed to write .env: {exc}")
            return
        for field in self._fields.values():
            field.clear()
        self._save_note.setStyleSheet(f"color:{theme.OK};")
        self._save_note.setText(
            f"Saved {len(values)} key(s) to .env. Restart CombinePro to activate the connectors."
        )

    # ----------------------------------------------------------- static panels
    def _build_static_panel(self, label: str) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        scroll.setWidget(body)

        title = QLabel(label)
        title.setObjectName("h1")
        layout.addWidget(title)

        layout.addWidget(SectionHeader("Preferences"))
        rows = {
            "General Settings": [
                ("Editor Settings", "Configure font, formatting, minimap, and terminal behavior", "Open"),
                ("Keyboard Shortcuts", "Customize keybindings and hotkeys", "Edit"),
                ("Import from VS Code", "Sync extensions, settings, and workspace data", "Import"),
            ],
            "AI Models": [
                ("Default Model", "Model used for new agent domains", "Change"),
                ("Token Budget", "Per-wake skeleton + file byte caps", "Edit"),
            ],
            "MCP Servers": [("knbase Sidecar", "Local Delta Memory server (SIDECAR_URL)", "Open")],
            "Plugins & Extensions": [("Marketplace", "Browse and install extensions", "Browse")],
            "Git & PRs": [("Repository", "Link a Git remote and manage pull requests", "Connect")],
            "Plan & Usage": [("Enterprise Plan", "Seats, usage, and billing", "Manage")],
        }.get(label, [("Coming soon", "This section is representative in the UI shell.", "")])

        card = QFrame()
        card.setObjectName("panelCard")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        for i, (name, desc, action) in enumerate(rows):
            cv.addWidget(self._setting_row(name, desc, action, last=i == len(rows) - 1))
        layout.addWidget(card)

        note = QLabel("Representative panel — styled to the Obsidian Logic system; not yet wired.")
        note.setProperty("muted", True)
        layout.addWidget(note)
        layout.addStretch(1)
        return scroll

    def _setting_row(self, name: str, desc: str, action: str, last: bool) -> QWidget:
        row = QFrame()
        if not last:
            row.setStyleSheet(f"border-bottom:1px solid {theme.BORDER};")
        h = QHBoxLayout(row)
        h.setContentsMargins(20, 16, 20, 16)
        h.setSpacing(12)
        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel(name)
        title.setStyleSheet(f"color:{theme.TEXT}; font-weight:600; border:none;")
        text.addWidget(title)
        d = QLabel(desc)
        d.setStyleSheet(f"color:{theme.TEXT_MUTED}; border:none;")
        text.addWidget(d)
        h.addLayout(text, 1)
        if action:
            btn = QPushButton(action)
            btn.setProperty("variant", "ghost")
            btn.setEnabled(False)
            h.addWidget(btn, alignment=Qt.AlignmentFlag.AlignVCenter)
        return row
