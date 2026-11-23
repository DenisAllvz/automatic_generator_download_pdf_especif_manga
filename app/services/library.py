import json
from pathlib import Path
from urllib.parse import urlsplit
from app.infrastructure.database import Database, timestamp
from app.infrastructure.filesystem import atomic_json, contained, identity, safe_name, chapter_key
from app.models import Manga
from app.infrastructure.catalog import Catalog, read_metadata, read_manifest, CATALOG_NAME
from app.services.integrity import diagnose, inspect_image


class Library:
    def __init__(self, database: Database, root: Path, chapter_pattern: str = "{title}"):
        self.db, self.root, self.chapter_pattern = database, root, chapter_pattern

    def repair_site_titles(self):
        from app.extractors.titles import is_site_title, title_from_work_url, clean_chapter_title
        for manga in self.db.mangas():
            if manga["url"] and is_site_title(manga["title"], manga["url"]):
                title = title_from_work_url(manga["url"])
                if title:
                    # Only metadata changes: chapter identities, folders and tasks survive.
                    self.db.execute("UPDATE mangas SET title=? WHERE id=?", (title, manga["id"]))
            if manga['url'] and 'mangalivre.' in (urlsplit(manga['url']).hostname or ''):
                changes = [(clean_chapter_title(c['title']), c['id']) for c in self.db.chapters(manga['id'])
                           if clean_chapter_title(c['title']) != c['title']]
                if changes:
                    with self.db.connection() as connection:
                        connection.executemany('UPDATE chapters SET title=? WHERE id=?', changes)

    def add(self, manga: Manga) -> tuple[str, list[str]]:
        mid = identity(manga.url)
        existing = self.db.query("SELECT * FROM mangas WHERE id=?", (mid,))
        if existing and existing[0]['custom_title']:
            from dataclasses import replace
            manga = replace(manga, title=existing[0]['title'])
        previous_chapters = self.db.chapters(mid) if existing else []
        incoming = {c.url: c.title for c in manga.chapters}
        changes = dict(renamed=[dict(url=c["url"], old=c["title"], new=incoming[c["url"]])
                               for c in previous_chapters if c["url"] in incoming and incoming[c["url"]] != c["title"]],
                       no_longer_listed=[c["url"] for c in previous_chapters if c["url"] and c["url"] not in incoming])
        folder = Path(existing[0]["folder"]) if existing else contained(self.root, safe_name(manga.title))
        if not existing and (folder.exists() or self.db.query('SELECT id FROM mangas WHERE folder=?', (str(folder),))):
            folder = contained(self.root, safe_name(manga.title) + '-' + mid)
        folder.mkdir(parents=True, exist_ok=True)
        with self.db.connection() as db:
            db.execute("""INSERT INTO mangas(id,title,url,folder,description,cover,updated) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET title=excluded.title, description=excluded.description,
                cover=excluded.cover, updated=excluded.updated""",
                       (mid, manga.title, manga.url, str(folder), manga.description, manga.cover, timestamp()))
            new = []
            for chapter in manga.chapters:
                cid = identity(chapter.url)
                if not db.execute("SELECT 1 FROM chapters WHERE id=?", (cid,)).fetchone():
                    new.append(cid)
                    number = chapter_key(chapter.title)[1]
                    name = self.chapter_pattern.format(title=chapter.title, number=str(number).zfill(4))
                    chapter_folder = contained(folder, safe_name(name) + "-" + cid)
                    db.execute("INSERT INTO chapters(id,manga_id,title,url,folder) VALUES(?,?,?,?,?)",
                               (cid, mid, chapter.title, chapter.url, str(chapter_folder)))
                else:
                    db.execute("UPDATE chapters SET title=? WHERE id=?", (chapter.title, cid))
        catalog = Catalog(folder)
        if (folder / "metadata.json").exists():
            catalog.migrate()
        catalog.put("metadata", "", dict(title=manga.title, url=manga.url,
            description=manga.description, cover_url=manga.cover,
            listing_complete=manga.listing_complete, changes=changes, updated=timestamp()))
        return mid, new

    def enqueue(self, chapter_ids: list[str], *, skip_complete=False):
        skipped = 0
        if skip_complete:
            from app.services.export import has_current_pdf
            eligible = []
            for cid in dict.fromkeys(chapter_ids):
                rows = self.db.query('SELECT * FROM chapters WHERE id=?', (cid,))
                if rows and has_current_pdf(rows[0]):
                    skipped += 1
                else:
                    eligible.append(cid)
            chapter_ids = eligible
        added = 0
        with self.db.connection() as db:
            for cid in chapter_ids:
                added += db.execute("INSERT OR IGNORE INTO tasks(chapter_id,updated) VALUES(?,?)", (cid, timestamp())).rowcount
        return dict(added=added, skipped=skipped)

    def diagnostic(self) -> list[dict]:
        results = []
        for manga in self.db.mangas():
            for chapter in self.db.chapters(manga["id"]):
                if chapter["status"] == "legacy":
                    result = dict(status="unverifiable", issues=["PDF legado: páginas e fonte não comprovadas"], pages=0)
                else:
                    result = diagnose(Path(chapter["folder"]))
                    self.db.execute("UPDATE chapters SET status=?,completed=?,expected=? WHERE id=?",
                                    (result["status"], result.get("valid_pages", 0), result.get("expected", 0), chapter["id"]))
                results.append(dict(manga=manga["title"], chapter=chapter["title"], id=chapter["id"], **result))
        return results

    def import_folder(self, root: Path) -> int:
        """Read-only toward existing content: never rename or delete user files."""
        root = root.resolve()
        if root.name == 'PDF' and (root.parent / CATALOG_NAME).is_file():
            root = root.parent
        if not root.is_dir():
            raise ValueError("Selecione uma pasta existente")
        count = 0
        groups = [root] if any(root.glob("*.pdf")) or (root / "metadata.json").exists() or (root / CATALOG_NAME).exists() else [p for p in root.iterdir() if p.is_dir() and not p.is_symlink()]
        for folder in groups:
            if folder.is_symlink():
                continue
            try:
                metadata = read_metadata(folder)
            except (ValueError, OSError):
                metadata = {}
            # Import remains local; metadata is untrusted and never enables network access.
            registered = self.db.query('SELECT id FROM mangas WHERE folder=?', (str(folder),))
            mid = registered[0]['id'] if registered else identity("local:" + str(folder))
            from app.services.reading import Reading
            known_pdfs = {str(Reading(self.db).pdf(c).resolve()) for c in self.db.chapters(mid)}
            with self.db.connection() as db:
                db.execute("INSERT OR IGNORE INTO mangas(id,title,folder,updated) VALUES(?,?,?,?)",
                           (mid, metadata.get("title", folder.name), str(folder), timestamp()))
                candidates = [p for p in folder.iterdir() if not p.is_symlink() and (p.suffix.lower() == ".pdf" or p.is_dir())]
                pdfs = folder / 'PDF'
                if pdfs.is_dir() and not pdfs.is_symlink():
                    candidates += [p for p in pdfs.glob('*.pdf') if not p.is_symlink()]
                for path in candidates:
                    if path.is_file() and str(path.resolve()) in known_pdfs:
                        continue
                    if path.is_dir() and read_manifest(path) is None and not any(p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif") for p in path.iterdir()):
                        continue
                    cid = identity("local:" + str(path))
                    status = "legacy" if path.is_file() else diagnose(path)["status"]
                    changed = db.execute("INSERT OR IGNORE INTO chapters(id,manga_id,title,folder,status) VALUES(?,?,?,?,?)",
                                        (cid, mid, path.stem, str(path), status)).rowcount
                    count += changed
        return count

    def storage(self) -> int:
        roots = {Path(m["folder"]) for m in self.db.mangas()}
        return sum(p.stat().st_size for root in roots if root.exists() for p in root.rglob("*") if p.is_file() and not p.is_symlink())
