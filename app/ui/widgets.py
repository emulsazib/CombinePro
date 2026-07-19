"""Presentational widgets for the Obsidian Logic dashboard.

Everything here is styled by tokens in `theme.py` and driven by the main window
in response to bus events — the widgets hold no orchestration logic themselves.
"""
from __future__ import annotations

import html
import os
from pathlib import Path

from PyQt6.QtCore import QProcess, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme


def dot(color: str, size: int = 10) -> str:
    """Inline HTML for a colored status dot (rendered inside a rich-text QLabel)."""
    return f'<span style="font-size:{size}px; color:{color};">&#9679;</span>'


# --------------------------------------------------------------------- badges

class StateBadge(QLabel):
    """Caps label + glowing dot reflecting a live agent state.

    States: ACTIVE (green), RUNNING (blue), IDLE (gray), ERROR (red).
    """

    def __init__(self, state: str = "IDLE") -> None:
        super().__init__()
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.set_state(state)

    def set_state(self, state: str) -> None:
        state = (state or "IDLE").upper()
        self._state = state
        color = theme.state_color(state)
        self.setText(
            f'{dot(color, 9)}&nbsp;'
            f'<span style="color:{color}; font-size:10px; font-weight:700; '
            f'letter-spacing:0.05em;">{html.escape(state)}</span>'
        )

    @property
    def state(self) -> str:
        return self._state


class SectionHeader(QLabel):
    """Caps-label section header (e.g. 'ACCOUNT MANAGEMENT')."""

    def __init__(self, text: str) -> None:
        super().__init__(text.upper())
        self.setProperty("caps", True)


# --------------------------------------------------------------------- nav

class NavButton(QPushButton):
    """Left-sidebar navigation entry: icon glyph + label, checkable/active."""

    def __init__(self, glyph: str, label: str) -> None:
        # Escape '&' so Qt doesn't treat it as a mnemonic accelerator.
        super().__init__(f"  {glyph}   {label}".replace("&", "&&"))
        self.setCheckable(True)
        self.setProperty("nav", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_active(self, active: bool) -> None:
        self.setChecked(active)
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)


