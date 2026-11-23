import asyncio
import logging
from PySide6.QtCore import QThread, Signal
from app.core.security import scrub


class Job(QThread):
    result = Signal(object)
    error = Signal(str)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.function = function

    def run(self):
        try:
            self.result.emit(self.function())
        except Exception as exc:
            # Thread boundary: show and log unexpected failures; never hide them.
            message = scrub(f"{type(exc).__name__}: {exc}")
            logging.getLogger("manga").error(message)
            self.error.emit(message)


class QueueWorker(QThread):
    changed = Signal()
    error = Signal(str)

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.manager.notify = self.changed.emit

    def run(self):
        try:
            asyncio.run(self.manager.run())
        except Exception as exc:
            message = scrub(f"Fila interrompida: {type(exc).__name__}: {exc}")
            logging.getLogger("manga").error(message)
            self.error.emit(message)
