"""Validate existing PDFs by metadata snapshot; never write inside downloads."""
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from app.infrastructure.database import Database
from app.infrastructure.filesystem import atomic_json
from app.services.library import Library

downloads = root / "Downloads_Mangas"
def snapshot():
    return {str(p.relative_to(downloads)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in downloads.rglob("*.pdf")}

before = snapshot()
data = root / "tmp" / "legacy-import-check"
db = Database(data / "library.sqlite3")
library = Library(db, data / "unused-library")
added = library.import_folder(downloads)
after = snapshot()
assert before == after
chapters = db.query("SELECT * FROM chapters")
assert len(chapters) == len(before)
assert all(c["status"] == "legacy" for c in chapters)
result = dict(pdf_count=len(before), works=len(db.mangas()), unchanged_sizes_and_mtimes=before == after,
              imported_records=len(chapters), status="legacy, completeness not verified")
atomic_json(data / "evidence.json", result)
print(result)
