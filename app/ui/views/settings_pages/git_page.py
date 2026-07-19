"""Git & PRs: real repository state for the workspace, read via the git CLI.

Every git call runs through QProcess with a finished-callback, so the UI thread
is never blocked (the same non-blocking pattern as the system terminal).
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QProcess
from PyQt6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from app.ui import theme
from app.ui.views.settings_pages.common import SettingsPage, ghost, info_row


class GitPage(SettingsPage):
    title = "Git & PRs"
    subtitle = "Repository state for the current workspace."

    def __init__(self, workspace: Path) -> None:
        super().__init__()
        self.workspace = workspace
        self._procs: list[QProcess] = []

        self._summary_card = self.add_card(padded=False)
        self._summary_host = QWidget()
        self._summary = QVBoxLayout(self._summary_host)
        self._summary.setContentsMargins(0, 0, 0, 0)
        self._summary.setSpacing(0)
        self._summary_card.addWidget(self._summary_host)

        changes_label = QLabel("WORKING TREE")
        changes_label.setProperty("caps", True)
        self.body.addWidget(changes_label)
        self._changes = self._mono_box("Clean working tree.")
        self.body.addWidget(self._changes)

        commits_label = QLabel("RECENT COMMITS")
        commits_label.setProperty("caps", True)
        self.body.addWidget(commits_label)
        self._commits = self._mono_box("")
        self.body.addWidget(self._commits)

        refresh = ghost("↻  Refresh")
        refresh.clicked.connect(self.refresh)
        self.add_actions(refresh)
        self.add_status_line()
        self.finish()

        self.refresh()

    @staticmethod
    def _mono_box(placeholder: str) -> QPlainTextEdit:
        box = QPlainTextEdit()
        box.setObjectName("terminal")
        box.setReadOnly(True)
        box.setFont(theme.mono_font(11))
        box.setMinimumHeight(120)
        box.setPlaceholderText(placeholder)
        return box

    # -------------------------------------------------------------- git plumbing
    def _git(self, args: list[str], done) -> None:  # noqa: ANN001
        """Run a git command in the workspace and hand stdout to `done`.

        Callbacks are defensive: if the page (and with it the QProcess) is torn
        down while a command is still in flight, Qt still delivers the pending
        signal, and touching the deleted C++ object would raise.
        """
        proc = QProcess(self)
        proc.setWorkingDirectory(str(self.workspace))
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)

        def _finished(code: int, _status) -> None:  # noqa: ANN001
            try:
                out = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace").strip()
            except RuntimeError:
                return  # process/page destroyed mid-flight
            if proc in self._procs:
                self._procs.remove(proc)
            done(code, out)

        def _failed(_err) -> None:  # noqa: ANN001
            if proc in self._procs:
                self._procs.remove(proc)
            done(-1, "")

        proc.finished.connect(_finished)
        proc.errorOccurred.connect(_failed)
        self._procs.append(proc)
        proc.start("git", args)

    def shutdown(self) -> None:
        """Kill any in-flight git command (called when the app closes)."""
        for proc in list(self._procs):
            try:
                if proc.state() != QProcess.ProcessState.NotRunning:
                    proc.kill()
                    proc.waitForFinished(500)
            except RuntimeError:
                pass
        self._procs.clear()

    def refresh(self) -> None:
        self.report("Reading repository…")
        self._git(["rev-parse", "--is-inside-work-tree"], self._on_is_repo)

    def _on_is_repo(self, code: int, out: str) -> None:
        if code != 0 or out != "true":
            self._render_summary([("Repository", "Not a git repository", theme.WARN)])
            self._changes.setPlainText("")
            self._changes.setPlaceholderText(
                f"{self.workspace} is not a git repository — run `git init` to track it."
            )
            self._commits.setPlainText("")
            self.report("Workspace is not under git version control.", theme.WARN)
            return
        self._git(["rev-parse", "--abbrev-ref", "HEAD"], self._on_branch)

    def _on_branch(self, _code: int, out: str) -> None:
        self._branch = out or "(detached)"
        self._git(["remote", "get-url", "origin"], self._on_remote)

    def _on_remote(self, code: int, out: str) -> None:
        self._remote = out if code == 0 and out else "no remote"
        self._git(["status", "--porcelain"], self._on_status)

    def _on_status(self, _code: int, out: str) -> None:
        lines = [ln for ln in out.splitlines() if ln.strip()]
        self._render_summary([
            ("Branch", self._branch, theme.ACCENT_TINT),
            ("Remote", self._remote, None),
            ("Working tree",
             "clean" if not lines else f"{len(lines)} change(s)",
             theme.OK if not lines else theme.WARN),
        ])
        self._changes.setPlainText("\n".join(lines))
        if not lines:
            self._changes.setPlaceholderText("Clean working tree.")
        self._git(["log", "-5", "--pretty=format:%h  %an  %ar  %s"], self._on_log)

    def _on_log(self, _code: int, out: str) -> None:
        self._commits.setPlainText(out)
        self.report(f"Repository read at {self.workspace}.", theme.OK)

    def _render_summary(self, rows: list[tuple[str, str, str | None]]) -> None:
        while self._summary.count():
            item = self._summary.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for i, (label, value, color) in enumerate(rows):
            self._summary.addWidget(
                info_row(label, value, value_color=color, mono=True, last=i == len(rows) - 1)
            )