class NavSidebar(QFrame):
    """Shared left navigation rail: brand header, primary nav, bottom links.

    Emits `view_requested(name)` where name ∈ {'explorer', 'agents', 'settings'}.
    Each stacked view owns its own instance; the main window keeps them in sync.
    """

    view_requested = pyqtSignal(str)

    NAV = (
        ("explorer", "\u25a6", "Explorer"),
        ("agents", "\u25c8", "Agents"),
        ("settings", "\u2699", "Settings"),
    )

    def __init__(self, version: str = "v1.0.4") -> None:
        super().__init__()
        self.setObjectName("navSidebar")
        self.setFixedWidth(240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        brand_box = QWidget()
        bb = QVBoxLayout(brand_box)
        bb.setContentsMargins(20, 20, 20, 20)
        bb.setSpacing(2)
        brand = QLabel("CombinePro")
        brand.setObjectName("navBrand")
        bb.addWidget(brand)
        ver = QLabel(version)
        ver.setObjectName("navVersion")
        bb.addWidget(ver)
        layout.addWidget(brand_box)

        layout.addWidget(_hline())
        layout.addSpacing(8)

        self._buttons: dict[str, NavButton] = {}
        for key, glyph, label in self.NAV:
            btn = NavButton(glyph, label)
            btn.clicked.connect(lambda _=False, k=key: self.view_requested.emit(k))
            layout.addWidget(btn)
            self._buttons[key] = btn

        self._layout = layout
        self._fill_index = layout.count()
        layout.addStretch(1)
        layout.addWidget(_hline())
        help_btn = NavButton("\u2139", "Help")
        help_btn.setCheckable(False)
        layout.addWidget(help_btn)
        layout.addSpacing(8)

    def set_fill(self, widget: QWidget) -> None:
        """Replace the empty stretch with a widget (the Explorer file tree)."""
        stretch = self._layout.takeAt(self._fill_index)
        del stretch
        self._layout.insertWidget(self._fill_index, widget, 1)

    def set_active(self, name: str) -> None:
        for key, btn in self._buttons.items():
            btn.set_active(key == name)


def _hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(f"background:{theme.BORDER}; max-height:1px; border:none;")
    line.setFixedHeight(1)
    return line


# --------------------------------------------------------------------- cards

class StatCard(QFrame):
    """A metric tile: caps title over a large value (optionally colored)."""

    def __init__(self, title: str, value: str, value_color: str | None = None) -> None:
        super().__init__()
        self.setObjectName("statCard")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        self._title = QLabel(title.upper())
        self._title.setProperty("caps", True)
        layout.addWidget(self._title)

        self._value = QLabel(value)
        self._value.setObjectName("statValue")
        if value_color:
            self._value.setStyleSheet(f"color:{value_color};")
        layout.addWidget(self._value)

    def set_value(self, value: str) -> None:
        self._value.setText(value)


class AgentCard(QFrame):
    """One agent tile. Two layouts:

    - compact=True  → side-panel cluster card (name, badge, description, progress)
    - compact=False → cluster-grid card (icon, badge, name, domain chip, provider,
      latency, success rate, Configure / Deactivate).
    """

    configure_clicked = pyqtSignal(str)
    toggle_clicked = pyqtSignal(str)

    def __init__(
        self,
        name: str,
        provider: str,
        *,
        compact: bool = False,
        domain: str = "",
        state: str = "IDLE",
    ) -> None:
        super().__init__()
        self.setObjectName("agentCard")
        self.name = name
        self._compact = compact
        self._color = theme.agent_color(name)

        if compact:
            self._build_compact(name, provider, state)
        else:
            self._build_full(name, provider, domain, state)

    # -------------------------------------------------------------- compact
    def _build_compact(self, name: str, provider: str, state: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)
        name_lbl = QLabel(f'{dot(self._color, 11)}&nbsp; {html.escape(name)}')
        name_lbl.setTextFormat(Qt.TextFormat.RichText)
        name_lbl.setObjectName("agentName")
        top.addWidget(name_lbl)
        top.addStretch(1)
        self._badge = StateBadge(state)
        top.addWidget(self._badge)
        layout.addLayout(top)

        self._desc = QLabel("Dormant — awaiting a task.")
        self._desc.setWordWrap(True)
        self._desc.setProperty("muted", True)
        layout.addWidget(self._desc)

        self._progress = QProgressBar()
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(4)
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.setStyleSheet(
            f"QProgressBar {{ background:{theme.BG_HIGH}; border:none; }}"
            f"QProgressBar::chunk {{ background:{theme.SECONDARY}; }}"
        )
        self._progress.hide()
        layout.addWidget(self._progress)

        self._provider_tag = QLabel(provider)
        self._provider_tag.setProperty("chip", True)
        self._provider_tag.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._provider_tag)

    # ----------------------------------------------------------------- full
    def _build_full(self, name: str, provider: str, domain: str, state: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        self.setMinimumWidth(280)

        top = QHBoxLayout()
        icon = QLabel()
        icon.setFixedSize(40, 40)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setText(name[:1].upper())
        icon.setStyleSheet(
            f"background:{theme.BG_HIGH}; color:{self._color}; "
            f"font-size:18px; font-weight:700; border:1px solid {theme.BORDER};"
        )
        top.addWidget(icon)
        top.addStretch(1)
        self._badge = StateBadge(state)
        top.addWidget(self._badge, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(top)

        name_lbl = QLabel(name)
        name_lbl.setObjectName("agentName")
        layout.addWidget(name_lbl)

        tags = QHBoxLayout()
        tags.setSpacing(6)
        self._domain_tag = QLabel(domain or "Unassigned")
        self._domain_tag.setProperty("chip", True)
        tags.addWidget(self._domain_tag)
        prov = QLabel(provider)
        prov.setProperty("muted", True)
        tags.addWidget(prov)
        tags.addStretch(1)
        layout.addLayout(tags)

        layout.addWidget(self._metric_row("Latency", "—", "latency"))
        layout.addWidget(self._metric_row("Success Rate", "—", "success"))

        btns = QHBoxLayout()
        btns.setSpacing(8)
        configure = QPushButton("Configure")
        configure.setProperty("variant", "ghost")
        configure.clicked.connect(lambda: self.configure_clicked.emit(self.name))
        self._toggle = QPushButton("Deactivate")
        self._toggle.setProperty("variant", "ghost")
        self._toggle.clicked.connect(lambda: self.toggle_clicked.emit(self.name))
        btns.addWidget(configure)
        btns.addWidget(self._toggle)
        layout.addLayout(btns)

    def _metric_row(self, label: str, value: str, key: str) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label)
        lbl.setProperty("muted", True)
        val = QLabel(value)
        val.setStyleSheet(f"color:{theme.TEXT}; font-weight:600;")
        setattr(self, f"_{key}_val", val)
        h.addWidget(lbl)
        h.addStretch(1)
        h.addWidget(val)
        return row

    # ------------------------------------------------------------- updates
    def set_state(self, state: str, description: str | None = None) -> None:
        self._badge.set_state(state)
        running = state.upper() in ("ACTIVE", "RUNNING")
        if self._compact:
            if description is not None:
                self._desc.setText(description)
            self._progress.setVisible(running)

    def set_metrics(self, latency: str | None = None, success: str | None = None) -> None:
        if not self._compact:
            if latency is not None and hasattr(self, "_latency_val"):
                self._latency_val.setText(latency)
            if success is not None and hasattr(self, "_success_val"):
                self._success_val.setText(success)

    def set_domain(self, domain: str) -> None:
        if not self._compact and hasattr(self, "_domain_tag"):
            self._domain_tag.setText(domain or "Unassigned")


# ---------------------------------------------------------------- cluster load

class ClusterLoadChart(QWidget):
    """A tiny bar chart of recent activity, painted by hand (no dependencies)."""

    def __init__(self, bars: int = 12) -> None:
        super().__init__()
        self._max_bars = bars
        self._values: list[float] = [0.15] * bars
        self.setMinimumHeight(60)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def push(self, value: float) -> None:
        self._values.append(max(0.05, min(1.0, value)))
        self._values = self._values[-self._max_bars:]
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w = self.width()
        h = self.height()
        n = len(self._values)
        if n == 0:
            return
        gap = 4
        bar_w = max(3, (w - gap * (n - 1)) / n)
        for i, v in enumerate(self._values):
            bar_h = max(3, v * (h - 4))
            x = i * (bar_w + gap)
            y = h - bar_h
            # Newest bars brighter; older ones dimmer.
            fade = 0.4 + 0.6 * (i / max(1, n - 1))
            color = QColor(theme.ACCENT_TINT)
            color.setAlphaF(fade)
            painter.fillRect(int(x), int(y), int(bar_w), int(bar_h), color)
        painter.end()


# ---------------------------------------------------------------- thought stream

class ThoughtStream(QScrollArea):
    """Chat-style feed of real AgentResults / cross-domain signals."""

    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._body = QWidget()
        self._layout = QVBoxLayout(self._body)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(12)
        self._layout.addStretch(1)
        self.setWidget(self._body)

    def add_entry(self, author: str, color: str, text: str, code: str | None = None) -> None:
        entry = QWidget()
        v = QVBoxLayout(entry)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        head = QLabel(
            f'{dot(color, 10)}&nbsp; '
            f'<span style="color:{color}; font-size:10px; font-weight:700; '
            f'letter-spacing:0.05em;">{html.escape(author.upper())}</span>'
        )
        head.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(head)

        bubble = QFrame()
        bubble.setObjectName("panelCard")
        bv = QVBoxLayout(bubble)
        bv.setContentsMargins(12, 10, 12, 10)
        bv.setSpacing(8)
        body = QLabel(text)
        body.setWordWrap(True)
        body.setStyleSheet(f"color:{theme.TEXT}; background:transparent;")
        bv.addWidget(body)
        if code:
            code_lbl = QLabel(code)
            code_lbl.setWordWrap(True)
            code_lbl.setFont(theme.mono_font(12))
            code_lbl.setStyleSheet(
                f"color:{theme.ACCENT_TINT}; background:{theme.BG_LOWEST}; "
                f"border:1px solid {theme.BORDER}; padding:8px;"
            )
            bv.addWidget(code_lbl)
        v.addWidget(bubble)

        self._layout.insertWidget(self._layout.count() - 1, entry)
        # Autoscroll to newest.
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def clear(self) -> None:
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()


# ---------------------------------------------------------------- log terminal

class _CommandEdit(QLineEdit):
    """QLineEdit with up/down shell-style history recall."""

    def __init__(self) -> None:
        super().__init__()
        self._history: list[str] = []
        self._idx = 0

    def remember(self, cmd: str) -> None:
        self._history.append(cmd)
        self._idx = len(self._history)

    def keyPressEvent(self, event) -> None:  # noqa: ANN001
        if event.key() == Qt.Key.Key_Up and self._history:
            self._idx = max(0, self._idx - 1)
            self.setText(self._history[self._idx])
            return
        if event.key() == Qt.Key.Key_Down and self._history:
            self._idx = min(len(self._history), self._idx + 1)
            self.setText("" if self._idx >= len(self._history) else self._history[self._idx])
            return
        super().keyPressEvent(event)


class LogTerminal(QWidget):
    """Interactive command terminal + live orchestrator log feed.

    Output lines from `append_line` (real logs) and typed shell commands share
    one monospace view. Commands run per-line via QProcess in the workspace
    directory; `cd` and `clear` are handled internally; up/down recall history.

    Non-blocking by design: stdout/stderr stream in via readyRead* signals on
    the Qt event loop, and the input line stays interactive while a process
    runs — typed lines are piped to the process's stdin. `stop()` terminates
    the process safely (SIGTERM, then SIGKILL after a grace period).
    """

    process_started = pyqtSignal(str)   # command line
    process_finished = pyqtSignal(int)  # exit code (-1 on crash/kill)

    _KILL_GRACE_MS = 1500

    def __init__(self, title: str = "SYSTEM TERMINAL") -> None:
        super().__init__()
        self._cwd = Path.cwd()
        self._proc: QProcess | None = None
        self._stopping = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel(f"  {title}")
        header.setObjectName("panelHeader")
        layout.addWidget(header)

        self._view = QPlainTextEdit()
        self._view.setObjectName("terminal")
        self._view.setReadOnly(True)
        self._view.setMaximumBlockCount(5000)
        self._view.setFont(theme.mono_font(12))
        self._view.document().setDocumentMargin(10)
        layout.addWidget(self._view, 1)

        row = QFrame()
        row.setObjectName("termInputRow")
        h = QHBoxLayout(row)
        h.setContentsMargins(10, 4, 10, 6)
        h.setSpacing(8)
        self._prompt = QLabel()
        self._prompt.setFont(theme.mono_font(12))
        self._prompt.setStyleSheet(f"color:{theme.ACCENT_TINT}; background:transparent;")
        h.addWidget(self._prompt)
        self._input = _CommandEdit()
        self._input.setObjectName("termInput")
        self._input.setFont(theme.mono_font(12))
        self._input.setPlaceholderText("Type a command (e.g. ls, git status, python -m pytest)…")
        self._input.returnPressed.connect(self._run)
        h.addWidget(self._input, 1)
        layout.addWidget(row)

        self._refresh_prompt()

    # ------------------------------------------------------------- public API
    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.state() != QProcess.ProcessState.NotRunning

    def stop(self) -> None:
        """Safely terminate the running process: SIGTERM now, SIGKILL if it is
        still alive after the grace period. Never blocks the event loop."""
        if not self.is_running:
            return
        self._stopping = True
        proc = self._proc
        self.append_line("stopping process…", theme.WARN)
        proc.terminate()

        def _force_kill() -> None:
            if proc is self._proc and self.is_running:
                self.append_line("process did not exit — killing.", theme.ERR)
                proc.kill()

        QTimer.singleShot(self._KILL_GRACE_MS, _force_kill)

    def set_cwd(self, path) -> None:  # noqa: ANN001
        p = Path(path)
        if p.is_dir():
            self._cwd = p.resolve()
            self._refresh_prompt()

    def append_line(self, text: str, color: str | None = None) -> None:
        color = color or theme.TEXT_MUTED
        safe = html.escape(text)
        self._view.appendHtml(
            f'<span style="color:{theme.ACCENT_TINT};">&rsaquo;</span> '
            f'<span style="color:{color};">{safe}</span>'
        )

    def append_raw(self, html_text: str) -> None:
        self._view.appendHtml(html_text)

    def set_font_size(self, size: int) -> None:
        """Resize the terminal's monospace font (Settings → General)."""
        font = theme.mono_font(size)
        self._view.setFont(font)
        self._prompt.setFont(font)
        self._input.setFont(font)

    # -------------------------------------------------------------- internals
    def _refresh_prompt(self) -> None:
        self._prompt.setText(f"{self._cwd.name or '/'} $")

    def _run(self) -> None:
        text = self._input.text()
        self._input.clear()
        if not text.strip() and not self.is_running:
            return
        # While a process runs the input line feeds its stdin, so interactive
        # programs (input(), REPLs) keep working and the terminal never locks.
        if self.is_running:
            self._view.appendHtml(
                f'<span style="color:{theme.SECONDARY};">&rsaquo; {html.escape(text)}</span>'
            )
            self._proc.write((text + "\n").encode())
            return
        cmd = text.strip()
        self._input.remember(cmd)
        self.run_command(cmd)

    def run_command(self, cmd: str) -> None:
        """Programmatically run a command (used by the Run button)."""
        cmd = cmd.strip()
        if not cmd:
            return
        if self.is_running:
            self.append_line("a process is already running — stop it first.", theme.WARN)
            return
        self._echo(cmd)
        if cmd == "clear":
            self._view.clear()
            return
        if cmd == "cd" or cmd.startswith("cd "):
            self._chdir(cmd[2:].strip())
            return
        self._start(cmd)

    def _echo(self, cmd: str) -> None:
        self._view.appendHtml(
            f'<span style="color:{theme.ACCENT_TINT};">{html.escape(self._cwd.name or "/")} $</span> '
            f'<span style="color:{theme.TEXT};">{html.escape(cmd)}</span>'
        )

    def _chdir(self, target: str) -> None:
        if not target or target == "~":
            dest = Path.home()
        else:
            dest = Path(target).expanduser()
            if not dest.is_absolute():
                dest = self._cwd / dest
        if dest.is_dir():
            self._cwd = dest.resolve()
            self._refresh_prompt()
        else:
            self._view.appendHtml(
                f'<span style="color:{theme.ERR};">cd: no such directory: {html.escape(target)}</span>'
            )

    def _start(self, cmd: str) -> None:
        self._stopping = False
        proc = QProcess(self)
        proc.setWorkingDirectory(str(self._cwd))
        # Separate channels: stdout streams as plain text, stderr renders in the
        # error color. Both arrive via readyRead* slots on the Qt event loop —
        # the UI thread is never blocked, no matter how chatty the process is.
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        proc.readyReadStandardOutput.connect(self._read_stdout)
        proc.readyReadStandardError.connect(self._read_stderr)
        proc.finished.connect(self._finished)
        proc.errorOccurred.connect(self._error)
        self._proc = proc
        self._input.setPlaceholderText("Process running — Enter sends to stdin; Stop terminates.")
        self._prompt.setText("stdin ▸")
        shell = os.environ.get("SHELL", "/bin/bash")
        proc.start(shell, ["-c", cmd])
        self.process_started.emit(cmd)

    def _read_stdout(self) -> None:
        if self._proc is None:
            return
        data = bytes(self._proc.readAllStandardOutput()).decode("utf-8", "replace")
        if data.strip("\n"):
            self._view.appendPlainText(data.rstrip("\n"))

    def _read_stderr(self) -> None:
        if self._proc is None:
            return
        data = bytes(self._proc.readAllStandardError()).decode("utf-8", "replace")
        for line in data.rstrip("\n").splitlines():
            self._view.appendHtml(
                f'<span style="color:{theme.ERR};">{html.escape(line)}</span>'
            )

    def _finished(self, code: int, _status) -> None:  # noqa: ANN001
        self._read_stdout()
        self._read_stderr()
        if self._stopping:
            self._view.appendHtml(
                f'<span style="color:{theme.WARN};">[process stopped]</span>'
            )
        elif code != 0:
            self._view.appendHtml(
                f'<span style="color:{theme.TEXT_FAINT};">[exit {code}]</span>'
            )
        self._reset_after_process()
        self.process_finished.emit(-1 if self._stopping else code)
        self._stopping = False

    def _error(self, err) -> None:  # noqa: ANN001
        # FailedToStart never reaches finished(); Crashed does. Only handle the
        # launch failure here so lines aren't double-reported.
        if err == QProcess.ProcessError.FailedToStart:
            self.append_line("failed to launch command (shell unavailable)", theme.ERR)
            self._reset_after_process()
            self.process_finished.emit(-1)

    def _reset_after_process(self) -> None:
        self._proc = None
        self._input.setPlaceholderText(
            "Type a command (e.g. ls, git status, python -m pytest)…"
        )
        self._refresh_prompt()
        self._input.setFocus()


class PromptBar(QFrame):
    """The AI chat bar — 'Prompt all agents…' input + send button."""

    submitted = pyqtSignal(str)

    def __init__(self, placeholder: str = "Prompt all agents… (e.g. 'Optimise my main loop')") -> None:
        super().__init__()
        self.setObjectName("promptBar")
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 10, 12, 10)
        h.setSpacing(10)

        icon = QLabel("\u26a1")
        icon.setStyleSheet(f"color:{theme.ACCENT_TINT}; font-size:15px; background:transparent;")
        h.addWidget(icon)

        self._input = QLineEdit()
        self._input.setObjectName("promptInput")
        self._input.setPlaceholderText(placeholder)
        self._input.returnPressed.connect(self._submit)
        h.addWidget(self._input, 1)

        hint = QLabel("\u2318K")
        hint.setProperty("chip", True)
        h.addWidget(hint)

        self._send = QPushButton("\u27a4")
        self._send.setProperty("variant", "primary")
        self._send.setFixedWidth(44)
        self._send.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send.clicked.connect(self._submit)
        h.addWidget(self._send)

    def _submit(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self.submitted.emit(text)

    def set_placeholder(self, text: str) -> None:
        self._input.setPlaceholderText(text)


# ---------------------------------------------------------------- status pill

class StatusPill(QLabel):
    """Health indicator for the memory sidecar (status-bar, mono text)."""

    def __init__(self, text: str = "sidecar: connecting…") -> None:
        super().__init__(text)
        self.setObjectName("statusPill")
        self.setTextFormat(Qt.TextFormat.RichText)

    def set_healthy(self, healthy: bool, detail: str = "") -> None:
        self.setProperty("healthy", "true" if healthy else "false")
        d = dot(theme.OK if healthy else theme.ERR, size=8)
        label = "SIDECAR ONLINE" if healthy else "SIDECAR DOWN"
        self.setText(f"{d}&nbsp; {label}")
        self.setToolTip(detail)
        self.style().unpolish(self)
        self.style().polish(self)
