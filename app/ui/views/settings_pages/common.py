"""Shared scaffolding for the Settings pages.

`SettingsPage` gives every page the same scroll frame, heading block and card
vocabulary so the seven pages stay short and visually identical. All styling
comes from existing `theme.py` QSS hooks (`panelCard`, `h1`, `caps`, `muted`,
`variant`) — this module introduces no new styling system.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme


class SettingsPage(QScrollArea):
    """Scrollable settings page: title, optional subtitle, then stacked content."""

    title: str = "Settings"
    subtitle: str = ""

    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        body = QWidget()
        self.body = QVBoxLayout(body)
        self.body.setContentsMargins(32, 28, 32, 28)
        self.body.setSpacing(16)
        self.setWidget(body)

        heading = QLabel(self.title)
        heading.setObjectName("h1")
        self.body.addWidget(heading)
        if self.subtitle:
            sub = QLabel(self.subtitle)
            sub.setProperty("muted", True)
            sub.setWordWrap(True)
            self.body.addWidget(sub)

        self._status: QLabel | None = None

    # ------------------------------------------------------------- builders
    def add_card(self, *, padded: bool = True) -> QVBoxLayout:
        """Append a bordered card and return its layout."""
        card = QFrame()
        card.setObjectName("panelCard")
        layout = QVBoxLayout(card)
        margin = 20 if padded else 0
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(14 if padded else 0)
        self.body.addWidget(card)
        return layout

    def add_status_line(self) -> QLabel:
        """A single feedback line pages use to report save/test results."""
        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setProperty("muted", True)
        self.body.addWidget(self._status)
        return self._status

    def report(self, message: str, color: str | None = None) -> None:
        if self._status is None:
            return
        self._status.setStyleSheet(f"color:{color or theme.TEXT_MUTED};")
        self._status.setText(message)

    def add_actions(self, *buttons: QPushButton) -> None:
        row = QHBoxLayout()
        row.addStretch(1)
        for btn in buttons:
            row.addWidget(btn)
        self.body.addLayout(row)

    def finish(self) -> None:
        """Push content to the top (call at the end of every page __init__)."""
        self.body.addStretch(1)


# ------------------------------------------------------------------ widgets

def labeled_field(
    label: str,
    value: str = "",
    *,
    placeholder: str = "",
    mono: bool = True,
    secret: bool = False,
) -> tuple[QWidget, QLineEdit]:
    """A caps label over an input, optionally password-masked with a reveal eye."""
    wrap = QWidget()
    box = QVBoxLayout(wrap)
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(6)

    caption = QLabel(label.upper())
    caption.setProperty("caps", True)
    box.addWidget(caption)

    row = QHBoxLayout()
    row.setSpacing(6)
    field = QLineEdit(value)
    field.setPlaceholderText(placeholder)
    if mono:
        field.setFont(theme.mono_font(12))
    if secret:
        field.setEchoMode(QLineEdit.EchoMode.Password)
    row.addWidget(field, 1)

    if secret:
        eye = QPushButton("\U0001f441")
        eye.setProperty("variant", "ghost")
        eye.setCheckable(True)
        eye.setFixedWidth(40)
        eye.setToolTip("Show/hide")
        eye.toggled.connect(
            lambda on, f=field: f.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        row.addWidget(eye)
    box.addLayout(row)
    return wrap, field


def info_row(label: str, value: str, *, value_color: str | None = None,
             mono: bool = False, last: bool = False) -> QFrame:
    """A read-only label/value row used by the diagnostics and repo pages."""
    row = QFrame()
    if not last:
        row.setStyleSheet(f"border-bottom:1px solid {theme.BORDER};")
    h = QHBoxLayout(row)
    h.setContentsMargins(20, 12, 20, 12)
    h.setSpacing(16)

    name = QLabel(label)
    name.setStyleSheet(f"color:{theme.TEXT_MUTED}; border:none;")
    h.addWidget(name)
    h.addStretch(1)

    val = QLabel(value)
    val.setStyleSheet(f"color:{value_color or theme.TEXT}; border:none; font-weight:600;")
    if mono:
        val.setFont(theme.mono_font(12))
    val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    val.setWordWrap(True)
    h.addWidget(val)
    return row


def action_row(name: str, desc: str, button: QPushButton | None, *, last: bool = False) -> QFrame:
    """A titled row with a description and a trailing action button."""
    row = QFrame()
    if not last:
        row.setStyleSheet(f"border-bottom:1px solid {theme.BORDER};")
    h = QHBoxLayout(row)
    h.setContentsMargins(20, 14, 20, 14)
    h.setSpacing(12)

    text = QVBoxLayout()
    text.setSpacing(2)
    title = QLabel(name)
    title.setStyleSheet(f"color:{theme.TEXT}; font-weight:600; border:none;")
    text.addWidget(title)
    if desc:
        d = QLabel(desc)
        d.setWordWrap(True)
        d.setStyleSheet(f"color:{theme.TEXT_MUTED}; border:none;")
        text.addWidget(d)
    h.addLayout(text, 1)

    if button is not None:
        h.addWidget(button, alignment=Qt.AlignmentFlag.AlignVCenter)
    return row


def primary(text: str) -> QPushButton:
    # Escape '&' so Qt renders it literally instead of as a mnemonic accelerator.
    btn = QPushButton(text.replace("&", "&&"))
    btn.setProperty("variant", "primary")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


def ghost(text: str) -> QPushButton:
    btn = QPushButton(text.replace("&", "&&"))
    btn.setProperty("variant", "ghost")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn
