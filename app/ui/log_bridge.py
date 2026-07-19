"""Bridge Python `logging` records onto a Qt signal.

Installs a `logging.Handler` on the orchestrator loggers (`app.core.*`,
`app.agents.*`, `app.context.*`, `app.memory.*`) and re-emits each formatted
record as a `pyqtSignal(str, str)` — (message, level). Because logging can fire
from any thread, the signal (auto-queued to the GUI thread by Qt) makes it safe
for `LogTerminal` to render **real** orchestrator activity.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, pyqtSignal

_LOGGERS = ("app.core", "app.agents", "app.context", "app.memory")


class QtLogBridge(QObject):
    message = pyqtSignal(str, str)  # (formatted line, levelname)

    def __init__(self, level: int = logging.INFO) -> None:
        super().__init__()
        self._handler = _SignalHandler(self.message)
        self._handler.setLevel(level)
        self._handler.setFormatter(
            logging.Formatter("%(name)s: %(message)s")
        )

    def install(self) -> None:
        for name in _LOGGERS:
            logger = logging.getLogger(name)
            if self._handler not in logger.handlers:
                logger.addHandler(self._handler)

    def uninstall(self) -> None:
        for name in _LOGGERS:
            logging.getLogger(name).removeHandler(self._handler)


class _SignalHandler(logging.Handler):
    def __init__(self, signal: pyqtSignal) -> None:
        super().__init__()
        self._signal = signal

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._signal.emit(msg, record.levelname)
        except Exception:  # never let logging crash the app
            self.handleError(record)
