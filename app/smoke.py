"""Offline frozen-build exercise. Only called with --smoke-test isolated data."""
import io
import json
from pathlib import Path
from PIL import Image
from app.models import Manga, Chapter
from app.services.library import Library
from app.services.integrity import inspect_image, diagnose
from app.services.export import export_chapter, export_chapters
from app.infrastructure.filesystem import atomic_bytes, atomic_json


def exercise(window, root: Path) -> dict:
    library = Library(window.db, root / "demo-library")
    manga = Manga("Coleção de demonstração", "https://example.org/demo", description="Teste offline de recursos e persistência.",
                  chapters=[Chapter("Capítulo 1", "https://example.org/demo/chapter-1")])
    mid, _ = library.add(manga)
    chapter = window.db.chapters(mid)[0]
    folder = Path(chapter["folder"])
    records = []
    for index, color in enumerate(("#366be0", "#20a898"), 1):
        stream = io.BytesIO()
        picture = Image.new("RGB", (240, 360), color)
        from PIL import ImageDraw
        draw = ImageDraw.Draw(picture)
        draw.rectangle((30, 40, 210, 300), outline="white", width=6)
        draw.text((100, 165), str(index), fill="white", font_size=48)
        picture.save(stream, "PNG")
        data = stream.getvalue()
        info = inspect_image(data)
        info.pop("extension")
        name = f"{index:04d}.png"
        atomic_bytes(folder / name, data)
        records.append(dict(file=name, url=f"https://example.org/{index}.png", **info))
    atomic_json(folder / "manifest.json", dict(expected=2, authoritative=False, pages=records))
    window.db.execute("UPDATE chapters SET status='downloaded',completed=2,expected=2 WHERE id=?", (chapter["id"],))
    chapter = window.db.chapters(mid)[0]
    window.selected_manga = window.db.query("SELECT * FROM mangas WHERE id=?", (mid,))[0]
    # Write new exports only, allowing repeated smoke invocations without overwrites.
    import time
    prefix = root / f"export-{time.time_ns()}"
    cbz, pdf = prefix.with_suffix(".cbz"), prefix.with_suffix(".pdf")
    export_chapter(folder, cbz, "cbz")
    export_chapter(folder, pdf, "pdf")
    batch = export_chapters([dict(chapter), dict(chapter, id=f"{chapter['id']}-batch")], prefix / "batch", "pdf")
    assert len(batch['created']) == 2 and not batch['failed']
    import pikepdf
    with pikepdf.open(pdf) as document:
        assert len(document.pages) == 2
    import zipfile
    with zipfile.ZipFile(cbz) as archive:
        assert len(archive.namelist()) == 2
    assert diagnose(folder)["status"] == "unverifiable"
    from app.services.export import ensure_pdf, pdf_target
    from app.services.download_manager import DownloadManager
    import asyncio
    library.enqueue([chapter['id']])
    task = next(t for t in window.db.tasks() if t['chapter_id'] == chapter['id'] and t['status'] == 'queued')
    window.db.execute("UPDATE tasks SET status='running' WHERE id=?", (task['id'],))
    manager = DownloadManager(window.db, window.settings)
    manager.running = True
    asyncio.run(manager.download(task, None, None))
    assert next(t for t in window.db.tasks() if t['id'] == task['id'])['status'] == 'complete'
    automatic = pdf_target(chapter)
    assert automatic.exists()
    assert ensure_pdf(chapter) == automatic
    assert not list(folder.parent.rglob('*.json'))
    reports = window.reports.finish_ready()
    assert reports and Path(reports[-1]['file']).is_file()
    assert not window.db.tasks()
    from app.services.covers import save_cover
    save_cover(window.db, mid, data, root)
    window.reading.mark([chapter['id']], True)
    assert window.db.mangas()[0]['read_count'] == 1
    from app.ui.reader import Reader
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QSize
    reader = Reader()
    reader.open_chapter(dict(window.db.chapters(mid)[0], pdf=str(automatic)))
    QApplication.processEvents()
    assert reader.doc.pageCount() == 2
    assert not reader.doc.render(0, QSize(240, 360)).isNull()
    reader.close()
    reader.deleteLater()
    from app.services.drive_sync import DriveSync
    from app.infrastructure.drive_auth import DriveVault
    from app.infrastructure.google_drive import FOLDER
    vault = DriveVault(root)
    vault.save({'client': {'client_id': 'smoke.apps.googleusercontent.com', 'client_secret': 'fixture-secret'},
                'token': {'refresh_token': 'fixture-token'}})
    assert b'fixture-token' not in vault.path.read_bytes()
    assert vault.load()['token']['refresh_token'] == 'fixture-token'
    vault.disconnect()
    class OfflineDrive:
        def __init__(self):
            self.items = [dict(id='rootfolder', name='Teste offline', mimeType=FOLDER)]
            self.uploads = 0
        def check_cancel(self): pass
        def get_folder(self, ident): return self.items[0]
        def list_children(self, parent): return [r for r in self.items if parent in r.get('parents', [])]
        def create_folder(self, parent, name, mid):
            row = dict(id='workfolder', name=name, mimeType=FOLDER, parents=[parent], appProperties={'mmWork':mid})
            self.items.append(row)
            return row
        def upload(self, parent, source, progress):
            row = dict(id='pdffile', name=Path(source['path']).name, parents=[parent], mimeType='application/pdf',
                       size=str(source['size']), md5Checksum=source['md5'], appProperties={'mmChapter':source['cid']})
            self.items.append(row)
            self.uploads += 1
            return row
    remote = OfflineDrive()
    sync = DriveSync(window.db, remote)
    pending = sync.plan('rootfolder')
    assert pending['missing'] == 1
    assert sync.send(pending)['uploaded'] == 1
    ready = sync.plan('rootfolder')
    assert ready['existing'] == 1 and ready['missing'] == 0 and remote.uploads == 1
    window.refresh_queue()
    return dict(drive_sync_offline=True, drive_encryption=True, reader=True, reading_state=True, cover=True, pdf_only=not folder.exists(),
                clean_metadata=True, download_log=True, queue_cleaned=True, automatic_pdf=True, batch_pdf_count=2, cbz=True, pdf_pages=2,
                integrity="unverifiable", manga_persisted=True, pdf_sample=str(pdf))


