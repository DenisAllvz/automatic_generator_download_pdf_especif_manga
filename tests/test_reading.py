import asyncio
from pathlib import Path
import pytest
from PIL import Image
from app.models import Manga, Chapter
from app.services.reading import Reading
from app.services.covers import save_cover
from app.services.export import pdf_target, has_current_pdf
from app.infrastructure.catalog import read_manifest
from tests.test_downloads import Client, perform


def test_bulk_read_rename_persists_and_new_chapter_removes_completion(setup_library):
    _, db, library, mid, ids = setup_library
    reading = Reading(db)
    reading.mark(ids, True)
    assert db.mangas()[0]['read_count'] == db.mangas()[0]['chapters'] == 1
    reading.rename(mid, 'Meu nome')
    library.add(Manga('Nome do site', 'https://example.org/manga/a', chapters=[
        Chapter('Capítulo 1', 'https://example.org/chapter-1'),
        Chapter('Capítulo 2', 'https://example.org/chapter-2')]))
    manga = db.mangas()[0]
    assert manga['title'] == 'Meu nome'
    assert manga['read_count'] == 1 and manga['chapters'] == 2
    reading.mark(ids, False)
    assert db.mangas()[0]['read_count'] == 0


def test_progress_is_independent_of_download_state_and_survives_reopen(setup_library):
    _, db, _, mid, ids = setup_library
    Reading(db).progress(ids[0], 4, 10, 0, 98, 1.25)
    from app.infrastructure.database import Database
    reopened = Database(db.path).chapters(mid)[0]
    assert reopened['read_page'] == 4 and reopened['read_y'] == 98 and reopened['read_zoom'] == 1.25
    assert reopened['status'] == 'pending' and not reopened['is_read']
    Reading(db).progress(ids[0], 9, 10, finished=True)
    assert db.chapters(mid)[0]['is_read']


def test_cover_is_a_small_local_image(setup_library, image_bytes, tmp_path):
    _, db, _, mid, _ = setup_library
    path = save_cover(db, mid, image_bytes, tmp_path)
    assert db.mangas()[0]['cover_file'] == path
    with Image.open(path) as cover:
        assert cover.width <= 320 and cover.height <= 480


async def test_pdf_only_deletes_images_and_reuses_pdf_offline(setup_library, image_bytes):
    settings, db, library, mid, ids = setup_library
    settings.keep_images = False
    await perform(settings, db, Client(image_bytes))
    chapter = db.chapters(mid)[0]
    folder = Path(chapter['folder'])
    assert pdf_target(chapter).is_file() and has_current_pdf(chapter)
    assert read_manifest(folder)['pdf_only']
    assert not folder.exists()
    class Offline(Client):
        async def text(self, url):
            raise AssertionError('PDF pronto não deve consultar rede')
    library.enqueue(ids)
    await perform(settings, db, Offline(image_bytes))
    assert db.tasks()[-1]['status'] == 'complete'
    from app.services.integrity import diagnose
    assert diagnose(folder)['issues'] == []


async def test_failed_pdf_keeps_images(setup_library, image_bytes, monkeypatch):
    settings, db, _, mid, _ = setup_library
    settings.keep_images = False
    import app.services.download_manager as module
    def fail(chapter):
        raise OSError('Disco cheio')
    monkeypatch.setattr(module, 'ensure_pdf', fail)
    await perform(settings, db, Client(image_bytes))
    folder = Path(db.chapters(mid)[0]['folder'])
    assert len(list(folder.glob('*.png'))) == 2
    assert db.tasks()[0]['status'] == 'failed'


