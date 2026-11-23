import json
from pathlib import Path
import pytest
from app.models import Manga, Chapter
from app.infrastructure.filesystem import atomic_bytes, atomic_json
from app.infrastructure.database import Database
from app.services.integrity import inspect_image
from app.services.library import Library
from app.services.download_manager import DownloadManager
from app.extractors.registry import Registry
from app.core.config import Settings


async def test_acceptance_C_200_validated_only_50_downloaded(tmp_path, image_bytes):
    settings = Settings(library=str(tmp_path / "library"))
    db = Database(tmp_path / "db.sqlite3")
    library = Library(db, Path(settings.library))
    manga = Manga("Obra 250", "https://example.org/manga", chapters=[Chapter(f"Capítulo {n}", f"https://example.org/chapter-{n}") for n in range(1, 251)])
    mid, ids = library.add(manga)
    chapters = db.chapters(mid)
    info = inspect_image(image_bytes)
    info.pop("extension")
    for chapter in chapters[:200]:
        folder = Path(chapter["folder"])
        atomic_bytes(folder / "0001.png", image_bytes)
        atomic_json(folder / "manifest.json", dict(expected=1, authoritative=False,
            pages=[dict(file="0001.png", url=chapter["url"] + "/image.png", **info)]))
        db.execute("UPDATE chapters SET status='downloaded',completed=1,expected=1 WHERE id=?", (chapter["id"],))
    library.enqueue(ids)
    class Source:
        calls = []
        async def text(self, url):
            return f'<div id="reader"><img src="{url}/image.png"></div>'
        async def image(self, url, referer=""):
            self.calls.append(url)
            return image_bytes
    source = Source()
    manager = DownloadManager(db, settings)
    manager.running = True
    for task in db.tasks():
        db.execute("UPDATE tasks SET status='running' WHERE id=?", (task["id"],))
        await manager.download(task, source, Registry(source))
    assert len(source.calls) == 50
    assert all(task["status"] == "complete" for task in db.tasks())
    assert sum(task["skipped"] for task in db.tasks()) == 200
    assert sum(chapter["completed"] for chapter in db.chapters(mid)) == 250


def test_database_newer_schema_rejected(tmp_path):
    db = Database(tmp_path / "db.sqlite3")
    db.execute("PRAGMA user_version=99")
    with pytest.raises(RuntimeError, match="mais nova"):
        Database(db.path)


def test_natural_order_ignores_old_priority_and_removal_preserves_chapter(setup_library):
    settings, db, library, mid, ids = setup_library
    _, new = library.add(Manga("Obra Á", "https://example.org/manga/a", chapters=[
        Chapter("Capítulo 10", "https://example.org/chapter-10"),
        Chapter("Capítulo 2", "https://example.org/chapter-2")]))
    library.enqueue(new)
    db.execute("UPDATE tasks SET priority=-100 WHERE chapter_id=?", (new[0],))
    assert [t['chapter'] for t in db.tasks()] == ['Capítulo 1', 'Capítulo 2', 'Capítulo 10']
    manager = DownloadManager(db, settings)
    task = db.tasks()[1]
    manager.command(task['id'], 'remove')
    assert len(db.tasks()) == 2
    assert len(db.chapters(mid)) == 3


async def test_scheduler_finishes_chapters_in_natural_order_even_with_old_concurrency(setup_library):
    import asyncio
    settings, db, library, mid, ids = setup_library
    _, more = library.add(Manga('Obra Á', 'https://example.org/manga/a', chapters=[
        Chapter('Capítulo 10', 'https://example.org/chapter-10'),
        Chapter('Capítulo 2', 'https://example.org/chapter-2')]))
    library.enqueue(more)
    settings.concurrent_tasks = 4
    settings.download_workers = 1
    class Client:
        def __init__(self, settings): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
    manager = DownloadManager(db, settings, client_factory=Client)
    started, finished = [], []
    async def download(task, client, registry):
        assert len(started) == len(finished)
        started.append(task['chapter'])
        await asyncio.sleep(.01)
        db.execute("UPDATE tasks SET status='complete' WHERE id=?", (task['id'],))
        finished.append(task['chapter'])
        if len(finished) == 3:
            manager.running = False
    manager.download = download
    await asyncio.wait_for(manager.run(), 3)
    assert started == finished == ['Capítulo 1', 'Capítulo 2', 'Capítulo 10']
