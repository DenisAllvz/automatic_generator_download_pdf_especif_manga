import io
import json
from pathlib import Path
import pytest
import pikepdf
from PIL import Image
from app.core.exceptions import DownloadError
from app.extractors.registry import Registry, MangaLivreExtractor
from app.services.export import ensure_pdf, pdf_target, export_chapter
from app.services.recovery import recover_downloads
from tests.test_downloads import Client, perform


async def test_automatic_pdf_and_offline_retry(setup_library, image_bytes, monkeypatch):
    settings, db, library, mid, ids = setup_library
    import app.services.download_manager as downloads
    real = downloads.ensure_pdf
    def fail(chapter):
        raise DownloadError("Falha de conversão simulada")
    monkeypatch.setattr(downloads, 'ensure_pdf', fail)
    source = Client(image_bytes)
    await perform(settings, db, source)
    assert db.tasks()[0]['status'] == 'failed'
    assert db.chapters(mid)[0]['status'] == 'downloaded'
    assert 'conversão' in db.tasks()[0]['error']
    monkeypatch.setattr(downloads, 'ensure_pdf', real)
    class Offline(Client):
        async def text(self, url):
            raise AssertionError('Não deve consultar a rede na recuperação do PDF')
    from app.services.download_manager import DownloadManager
    DownloadManager(db, settings).command(db.tasks()[0]['id'], 'retry')
    await perform(settings, db, Offline(image_bytes))
    assert db.tasks()[0]['status'] == 'complete'
    assert not db.tasks()[0]['error']
    chapter = db.chapters(mid)[0]
    with pikepdf.open(pdf_target(chapter)) as pdf:
        assert len(pdf.pages) == 2
    before = pdf_target(chapter).stat().st_mtime_ns
    ensure_pdf(chapter)
    assert pdf_target(chapter).stat().st_mtime_ns == before


async def test_recovery_relinks_moved_folder_without_changing_images(setup_library, image_bytes, tmp_path):
    settings, db, library, mid, ids = setup_library
    await perform(settings, db, Client(image_bytes))
    chapter = db.chapters(mid)[0]
    pdf_target(chapter).unlink()
    old = Path(chapter['folder']).parent
    new = old.with_name('pasta renomeada')
    old.rename(new)
    report = recover_downloads(library, Path(settings.library))
    assert report == dict(queued=1, relocated=1)
    relocated = db.chapters(mid)[0]
    assert Path(relocated['folder']).parent == new
    assert db.tasks()[0]['status'] == 'queued'
    await perform(settings, db, Client(image_bytes))
    assert pdf_target(relocated).exists()
    assert recover_downloads(library, Path(settings.library))['queued'] == 0


@pytest.mark.parametrize('fmt,mode', [('WEBP', 'RGBA'), ('GIF', 'P'), ('PNG', 'P')])
def test_pdf_handles_real_formats_and_transparency(tmp_path, fmt, mode):
    folder = tmp_path / 'images'
    folder.mkdir()
    image = Image.new(mode, (40, 80))
    if mode == 'P':
        image.info['transparency'] = 0
    image.save(folder / ('page.' + fmt.lower()), fmt)
    export_chapter(folder, tmp_path / 'chapter.pdf', 'pdf')
    with pikepdf.open(tmp_path / 'chapter.pdf') as pdf:
        assert len(pdf.pages) == 1
        assert float(pdf.pages[0].MediaBox[2]) / float(pdf.pages[0].MediaBox[3]) == pytest.approx(.5)


def test_long_page_invalid_dpi_fits_pdf_limits(tmp_path):
    folder = tmp_path / 'images'
    folder.mkdir()
    Image.new('RGB', (20, 20000)).save(folder / 'page.png', dpi=(1, 1))
    export_chapter(folder, tmp_path / 'long.pdf', 'pdf')
    with pikepdf.open(tmp_path / 'long.pdf') as pdf:
        assert len(pdf.pages) == 1
        assert max(map(float, pdf.pages[0].MediaBox)) <= 14000
        assert float(pdf.pages[0].MediaBox[2]) / float(pdf.pages[0].MediaBox[3]) == pytest.approx(.001)


async def test_mangalivre_names_and_no_ui_author_as_title():
    from tests.test_extractors import FakeClient
    url = 'https://mangalivre.blog/manga/vagabond/'
    html = '<a href="/capitulo/vagabond-capitulo-1/">Iniciar Leitura</a><h1 class="site-title">Manga Livre</h1><span itemprop="name">Autor errado</span><h1 class="manga-title">Vagabond</h1><div class="chapter-list"><a href="/capitulo/vagabond-capitulo-1/">Capítulo 1: Capítulo 1</a></div>'
    source = FakeClient({url: html})
    extractor = Registry(source).select(url)
    assert isinstance(extractor, MangaLivreExtractor)
    manga = await extractor.get_manga_info(url)
    assert manga.title == 'Vagabond'
    assert len(manga.chapters) == 1 and manga.chapters[0].title == 'Capítulo 1'


async def test_mangalivre_direct_chapter_uses_parent_work():
    from tests.test_extractors import FakeClient
    work = 'https://mangalivre.blog/manga/vagabond/'
    url = 'https://mangalivre.blog/capitulo/vagabond-capitulo-1/'
    source = FakeClient({url: '<nav class="breadcrumb"><a href="/manga/vagabond/">Vagabond</a></nav><h1 class="chapter-title">Vagabond / Capítulo 1 - Capítulo 1</h1><div id="reader"><img src="/1.webp"></div>', work: '<h1 class="manga-title">Vagabond</h1>'})
    manga = await Registry(source).select(url).get_manga_info(url)
    assert manga.url == work and manga.title == 'Vagabond'
    assert len(manga.chapters) == 1 and manga.chapters[0].title == 'Capítulo 1'


def test_mangalivre_decimal_label_uses_real_chapter_title():
    from app.extractors.titles import clean_chapter_title
    assert clean_chapter_title('Capítulo 327: Capítulo 327.5') == 'Capítulo 327.5'
    assert clean_chapter_title('Capítulo 5: Uma nova história') == 'Capítulo 5: Uma nova história'


async def test_pause_during_pdf_waits_for_atomic_conversion(setup_library, image_bytes, monkeypatch):
    import asyncio
    import threading
    import app.services.download_manager as downloads
    from app.services.download_manager import DownloadManager
    settings, db, library, mid, ids = setup_library
    entered, release = threading.Event(), threading.Event()
    real = downloads.ensure_pdf
    def slow(chapter):
        entered.set()
        assert release.wait(5)
        return real(chapter)
    monkeypatch.setattr(downloads, 'ensure_pdf', slow)
    manager = DownloadManager(db, settings)
    manager.running = True
    record = db.tasks()[0]
    db.execute("UPDATE tasks SET status='running' WHERE id=?", (record['id'],))
    source = Client(image_bytes)
    task = asyncio.create_task(manager.download(record, source, Registry(source)))
    for _ in range(200):
        if entered.is_set():
            break
        await asyncio.sleep(.01)
    assert entered.is_set()
    db.execute("UPDATE tasks SET status='paused' WHERE id=?", (record['id'],))
    task.cancel()
    await asyncio.sleep(.02)
    assert not task.done()
    release.set()
    await task
    assert db.tasks()[0]['status'] == 'paused'
    assert pdf_target(db.chapters(mid)[0]).exists()
    manager.command(record['id'], 'resume')
    await perform(settings, db, source)
    assert db.tasks()[0]['status'] == 'complete'
