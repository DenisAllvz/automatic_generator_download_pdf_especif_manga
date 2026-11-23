import asyncio
import json
from pathlib import Path
import pytest
from app.core.exceptions import DownloadError
from app.infrastructure.database import Database
from app.services.download_manager import DownloadManager
from app.services.integrity import diagnose
from app.infrastructure.catalog import read_manifest
from app.services.export import export_chapter
from app.extractors.registry import Registry


class Client:
    def __init__(self, image, failure=None, hook=None):
        self.image_data = image
        self.calls = []
        self.failure = failure
        self.hook = hook

    async def text(self, url):
        return '<div id="reader"><img src="/1.png"><img src="/2.png"></div>'

    async def image(self, url, referer=""):
        self.calls.append(url)
        if self.hook:
            await self.hook(url)
        if self.failure and url.endswith("2.png"):
            raise self.failure
        # Distinct image content avoids false duplicate-content diagnostics.
        if url.endswith("2.png"):
            import io
            from PIL import Image
            stream = io.BytesIO()
            Image.new("RGB", (32, 64), "green").save(stream, "PNG")
            return stream.getvalue()
        return self.image_data


async def perform(settings, db, client):
    manager = DownloadManager(db, settings)
    manager.running = True
    task = db.tasks()[-1]
    db.execute("UPDATE tasks SET status='running' WHERE id=?", (task["id"],))
    await manager.download(task, client, Registry(client))
    return manager


async def test_success_resume_corruption_cbz(setup_library, image_bytes, tmp_path):
    settings, db, library, mid, ids = setup_library
    client = Client(image_bytes)
    await perform(settings, db, client)
    assert db.tasks()[0]["status"] == "complete"
    chapter = db.chapters(mid)[0]
    folder = Path(chapter["folder"])
    assert diagnose(folder)["status"] == "unverifiable"
    library.enqueue(ids)
    cached = Client(image_bytes)
    await perform(settings, db, cached)
    assert cached.calls == []
    manifest = read_manifest(folder)
    (folder / manifest["pages"][1]["file"]).write_bytes(b"corrupt")
    assert diagnose(folder)["status"] == "incomplete"
    library.enqueue(ids)
    repair = Client(image_bytes)
    await perform(settings, db, repair)
    assert repair.calls == ["https://example.org/2.png"]
    target = tmp_path / "chapter.cbz"
    export_chapter(folder, target, "cbz")
    import zipfile
    with zipfile.ZipFile(target) as archive:
        assert archive.namelist() == ["0001.png", "0002.png"]
        assert archive.read("0001.png") == image_bytes


async def test_failure_restart_only_missing_and_detailed_error(setup_library, image_bytes):
    settings, db, library, mid, ids = setup_library
    client = Client(image_bytes, DownloadError("Falha temporária", 500, 3))
    await perform(settings, db, client)
    task = db.tasks()[0]
    assert task["status"] == "failed" and task["done"] == 1
    error = db.query("SELECT * FROM errors")[0]
    assert error["page"] == 2 and error["attempts"] == 3 and error["http_status"] == 500
    db = Database(db.path)
    manager = DownloadManager(db, settings)
    manager.command(task["id"], "retry")
    cached = Client(image_bytes)
    await perform(settings, db, cached)
    assert cached.calls == ["https://example.org/2.png"]


async def test_pause_and_cancel_preserve_files(setup_library, image_bytes):
    settings, db, library, mid, ids = setup_library
    manager = DownloadManager(db, settings)
    manager.running = True
    task = db.tasks()[0]
    db.execute("UPDATE tasks SET status='running' WHERE id=?", (task["id"],))
    async def hook(url):
        if url.endswith("2.png"):
            manager.command(task["id"], "pause")
    client = Client(image_bytes, hook=hook)
    await manager.download(task, client, Registry(client))
    assert db.tasks()[0]["status"] == "paused"
    folder = Path(db.chapters(mid)[0]["folder"])
    assert len(list(folder.glob("*.png"))) == 1
    manager.command(task["id"], "resume")
    await perform(settings, db, Client(image_bytes))
    assert db.tasks()[0]["status"] == "complete"
    manager.command(task["id"], "cancel")
    assert len(list(folder.glob("*.png"))) == 2


async def test_invalid_image_does_not_complete(setup_library):
    settings, db, library, mid, ids = setup_library
    await perform(settings, db, Client(b"<html>not image</html>"))
    assert db.tasks()[0]["status"] == "failed"
    assert not list(Path(db.chapters(mid)[0]["folder"]).glob("*.png"))


def test_recovery_and_no_duplicate_active_tasks(setup_library):
    settings, db, library, mid, ids = setup_library
    library.enqueue(ids)
    assert len(db.tasks()) == 1
    db.execute("UPDATE tasks SET status='running'")
    reopened = Database(db.path)
    assert reopened.tasks()[0]["status"] == "paused"
    assert reopened.chapters(mid)[0]["url"]


def test_import_pdf_does_not_delete_small_files(tmp_path):
    from app.services.library import Library
    folder = tmp_path / "legacy"
    folder.mkdir()
    pdf = folder / "Capítulo 1.pdf"
    pdf.write_bytes(b"%PDF-small")
    library = Library(Database(tmp_path / "db.sqlite3"), tmp_path / "new")
    assert library.import_folder(folder) == 1
    assert library.import_folder(folder) == 0
    assert pdf.read_bytes() == b"%PDF-small"
    assert library.diagnostic()[0]["status"] == "unverifiable"