async def exercise_source(root, url):
    """Opt-in live validation using isolated data; never runs during ordinary use."""
    from app.core.config import Settings
    from app.infrastructure.database import Database
    from app.infrastructure.http_client import HttpClient
    from app.extractors.registry import Registry
    from app.services.download_manager import DownloadManager
    import pikepdf
    settings = Settings(library=str(root / "source-library"))
    db = Database(root / "source-check.sqlite3")
    library = Library(db, Path(settings.library))
    async with HttpClient(settings) as client:
        extractor = Registry(client).select(url)
        manga = await extractor.get_manga_info(url)
        if not manga.chapters:
            raise RuntimeError("A fonte não retornou capítulos.")
        chapter = next((c for c in manga.chapters if c.language == "pt-br"), manga.chapters[0])
        mid, ids = library.add(Manga(manga.title, manga.url, manga.description, chapters=[chapter]))
        library.enqueue(ids)
        task = db.tasks()[0]
        db.execute("UPDATE tasks SET status='running' WHERE id=?", (task["id"],))
        manager = DownloadManager(db, settings)
        manager.running = True
        await manager.download(task, client, Registry(client))
        assert db.tasks()[0]["status"] == "complete", db.tasks()[0]["error"]
    local = db.chapters(mid)[0]
    target = root / "source-check.pdf"
    import shutil
    from app.services.export import pdf_target
    shutil.copy2(pdf_target(local), target)
    with pikepdf.open(target) as pdf:
        count = len(pdf.pages)
    assert count == local["expected"] and count > 0
    return dict(title=manga.title, chapters=len(manga.chapters), chapter=chapter.title,
                status=local["status"], pdf_pages=count)