async def test_parallel_downloads_are_bounded_and_start_in_natural_order(setup_library):
    settings, db, library, _, _ = setup_library
    _, more = library.add(Manga('Obra Á', 'https://example.org/manga/a', chapters=[
        Chapter('Capítulo 10', 'https://example.org/10'), Chapter('Capítulo 2', 'https://example.org/2')]))
    library.enqueue(more)
    from app.services.download_manager import DownloadManager
    class Client:
        def __init__(self, settings): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
    manager = DownloadManager(db, settings, client_factory=Client)
    active, peak = 0, 0
    started, finished = [], []
    async def download(task, *args):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        started.append(task['chapter'])
        await asyncio.sleep(.25)
        active -= 1
        finished.append(task['chapter'])
        db.execute("UPDATE tasks SET status='complete' WHERE id=?", (task['id'],))
        if len(finished) == 3:
            manager.running = False
    manager.download = download
    await asyncio.wait_for(manager.run(), 4)
    assert peak == 2
    assert started == ['Capítulo 1', 'Capítulo 2', 'Capítulo 10']


def test_older_progress_does_not_override_later_mark_unread(setup_library):
    _, db, _, mid, ids = setup_library
    reading = Reading(db)
    reading.mark(ids, False, updated='2026-11-12T12:00:02+00:00')
    reading.progress(ids[0], 4, 5, finished=True, updated='2026-11-12T12:00:01+00:00')
    chapter = db.chapters(mid)[0]
    assert not chapter['is_read'] and chapter['read_total'] == 0


async def test_import_pdf_only_work_does_not_duplicate_registered_chapters(setup_library, image_bytes):
    settings, db, library, mid, _ = setup_library
    settings.keep_images = False
    await perform(settings, db, Client(image_bytes))
    folder = Path(db.mangas()[0]['folder'])
    assert library.import_folder(folder / 'PDF') == 0
    assert len(db.mangas()) == 1 and len(db.chapters(mid)) == 1


def test_migrate_v1_preserves_chapters_and_old_read_position(setup_library):
    _, db, _, mid, ids = setup_library
    db.execute('UPDATE chapters SET read_page=7 WHERE id=?', (ids[0],))
    db.execute('PRAGMA user_version=1')
    from app.infrastructure.database import Database
    migrated = Database(db.path)
    assert migrated.query('PRAGMA user_version')[0]['user_version'] == 2
    assert migrated.chapters(mid)[0]['read_page'] == 7


async def test_pdf_conversion_stays_serial_with_parallel_downloads(setup_library, monkeypatch):
    import threading
    import time
    settings, db, library, _, _ = setup_library
    _, new = library.add(Manga('Obra B', 'https://example.org/b', chapters=[Chapter('Capítulo 1', 'https://example.org/b/1')]))
    library.enqueue(new)
    db.execute("UPDATE tasks SET status='running'")
    import app.services.download_manager as module
    active, peak = 0, 0
    lock = threading.Lock()
    def convert(chapter):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(.08)
        with lock:
            active -= 1
    monkeypatch.setattr(module, 'ensure_pdf', convert)
    manager = module.DownloadManager(db, settings)
    manager.running = True
    chapters = {c['id']: c for c in db.query('SELECT * FROM chapters')}
    await asyncio.gather(*(manager.convert_pdf(t['id'], chapters[t['chapter_id']]) for t in db.tasks()))
    assert peak == 1


async def test_real_parallel_pipeline_finishes_two_pdfs_without_image_cache(setup_library, image_bytes):
    settings, db, library, mid, _ = setup_library
    settings.keep_images = False
    _, new = library.add(Manga('Obra Á', 'https://example.org/manga/a', chapters=[
        Chapter('Capítulo 1', 'https://example.org/chapter-1'),
        Chapter('Capítulo 2', 'https://example.org/chapter-2')]))
    library.enqueue(new)
    active, peak = 0, 0
    class Source(Client):
        def __init__(self, settings): super().__init__(image_bytes)
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def image(self, *args, **kwargs):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(.08)
                return await super().image(*args, **kwargs)
            finally:
                active -= 1
    from app.services.download_manager import DownloadManager
    manager = DownloadManager(db, settings, client_factory=Source)
    def notify():
        if all(t['status'] == 'complete' for t in db.tasks()):
            manager.running = False
    manager.notify = notify
    await asyncio.wait_for(manager.run(), 5)
    assert peak == 2
    assert all(t['status'] == 'complete' for t in db.tasks())
    for chapter in db.chapters(mid):
        assert pdf_target(chapter).is_file() and not Path(chapter['folder']).exists()
