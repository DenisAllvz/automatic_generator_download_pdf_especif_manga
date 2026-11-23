"""Recover complete local downloads, including folders moved in Explorer."""
import json
from pathlib import Path
from app.infrastructure.filesystem import identity, contained
from app.infrastructure.catalog import Catalog, CATALOG_NAME, read_metadata, read_manifest
from app.core.exceptions import SecurityError
from app.services.export import pdf_target


def recover_downloads(library, root=None):
    db = library.db
    relocated = 0
    if root is not None:
        root = Path(root).resolve()
        works = {p.parent.parent for p in root.rglob('manifest.json')}
        works.update(p.parent for p in root.rglob(CATALOG_NAME))
        for work in works:
            if work.is_symlink() or not work.resolve().is_relative_to(root):
                continue
            try:
                metadata = read_metadata(work)
                known = db.query('SELECT * FROM mangas WHERE url=?', (metadata.get('url'),))
                if not known:
                    continue
                catalog = Catalog(work)
                catalog.migrate()
                for name, data in catalog.manifests():
                    folder = contained(work, name)
                    url = data.get('chapter_url')
                    if not url or not data.get('expected') or not isinstance(data.get('pages'), list):
                        continue
                    existing = db.query('SELECT * FROM chapters WHERE id=? AND manga_id=?', (identity(url), known[0]['id']))
                    if not existing:
                        continue
                    chapter = existing[0]
                    if Path(chapter['folder']) != folder:
                        if Path(chapter['folder']).exists():
                            continue
                        db.execute('UPDATE chapters SET folder=? WHERE id=?', (str(folder), chapter['id']))
                        db.execute('UPDATE mangas SET folder=? WHERE id=?', (str(work), chapter['manga_id']))
                        relocated += 1
                    complete = len(data['pages']) == data['expected']
                    status = ('verified' if data.get('authoritative') else 'downloaded') if complete else 'incomplete'
                    db.execute('UPDATE chapters SET status=?,expected=?,completed=? WHERE id=?',
                               (status, data['expected'], len(data['pages']), chapter['id']))
            except (OSError, ValueError, KeyError, TypeError, SecurityError):
                continue
    chapters = db.query("SELECT * FROM chapters WHERE status IN ('downloaded','verified','unverifiable')")
    ready = []
    for chapter in chapters:
        try:
            if read_manifest(Path(chapter['folder'])) is not None and not pdf_target(chapter).exists():
                ready.append(chapter)
        except (OSError, ValueError, TypeError):
            continue
    # Reuse historical tasks; don't create hundreds of duplicate completed rows.
    count = 0
    with db.connection() as connection:
        for chapter in ready:
            active = connection.execute("SELECT 1 FROM tasks WHERE chapter_id=? AND status IN ('queued','running','paused')", (chapter['id'],)).fetchone()
            if active:
                continue
            task = connection.execute('SELECT id FROM tasks WHERE chapter_id=? ORDER BY id DESC LIMIT 1', (chapter['id'],)).fetchone()
            if task:
                connection.execute("UPDATE tasks SET status='queued',error='' WHERE id=?", (task[0],))
            else:
                connection.execute("INSERT INTO tasks(chapter_id,status) VALUES(?,'queued')", (chapter['id'],))
            count += 1
    return dict(queued=count, relocated=relocated)
