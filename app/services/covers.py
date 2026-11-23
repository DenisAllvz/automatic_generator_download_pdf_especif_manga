"""Small local thumbnails; large original covers never become grid pixmaps."""
import io
from pathlib import Path
from PIL import Image, ImageOps
from app.infrastructure.filesystem import atomic_bytes
from app.services.integrity import inspect_image
from app.infrastructure.database import timestamp


def save_cover(db, mid, content, data_root):
    inspect_image(content)
    with Image.open(io.BytesIO(content)) as source:
        source.thumbnail((320, 480))
        with ImageOps.exif_transpose(source) as oriented:
            with oriented.convert('RGB') as rgb:
                stream = io.BytesIO()
                rgb.save(stream, 'JPEG', quality=86)
    target = Path(data_root) / 'covers' / f'{mid}.jpg'
    atomic_bytes(target, stream.getvalue())
    db.execute('UPDATE mangas SET cover_file=?,updated=? WHERE id=?', (str(target), timestamp(), mid))
    return str(target)


def cover_from_pdf(db, manga, data_root):
    """Offline fallback, rendered as a tiny thumbnail rather than an entire page image."""
    if manga['cover_file'] and Path(manga['cover_file']).is_file():
        return True
    from PySide6.QtGui import QGuiApplication
    if QGuiApplication.instance() is None:
        return False
    from PySide6.QtCore import Qt, QBuffer, QIODevice, QByteArray
    from PySide6.QtPdf import QPdfDocument
    from app.services.reading import Reading
    chapter = next((c for c in Reading(db).chapters(manga['id']) if c['available']), None)
    if chapter is None:
        return False
    document = QPdfDocument()
    try:
        document.load(chapter['pdf'])
        if document.status() != QPdfDocument.Status.Ready:
            return False
        image = document.render(0, document.pagePointSize(0).scaled(320, 480, Qt.AspectRatioMode.KeepAspectRatio).toSize())
        if image.isNull():
            return False
        output = QByteArray()
        buffer = QBuffer(output)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not image.save(buffer, 'JPEG', 86):
            return False
        buffer.close()
        target = Path(data_root) / 'covers' / f"pdf-{manga['id']}.jpg"
        atomic_bytes(target, bytes(output))
        db.execute('UPDATE mangas SET cover_file=?,updated=? WHERE id=?', (str(target), timestamp(), manga['id']))
        return True
    finally:
        document.close()


async def refresh_covers(db, data_root, settings, cancel=None):
    import asyncio
    from dataclasses import replace
    from urllib.parse import urljoin
    from bs4 import BeautifulSoup
    from app.infrastructure.http_client import HttpClient
    result = dict(saved=0, failed=[])
    async def request(coro):
        pending = asyncio.create_task(asyncio.wait_for(coro, 10))
        try:
            while not pending.done():
                if cancel and cancel.is_set():
                    return None
                await asyncio.wait({pending}, timeout=.1)
            return pending.result()
        finally:
            if not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
    async with HttpClient(replace(settings, timeout=8, retries=1)) as client:
        for manga in db.mangas():
            if cancel and cancel.is_set():
                break
            if manga['cover_file'] and Path(manga['cover_file']).is_file() and not Path(manga['cover_file']).name.startswith('pdf-'):
                continue
            try:
                local = next((p for p in Path(manga['folder']).glob('cover.*') if p.is_file()), None)
                if local:
                    content = local.read_bytes()
                else:
                    url = manga['cover']
                    if not url and manga['url']:
                        html = await request(client.text(manga['url']))
                        if html is None:
                            break
                        soup = BeautifulSoup(html, 'html.parser')
                        image = soup.select_one('meta[property="og:image"], meta[name="twitter:image"]')
                        url = urljoin(manga['url'], image.get('content', '')) if image else ''
                    if not url:
                        result['saved'] += int(cover_from_pdf(db, manga, data_root))
                        continue
                    content = await request(client.image(url, manga['url'] or ''))
                    if content is None:
                        break
                save_cover(db, manga['id'], content, data_root)
                result['saved'] += 1
            except Exception as exc:
                try:
                    fallback = cover_from_pdf(db, manga, data_root)
                except Exception:
                    fallback = False
                if fallback:
                    result['saved'] += 1
                else:
                    result['failed'].append(dict(title=manga['title'], error=str(exc)))
    return result
