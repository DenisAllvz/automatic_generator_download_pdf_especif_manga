"""Offline queue benchmark. Uses isolated data and never touches user downloads."""
import json
import os
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from PySide6.QtWidgets import QApplication, QProgressBar
from app.core.config import Settings
from app.infrastructure.database import Database
from app.models import Manga, Chapter
from app.services.library import Library
from app.ui.main_window import MainWindow

app = QApplication([])
with TemporaryDirectory(prefix='manga-performance-') as temporary:
    data = Path(temporary)
    settings = Settings(library=str(data / 'library'))
    db = Database(data / 'library.sqlite3')
    library = Library(db, Path(settings.library))
    _, ids = library.add(Manga('Benchmark', 'https://example.org/benchmark', chapters=[
        Chapter(f'Capítulo {i}', f'https://example.org/benchmark/{i}') for i in range(1000)]))
    library.enqueue(ids)
    window = MainWindow(db, settings, data, start_queue=False)
    window.timer.stop()
    window.show()
    app.processEvents()
    elapsed = []
    for _ in range(5):
        start = time.perf_counter()
        window.refresh_queue()
        elapsed.append(round(1000 * (time.perf_counter() - start), 2))
        app.processEvents()
    report = dict(version=__import__('app').__version__, rows=len(window.task_rows),
                  refresh_ms=elapsed, progress_widgets=len(window.findChildren(QProgressBar)))
    window.close()
output = root / 'tmp' / 'performance-after.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
