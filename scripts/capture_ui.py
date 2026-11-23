"""Offline visual review across five pages; isolated sample data only."""
import os
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase, QFont
from app.core.config import Settings
from app.infrastructure.database import Database
from app.ui.main_window import MainWindow
from app.smoke import exercise
from app.models import Manga, Chapter

app = QApplication([])
font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
if font.exists():
    QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont("Segoe UI", 10))
output = root / "tmp" / "ui-review"
output.mkdir(parents=True, exist_ok=True)
data = output / f"data-{time.time_ns()}"
window = MainWindow(Database(data / "library.sqlite3"), Settings(library=str(data / "demo-library")), data, start_queue=False)
window.show()
exercise(window, data)
window.show_preview((Manga("Coleção de demonstração", "https://example.org/demo", description="Prévia de fonte simulada.",
                           chapters=[Chapter(f"Capítulo {i}", f"https://example.org/demo/chapter-{i}") for i in range(1, 6)]), None, "Fixture HTML"))
diagnostic = window.library.diagnostic()
from app.ui.main_window import fill, STATUS
fill(window.diagnostic_table, [[r["manga"], r["chapter"], STATUS.get(r["status"], r["status"]), "; ".join(r["issues"])] for r in diagnostic])
for index in range(window.stack.count()):
    window.show_page(index)
    app.processEvents()
    window.grab().save(str(output / f"screen-{index}.png"))
    print(index, window.minimumSizeHint().width(), window.minimumSizeHint().height())
mid, ids = window.library.add(Manga('Demonstração da fila', 'https://example.org/queue-demo', chapters=[
    Chapter(f'Capítulo {i}', f'https://example.org/queue-demo/{i}') for i in range(1, 4)]))
window.library.enqueue(ids)
window.db.execute("UPDATE tasks SET status='running',done=18,total=30 WHERE chapter_id=?", (ids[0],))
window.db.execute("UPDATE tasks SET status='failed',error='Conexão interrompida. Tente novamente.' WHERE chapter_id=?", (ids[2],))
window.refresh_queue()
window.show_page(2)
app.processEvents()
window.grab().save(str(output / 'screen-downloads.png'))
window.timer.stop()
window.refresh_timer.stop()
while window.jobs:
    app.processEvents()
    time.sleep(.01)
window.close()
