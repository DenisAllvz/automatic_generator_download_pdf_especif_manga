"""Copy this workspace's old portable database to the new build without replacing it."""
import hashlib
import shutil
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from app.core.config import Settings
from app.infrastructure.database import Database
from app.services.library import Library

import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--source-name", default="MangaManager")
parser.add_argument("--output-name", default="MangaManager-2.0.1")
args = parser.parse_args()
for name in (args.source_name, args.output_name):
    if not name.replace("-", "").replace("_", "").replace(".", "").isalnum():
        raise SystemExit("Nome de pasta inválido.")
source = root / "dist" / args.source_name / "data"
destination = root / "dist" / args.output_name / "data"
database = source / "library.sqlite3"
if not database.is_file():
    raise SystemExit("Não há banco portátil anterior para copiar.")
if destination.exists():
    raise SystemExit("O destino já contém dados; nada foi substituído.")
before = hashlib.sha256(database.read_bytes()).hexdigest()
destination.mkdir(parents=True)
with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as old:
    old.execute("BEGIN")
    old_counts = [old.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("mangas", "chapters", "tasks")]
    with closing(sqlite3.connect(destination / "library.sqlite3")) as new:
        old.backup(new)
if (source / "settings.json").is_file():
    shutil.copy2(source / "settings.json", destination / "settings.json")
if (source / "logs" / "downloads").is_dir():
    shutil.copytree(source / "logs" / "downloads", destination / "logs" / "downloads")
if (source / 'covers').is_dir():
    shutil.copytree(source / 'covers', destination / 'covers')
if (source / 'drive').is_dir():
    shutil.copytree(source / 'drive', destination / 'drive')
if (source / 'logs' / 'drive').is_dir():
    shutil.copytree(source / 'logs' / 'drive', destination / 'logs' / 'drive')
settings = Settings.load(destination / "settings.json")
settings.save(destination / "settings.json")
db = Database(destination / "library.sqlite3")
Library(db, Path(settings.library)).repair_site_titles()
for manga in db.mangas():
    cover = Path(manga['cover_file']) if manga['cover_file'] else None
    if cover and cover.is_absolute() and cover.is_relative_to(source.resolve()):
        db.execute('UPDATE mangas SET cover_file=? WHERE id=?',
                   (str(destination.resolve() / cover.relative_to(source.resolve())), manga['id']))
new_counts = [db.query(f"SELECT COUNT(*) AS count FROM {table}")[0]["count"] for table in ("mangas", "chapters", "tasks")]
assert old_counts == new_counts
if before != hashlib.sha256(database.read_bytes()).hexdigest():
    print('A versão antiga continuou gravando; foi preservado um instantâneo SQLite consistente, sem alterar a origem.')
print(f"Biblioteca preservada: {new_counts[0]} obras, {new_counts[1]} capítulos, {new_counts[2]} tarefas.")
print(destination)
