import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Short connections + lock: safe for GUI and worker threads; no shared cursor."""
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 2:
                raise RuntimeError("Banco de versão mais nova; atualize o aplicativo.")
            if version == 0:
                db.executescript("""
                    CREATE TABLE mangas(id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT UNIQUE,
                        folder TEXT NOT NULL, description TEXT DEFAULT '', cover TEXT DEFAULT '',
                        favorite INTEGER DEFAULT 0, tags TEXT DEFAULT '', updated TEXT);
                    CREATE TABLE chapters(id TEXT PRIMARY KEY, manga_id TEXT REFERENCES mangas(id),
                        title TEXT, url TEXT UNIQUE, folder TEXT, status TEXT DEFAULT 'pending',
                        read_page INTEGER DEFAULT 0, expected INTEGER DEFAULT 0, completed INTEGER DEFAULT 0,
                        authoritative INTEGER DEFAULT 0);
                    CREATE TABLE tasks(id INTEGER PRIMARY KEY AUTOINCREMENT, chapter_id TEXT REFERENCES chapters(id),
                        status TEXT DEFAULT 'queued', priority INTEGER DEFAULT 0,
                        done INTEGER DEFAULT 0, total INTEGER DEFAULT 0, bytes INTEGER DEFAULT 0,
                        speed REAL DEFAULT 0, elapsed REAL DEFAULT 0, skipped INTEGER DEFAULT 0,
                        error TEXT DEFAULT '', updated TEXT);
                    CREATE UNIQUE INDEX active_chapter ON tasks(chapter_id)
                        WHERE status IN ('queued','running','paused');
                    CREATE TABLE errors(id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER,
                        chapter_id TEXT, page INTEGER, url TEXT, category TEXT, message TEXT,
                        attempts INTEGER, http_status INTEGER, created TEXT, action TEXT);
                    PRAGMA user_version=1;
                """)
            if version <= 1:
                db.execute('BEGIN')
                additions = {
                    'mangas': {'cover_file': "TEXT DEFAULT ''", 'custom_title': 'INTEGER DEFAULT 0'},
                    'chapters': {'is_read': 'INTEGER DEFAULT 0', 'read_total': 'INTEGER DEFAULT 0',
                                 'read_x': 'REAL DEFAULT 0', 'read_y': 'REAL DEFAULT 0',
                                 'read_scroll': 'REAL DEFAULT 0',
                                 'read_zoom': 'REAL DEFAULT 0', 'read_updated': "TEXT DEFAULT ''"}}
                for table, columns in additions.items():
                    existing = {row[1] for row in db.execute(f'PRAGMA table_info({table})')}
                    for column, definition in columns.items():
                        if column not in existing:
                            db.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
                db.execute('CREATE INDEX IF NOT EXISTS chapters_manga ON chapters(manga_id)')
                db.execute('CREATE INDEX IF NOT EXISTS tasks_status ON tasks(status,id)')
                db.execute('PRAGMA user_version=2')
        # Recovery is explicit, never silently resume network traffic.
        with self.connection() as db:
            db.execute("UPDATE tasks SET status='paused', speed=0 WHERE status='running'")

    @contextmanager
    def connection(self):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=15)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA journal_mode=WAL")
            try:
                with db:
                    yield db
            finally:
                db.close()

    def query(self, sql: str, args=()) -> list[dict]:
        with self.connection() as db:
            return [dict(row) for row in db.execute(sql, args).fetchall()]

    def execute(self, sql: str, args=()):
        with self.connection() as db:
            return db.execute(sql, args).lastrowid

    def mangas(self):
        return self.query("""SELECT m.*, count(c.id) chapters,
            sum(CASE WHEN c.status IN ('verified','downloaded','legacy') THEN 1 ELSE 0 END) completed,
            sum(CASE WHEN c.is_read=1 THEN 1 ELSE 0 END) read_count
            FROM mangas m LEFT JOIN chapters c ON m.id=c.manga_id GROUP BY m.id ORDER BY m.title COLLATE NOCASE""")

    def chapters(self, manga_id: str):
        from app.infrastructure.filesystem import chapter_key
        return sorted(self.query("SELECT * FROM chapters WHERE manga_id=?", (manga_id,)), key=lambda c: chapter_key(c["title"]))

    def tasks(self, status=None):
        from app.infrastructure.filesystem import chapter_key
        sql = """SELECT t.*, c.title chapter, m.title manga,c.manga_id FROM tasks t
            JOIN chapters c ON t.chapter_id=c.id JOIN mangas m ON c.manga_id=m.id
            """
        rows = self.query(sql + ('WHERE t.status=? ' if status else '') + 'ORDER BY t.id', (status,) if status else ())
        groups = {}
        for row in rows:
            groups.setdefault(row['manga_id'], row['id'])
        return sorted(rows, key=lambda t: (groups[t['manga_id']], chapter_key(t['chapter']), t['id']))

    def backup(self, target: Path):
        with self.connection() as db, sqlite3.connect(target) as out:
            db.backup(out)
