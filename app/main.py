"""CombinePro entry point.

qasync merges the Qt and asyncio event loops so the PyQt6 UI and the async
orchestrator (router, watcher, agents, memory client) run in one process on
one loop — no threads, no polling.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import qasync
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QFileDialog

from app.config import Config
from app.core.orchestrator import Orchestrator
from app.ui.icons import app_icon
from app.ui.main_window import MainWindow
from app.ui.theme import apply_theme

log = logging.getLogger(__name__)


def resolve_workspace(app: QApplication, config: Config) -> Path | None:
    settings = QSettings("CombinePro", "CombinePro")
    candidates = [config.workspace, settings.value("workspace", "")]
    for cand in candidates:
        if cand and Path(cand).is_dir():
            return Path(cand).resolve()
    chosen = QFileDialog.getExistingDirectory(None, "Choose a workspace folder")
    if not chosen:
        return None
    settings.setValue("workspace", chosen)
    return Path(chosen).resolve()


async def amain(app: QApplication, window: MainWindow, orchestrator: Orchestrator) -> None:
    await orchestrator.start()
    pump = asyncio.ensure_future(window.run_event_pump())

    closed = asyncio.Event()
    app.aboutToQuit.connect(closed.set)
    await closed.wait()

    pump.cancel()
    await orchestrator.stop()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    config = Config()

    app = QApplication(sys.argv)
    app.setApplicationName("CombinePro")
    # Default icon for every top-level window and dialog.
    app.setWindowIcon(app_icon())
    apply_theme(app)

    workspace = resolve_workspace(app, config)
    if workspace is None:
        print("No workspace selected — exiting.")
        return 1

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    orchestrator = Orchestrator(config, workspace)
    window = MainWindow(config, workspace, orchestrator)
    window.show()

    with loop:
        loop.run_until_complete(amain(app, window, orchestrator))
    return 0


if __name__ == "__main__":
    sys.exit(main())
