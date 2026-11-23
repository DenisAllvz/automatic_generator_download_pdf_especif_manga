"""One local SQLite catalogue per work, replacing JSON sidecars per chapter."""
import json
import os
import sqlite3
import threading
from contextlib import contextmanager, closing
from pathlib import Path

CATALOG_NAME = '.manga-manager.sqlite3'
_lock = threading.RLock()


class Catalog:
    def __init__(self, folder):
        self.folder = Path(folder).resolve()
        self.path = self.folder / CATALOG_NAME

    @contextmanager
    def connection(self):
        with _lock:
            self.folder.mkdir(parents=True, exist_ok=True)
            if self.path.is_symlink():
                raise OSError('O catálogo da obra não pode ser um link simbólico.')
            try:
                with closing(sqlite3.connect(self.path, timeout=15)) as db:
                    db.execute('CREATE TABLE IF NOT EXISTS records(kind TEXT, name TEXT, payload TEXT NOT NULL, PRIMARY KEY(kind,name))')
                    with db:
                        yield db
            except sqlite3.Error as exc:
                raise OSError(f'Não foi possível salvar o catálogo da obra: {exc}') from exc
            if os.name == 'nt':
                import ctypes
                attrs = ctypes.windll.kernel32.GetFileAttributesW(str(self.path.resolve()))
                if attrs != -1:
                    ctypes.windll.kernel32.SetFileAttributesW(str(self.path.resolve()), attrs | 2)

    def get(self, kind, name):
        if not self.path.exists():
            return None
        if self.path.is_symlink():
            raise OSError('Catálogo inválido.')
        try:
            with _lock, closing(sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)) as db:
                row = db.execute('SELECT payload FROM records WHERE kind=? AND name=?', (kind, name)).fetchone()
                return json.loads(row[0]) if row else None
        except sqlite3.Error as exc:
            raise OSError(f'Não foi possível ler o catálogo da obra: {exc}') from exc

    def put(self, kind, name, data):
        with self.connection() as db:
            db.execute('INSERT OR REPLACE INTO records VALUES(?,?,?)', (kind, name, json.dumps(data, ensure_ascii=False)))

    def manifests(self):
        if not self.path.exists():
            return []
        with self.connection() as db:
            return [(name, json.loads(data)) for name, data in db.execute("SELECT name,payload FROM records WHERE kind='manifest'")]

    def migrate(self):
        """Commit all recognized records before deleting unchanged legacy sidecars."""
        candidates = [(self.folder / 'metadata.json', 'metadata', '')]
        candidates += [(p, 'manifest', p.parent.name) for p in self.folder.glob('*/manifest.json')]
        candidates += [(p, 'receipt', p.name[:-5]) for p in (self.folder / 'PDF').glob('*.pdf.json')]
        records = []
        for path, kind, name in candidates:
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(self.folder.resolve()):
                continue
            try:
                content = path.read_bytes()
                data = json.loads(content)
                recognized = isinstance(data, dict) and (
                    (kind=='manifest' and isinstance(data.get('expected'), int) and isinstance(data.get('pages'), list)) or
                    (kind=='receipt' and all(isinstance(data.get(k), str) and len(data[k])==64 for k in ('images','pdf'))) or
                    (kind=='metadata' and isinstance(data.get('title'), str) and isinstance(data.get('url'), str)))
                if recognized:
                    records.append((path, kind, name, data, content))
            except (OSError, ValueError):
                continue
        if not records:
            return 0
        with self.connection() as db:
            for _, kind, name, data, _ in records:
                db.execute('INSERT OR REPLACE INTO records VALUES(?,?,?)', (kind, name, json.dumps(data, ensure_ascii=False)))
        removed = 0
        for path, kind, name, data, content in records:
            # Verify the durable copy and preserve files changed by another instance.
            if self.get(kind, name) == data and path.read_bytes() == content:
                path.unlink()
                removed += 1
        return removed


def read_manifest(folder):
    folder = Path(folder)
    legacy = folder / 'manifest.json'
    if legacy.exists():
        return json.loads(legacy.read_text(encoding='utf-8'))
    return Catalog(folder.parent.resolve()).get('manifest', folder.name)


def save_manifest(folder, data):
    folder = Path(folder)
    Catalog(folder.parent.resolve()).put('manifest', folder.name, data)
    legacy = folder / 'manifest.json'
    if legacy.exists() and not legacy.is_symlink():
        # The new checkpoint includes the old cached pages and newer downloaded pages.
        legacy.unlink()


def read_metadata(folder):
    folder = Path(folder)
    legacy = folder / 'metadata.json'
    return json.loads(legacy.read_text(encoding='utf-8')) if legacy.exists() else Catalog(folder.resolve()).get('metadata', '') or {}
