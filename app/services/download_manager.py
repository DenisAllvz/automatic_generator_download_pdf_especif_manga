import asyncio
import json
import logging
import shutil
import time
from pathlib import Path

from app.core.exceptions import MangaError, TaskInterrupted, DownloadError, ExtractionError
from app.core.security import safe_url, scrub
from app.extractors.registry import Registry
from app.infrastructure.database import timestamp
from app.infrastructure.filesystem import atomic_bytes, atomic_json, contained, identity
from app.infrastructure.http_client import HttpClient
from app.services.integrity import inspect_image, valid_page
from app.services.export import ensure_pdf, local_pages, has_current_pdf
from app.infrastructure.catalog import read_manifest, save_manifest
from app.infrastructure.filesystem import chapter_key


class DownloadManager:
    def __init__(self, database, settings, notify=lambda: None, client_factory=HttpClient):
        self.db, self.settings, self.notify = database, settings, notify
        self.client_factory = client_factory
        self.loop = None
        self.running = False
        self.active: dict[int, asyncio.Task] = {}
        self.pdf_gate = asyncio.Semaphore(1)

    def command(self, task_id: int, action: str):
        return self.commands([task_id], action)

    def commands(self, task_ids, action):
        if action not in ("pause", "resume", "cancel", "retry", "remove"):
            raise ValueError("Comando inválido")
        allowed = {'pause': ('queued', 'running'), 'resume': ('paused',),
                   'retry': ('failed', 'cancelled'), 'cancel': ('queued','running','paused','failed')}
        state = {"pause": "paused", "resume": "queued", "retry": "queued", "cancel": "cancelled", "remove": "cancelled"}[action]
        changed = []
        with self.db.connection() as db:
            for task_id in dict.fromkeys(task_ids):
                current = db.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
                if not current or (action in allowed and current[0] not in allowed[action]):
                    continue
                if action in ("resume", "retry"):
                    conflict = db.execute("""SELECT 1 FROM tasks WHERE chapter_id=(SELECT chapter_id FROM tasks WHERE id=?)
                        AND id<>? AND status IN ('queued','running','paused')""", (task_id, task_id)).fetchone()
                    if conflict:
                        continue
                if action == 'remove':
                    db.execute('DELETE FROM tasks WHERE id=?', (task_id,))
                else:
                    db.execute("UPDATE tasks SET status=?,speed=0,error='',updated=? WHERE id=?", (state, timestamp(), task_id))
                changed.append(task_id)
        if action in ("pause", "cancel", "remove") and self.loop:
            for task_id in changed:
                self.loop.call_soon_threadsafe(self._interrupt, task_id)
        self.notify()
        return len(changed)

    def _interrupt(self, task_id: int):
        task = self.active.get(task_id)
        if task:
            task.cancel()

    def stop(self):
        self.running = False
        self.db.execute("UPDATE tasks SET status='paused', speed=0 WHERE status='running'")
        if self.loop:
            self.loop.call_soon_threadsafe(lambda: [task.cancel() for task in list(self.active.values())])

    async def run(self):
        self.loop = asyncio.get_running_loop()
        self.running = True
        try:
            async with self.client_factory(self.settings) as client:
                registry = Registry(client)
                while self.running:
                    queued = self.db.tasks(status='queued') if len(self.active) < self.settings.download_workers else []
                    for record in queued:
                        if len(self.active) >= self.settings.download_workers:
                            break
                        if record["id"] in self.active:
                            continue
                        self.db.execute("UPDATE tasks SET status='running',updated=? WHERE id=? AND status='queued'", (timestamp(), record["id"]))
                        task = asyncio.create_task(self.download(record, client, registry))
                        self.active[record["id"]] = task
                    finished = [tid for tid, task in self.active.items() if task.done()]
                    for tid in finished:
                        task = self.active.pop(tid)
                        if not task.cancelled():
                            task.result()  # Unexpected exceptions surface rather than silently disappearing.
                    await asyncio.sleep(.05 if self.active else .3)
        finally:
            for task in self.active.values():
                task.cancel()
            await asyncio.gather(*self.active.values(), return_exceptions=True)
            self.active.clear()
            self.loop = None

    def check_task(self, task_id: int):
        rows = self.db.query("SELECT status FROM tasks WHERE id=?", (task_id,))
        if not self.running or not rows or rows[0]["status"] != "running":
            raise TaskInterrupted("Tarefa interrompida")

    async def download(self, record: dict, client, registry):
        tid, cid = record["id"], record["chapter_id"]
        chapter = self.db.query("SELECT * FROM chapters WHERE id=?", (cid,))[0]
        folder = Path(chapter["folder"])
        index, page_url = None, chapter["url"]
        started, transferred, skipped = time.monotonic(), 0, 0
        try:
            self.check_task(tid)
            try:
                cached_manifest = read_manifest(folder) or {}
            except (OSError, ValueError):
                cached_manifest = {}
            if cached_manifest.get('pdf_only') and has_current_pdf(chapter):
                if not self.settings.keep_images:
                    from app.services.cleanup import cleanup_images
                    await asyncio.to_thread(cleanup_images, chapter)
                manifest = read_manifest(folder)
                count = manifest['expected']
                self.db.execute("UPDATE tasks SET status='complete',done=?,total=?,skipped=?,error='' WHERE id=? AND status='running'", (count, count, count, tid))
                return
            # A complete local manifest permits PDF recovery even when the site is offline.
            if chapter['status'] in ('downloaded', 'verified', 'unverifiable'):
                try:
                    cached = await asyncio.to_thread(local_pages, folder)
                except (MangaError, OSError, ValueError, KeyError):
                    cached = []
                if cached and read_manifest(folder) is not None:
                    self.db.execute('UPDATE tasks SET done=?,total=?,skipped=? WHERE id=?', (len(cached), len(cached), len(cached), tid))
                    await self.convert_pdf(tid, chapter)
                    self.db.execute("UPDATE tasks SET status='complete',speed=0,error='' WHERE id=? AND status='running'", (tid,))
                    return
            if not chapter["url"]:
                raise DownloadError("Capítulo importado sem URL. Adicione a fonte autorizada para baixar.")
            try:
                pages = await registry.select(chapter["url"]).get_chapter_pages(chapter["url"])
            except ExtractionError:
                if not self.settings.render_javascript:
                    raise
                from app.infrastructure.browser_renderer import BrowserRenderer
                pages = await Registry(BrowserRenderer(client)).select(chapter["url"]).get_chapter_pages(chapter["url"])
            self.check_task(tid)
            folder.mkdir(parents=True, exist_ok=True)
            try:
                previous = read_manifest(folder) or {}
            except (OSError, ValueError):
                previous = {}
            old_pages = {p.get("source_key", p.get("url")): p for p in previous.get("cached_pages", []) + previous.get("pages", [])}
            manifest = dict(chapter_url=chapter["url"], expected=len(pages.urls), authoritative=pages.authoritative,
                            pages=[], cached_pages=list(old_pages.values()))
            self.db.execute("UPDATE chapters SET expected=?,status='downloading',authoritative=? WHERE id=?", (len(pages.urls), pages.authoritative, cid))
            self.db.execute("UPDATE tasks SET done=0,total=?,bytes=0,skipped=0 WHERE id=?", (len(pages.urls), tid))
            for index, page_url in enumerate(pages.urls, 1):
                self.check_task(tid)
                source_key = pages.cache_keys[index-1] if pages.cache_keys else page_url
                old = old_pages.get(source_key)
                if old and valid_page(folder, old):
                    page = dict(old, url=page_url)
                    skipped += 1
                else:
                    if shutil.disk_usage(folder).free < self.settings.max_image_mb * 1024**2 + 10 * 1024**2:
                        raise DownloadError("Espaço insuficiente em disco; libere espaço antes de retomar.")
                    content = await client.image(page_url, chapter["url"])
                    self.check_task(tid)
                    info = await asyncio.to_thread(inspect_image, content)
                    name = f"{index:04d}-{identity(source_key)}" + info.pop("extension")
                    path = contained(folder, name)
                    atomic_bytes(path, content)
                    transferred += len(content)
                    page = dict(url=page_url, source_key=source_key, file=name, **info)
                    del content
                manifest["pages"].append(page)
                save_manifest(folder, manifest)
                elapsed = time.monotonic() - started
                self.db.execute("UPDATE tasks SET done=?,bytes=?,speed=?,elapsed=?,skipped=?,updated=? WHERE id=?",
                                (index, transferred, transferred / max(elapsed, .001), elapsed, skipped, timestamp(), tid))
                self.notify()
            self.check_task(tid)
            status = "verified" if pages.authoritative else "downloaded"
            self.db.execute("UPDATE chapters SET status=?,completed=? WHERE id=?", (status, len(pages.urls), cid))
            await self.convert_pdf(tid, chapter)
            self.db.execute("UPDATE tasks SET status='complete',speed=0,error='' WHERE id=? AND status='running'", (tid,))
        except (asyncio.CancelledError, TaskInterrupted):
            self.db.execute("UPDATE chapters SET status='incomplete' WHERE id=? AND status='downloading'", (cid,))
            self.db.execute("UPDATE tasks SET status='paused',speed=0 WHERE id=? AND status='running'", (tid,))
        except (MangaError, OSError, ValueError) as exc:
            message = scrub(str(exc))
            self.db.execute("UPDATE chapters SET status='incomplete' WHERE id=? AND status='downloading'", (cid,))
            self.db.execute("UPDATE tasks SET status='failed',speed=0,error=? WHERE id=?", (message, tid))
            self.db.execute("""INSERT INTO errors(task_id,chapter_id,page,url,category,message,attempts,http_status,created,action)
                VALUES(?,?,?,?,?,?,?,?,?,?)""", (tid, cid, index, safe_url(page_url or ""), type(exc).__name__, message,
                getattr(exc, "attempts", 1), getattr(exc, "status", None), timestamp(), "Confira fonte, acesso e conexão; depois tente novamente."))
            logging.getLogger("manga").warning(json.dumps(dict(event="download_failed", task=tid, chapter=cid,
                page=index, url=safe_url(page_url or ""), category=type(exc).__name__, message=message), ensure_ascii=False))
        finally:
            self.notify()

    async def convert_pdf(self, tid, chapter):
        async with self.pdf_gate:
            await self._convert_pdf(tid, chapter)

    async def _convert_pdf(self, tid, chapter):
        self.check_task(tid)
        self.db.execute("UPDATE tasks SET error='Gerando PDF…',speed=0 WHERE id=?", (tid,))
        self.notify()
        def produce():
            ensure_pdf(chapter)
            if not self.settings.keep_images:
                from app.services.cleanup import cleanup_images
                cleanup_images(chapter)
        conversion = asyncio.create_task(asyncio.to_thread(produce))
        try:
            await asyncio.shield(conversion)
        except asyncio.CancelledError:
            # A Python worker cannot be killed halfway through an atomic file write.
            # Keep its slot occupied until it exits, preventing a concurrent retry.
            await asyncio.gather(conversion, return_exceptions=True)
            raise
        self.check_task(tid)
