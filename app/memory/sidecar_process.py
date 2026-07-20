"""Supervises the bundled Node memory sidecar.

A built CombinePro ships the sidecar's JavaScript and `node_modules`, but not a
Node runtime — Node links against a tree of shared libraries that does not
relocate cleanly into an app bundle. So we launch the sidecar with the Node
already on the user's machine and, when there isn't one, simply run without
Delta Memory: the orchestrator already treats an unreachable sidecar as a
degraded-but-working state, and Settings → Memory & MCP shows it plainly.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from app.paths import resource_path

log = logging.getLogger(__name__)

# Locations Node commonly installs to but which a GUI app's PATH may miss —
# launching from Finder/Explorer does not inherit a login shell's PATH.
_EXTRA_NODE_PATHS = (
    "/opt/homebrew/bin/node",
    "/usr/local/bin/node",
    "/usr/bin/node",
    str(Path.home() / ".nvm" / "versions" / "node"),
    r"C:\Program Files\nodejs\node.exe",
    r"C:\Program Files (x86)\nodejs\node.exe",
)


def find_node() -> str | None:
    """Locate a Node executable, tolerating a GUI app's minimal PATH."""
    found = shutil.which("node")
    if found:
        return found
    for candidate in _EXTRA_NODE_PATHS:
        path = Path(candidate)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
        # nvm keeps versioned installs; take the newest.
        if path.is_dir():
            versions = sorted(path.glob("*/bin/node"), reverse=True)
            if versions:
                return str(versions[0])
    return None


class SidecarProcess:
    """Starts/stops the knbase sidecar as a child process."""

    def __init__(self, sidecar_url: str, workspace: Path | None = None) -> None:
        self.sidecar_url = sidecar_url
        self.workspace = workspace
        self.dir = resource_path("sidecar")
        self._proc: subprocess.Popen | None = None
        self.reason: str = ""

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _port(self) -> str:
        parsed = urlparse(self.sidecar_url)
        return str(parsed.port or 8787)

    def start(self) -> bool:
        """Launch the sidecar. Returns False (with `reason` set) if it can't run."""
        server = self.dir / "server.js"
        if not server.is_file():
            self.reason = f"sidecar not bundled ({server})"
            log.warning("Memory sidecar missing: %s", server)
            return False
        if not (self.dir / "node_modules").is_dir():
            self.reason = "sidecar dependencies missing (run `npm install` in sidecar/)"
            log.warning(self.reason)
            return False

        node = find_node()
        if node is None:
            self.reason = "Node.js not found — install Node 18+ to enable Delta Memory"
            log.warning(self.reason)
            return False

        env = dict(os.environ)
        env["SIDECAR_PORT"] = self._port()
        # Pin the project root. knbase's resolveProjectRoot() otherwise walks UP
        # for a .knbase dir and falls back to the nearest .git — so a workspace
        # nested inside a larger repo would silently write memory-bank/ at the
        # repo root instead of the workspace.
        if self.workspace is not None:
            env["KNBASE_ROOT"] = str(self.workspace)
        creation = {}
        if os.name == "nt":
            # Keep a console window from flashing up on Windows.
            creation["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self._proc = subprocess.Popen(
                [node, str(server)],
                cwd=str(self.dir),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                **creation,
            )
        except OSError as exc:
            self.reason = f"could not launch sidecar: {exc}"
            log.warning(self.reason)
            return False

        log.info("Memory sidecar started (pid %s, port %s)", self._proc.pid, self._port())
        return True

    def stop(self) -> None:
        """Terminate the sidecar, escalating to kill if it ignores SIGTERM."""
        if not self.running:
            self._proc = None
            return
        proc = self._proc
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                log.warning("Memory sidecar did not exit")
        self._proc = None
        log.info("Memory sidecar stopped")
