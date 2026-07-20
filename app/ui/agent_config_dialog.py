"""Per-agent configuration modal, opened by 'Configure' on a cluster card.

A focused form — name, provider, model version, role — as opposed to
`AddAgentDialog`, which onboards a brand-new agent with a full environment
grid. Styling deliberately mirrors that dialog so the two feel like one family.

`result()` is valid only after an accepted exec(); the caller applies the
changes (the dialog itself touches no runtime state).
"""
from __future__ import annotations

import re

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app.agents import providers, roles
from app.ui import feather, theme

_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


class AgentConfigDialog(QDialog):
    """Modal 'Configure Agent' form. Call `result()` after an accepted exec()."""

    def __init__(
        self,
        name: str,
        *,
        provider: str = "",
        model: str = "",
        role: str = "",
        existing: set[str] | None = None,
        locked_name: bool = False,
        parent=None,  # noqa: ANN001
    ) -> None:
        super().__init__(parent)
        self._original_name = name
        self._existing = {e.lower() for e in (existing or set())} - {name.lower()}
        self._locked_name = locked_name
        self._result: dict | None = None

        self.setWindowTitle(f"Configure — {name}")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setObjectName("agentDialog")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        title = QLabel("CONFIGURE AGENT")
        title.setProperty("caps", True)
        root.addWidget(title)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.name_edit = QLineEdit(name)
        if locked_name:
            self.name_edit.setReadOnly(True)
            self.name_edit.setToolTip(
                "Built-in agents are key-driven and cannot be renamed."
            )
        form.addRow(self._label("Agent Name"), self.name_edit)

        self.provider_combo = QComboBox()
        for spec in providers.PROVIDERS:
            self.provider_combo.addItem(spec.label, spec.id)
        self._select_data(self.provider_combo, provider)
        self.provider_combo.currentIndexChanged.connect(self._provider_changed)
        form.addRow(self._label("AI Model Name"), self.provider_combo)

        # Editable: the suggestions go stale faster than releases ship, so a
        # version we don't know about must still be typeable.
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setFont(theme.mono_font(12))
        form.addRow(self._label("AI Model Version"), self.model_combo)

        self.role_combo = QComboBox()
        self.role_combo.addItem("Unassigned", "")
        for role_id, role_label in roles.ROLES:
            self.role_combo.addItem(role_label, role_id)
        self._select_data(self.role_combo, roles.normalize(role))
        form.addRow(self._label("Agent Role"), self.role_combo)

        root.addLayout(form)

        self._hint = QLabel("")
        self._hint.setProperty("muted", True)
        self._hint.setWordWrap(True)
        root.addWidget(self._hint)

        self._error = QLabel("")
        self._error.setStyleSheet(f"color:{theme.ERR};")
        self._error.setWordWrap(True)
        self._error.hide()
        root.addWidget(self._error)

        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("  Cancel")
        cancel.setProperty("variant", "ghost")
        cancel.setIcon(feather.icon("x", theme.TEXT_MUTED, 15))
        cancel.setIconSize(feather.size_hint(15))
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        save = QPushButton("  Save")
        save.setProperty("variant", "primary")
        save.setIcon(feather.icon("save", theme.ON_ACCENT, 15))
        save.setIconSize(feather.size_hint(15))
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.clicked.connect(self._save)
        btns.addWidget(save)
        root.addLayout(btns)

        # Populate versions for the initial provider, preserving the current one.
        self._provider_changed(keep=model)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty("muted", True)
        return lbl

    @staticmethod
    def _select_data(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _provider_id(self) -> str:
        return str(self.provider_combo.currentData() or "")

    def _provider_changed(self, _index: int = 0, *, keep: str = "") -> None:
        """Repopulate the version list; keep a version the user already had."""
        current = keep or self.model_combo.currentText().strip()
        spec = providers.get(self._provider_id())
        self.model_combo.clear()
        if spec is not None:
            self.model_combo.addItems(spec.models)
        if current:
            self.model_combo.setEditText(current)
        elif spec is not None and spec.models:
            self.model_combo.setEditText(spec.models[0])

        if spec is None:
            self._hint.setText("")
        elif spec.kind == "local":
            self._hint.setText(
                f"Local provider — set {spec.env_key} on the agent (Add New Agent) "
                "to point it at your server."
            )
        else:
            self._hint.setText(
                f"Uses {spec.env_key} from API Configuration."
                + (f"  Endpoint: {spec.base_url}" if spec.base_url else "")
            )

    def _fail(self, message: str) -> None:
        self._error.setText(message)
        self._error.show()

    # --------------------------------------------------------------------- save
    def _save(self) -> None:
        self._error.hide()
        name = self.name_edit.text().strip().lower()
        if not _NAME_RE.match(name):
            return self._fail("Agent name must be 1–32 chars: letters, digits, '-' or '_', "
                              "starting with a letter.")
        if name in self._existing:
            return self._fail(f"An agent named '{name}' already exists.")
        model = self.model_combo.currentText().strip()
        if not model:
            return self._fail("Model version is required (e.g. gpt-5.1, glm-4.6).")

        self._result = {
            "name": name,
            "original_name": self._original_name,
            "provider": self._provider_id(),
            "model": model,
            "role": str(self.role_combo.currentData() or ""),
        }
        self.accept()

    def result(self) -> dict:
        if self._result is None:
            raise RuntimeError("result() is only valid after the dialog was accepted")
        return dict(self._result)
