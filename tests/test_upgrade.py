import hashlib
from pathlib import Path
import pytest
import pikepdf
from PIL import Image, ImageChops, ImageOps
from app.services.export import export_chapter, file_hash
from app.services.batch import add_links
from app.models import Manga, Chapter
from tests.test_downloads import Client, perform


def test_streamed_pdf_preserves_pixels_order_and_embedded_jpeg(tmp_path):
    folder = tmp_path / 'pages'
    folder.mkdir()
    Image.new('RGB', (80, 120), '#b03b59').save(folder / '1.png')
    Image.new('RGB', (60, 90), '#0d9488').save(folder / '2.jpg')
    export_chapter(folder, tmp_path / 'book.pdf', 'pdf')
    with pikepdf.open(tmp_path / 'book.pdf') as pdf:
        assert len(pdf.pages) == 2
        first = pikepdf.PdfImage(pdf.pages[0].get_images()['/Im0']).as_pil_image()
        with Image.open(folder / '1.png') as original:
            assert ImageChops.difference(first, original).getbbox() is None
        assert pdf.pages[1].get_images()['/Im0'].read_raw_bytes() == (folder / '2.jpg').read_bytes()
        assert pdf.check_pdf_syntax() == []


def test_streamed_pdf_applies_exif_rotation(tmp_path):
    folder = tmp_path / 'pages'
    folder.mkdir()
    exif = Image.Exif()
    exif[274] = 6
    Image.new('RGB', (40, 80), 'navy').save(folder / '1.jpg', exif=exif)
    export_chapter(folder, tmp_path / 'rotated.pdf', 'pdf')
    with pikepdf.open(tmp_path / 'rotated.pdf') as pdf:
        image = pikepdf.PdfImage(pdf.pages[0].get_images()['/Im0']).as_pil_image()
        assert image.size == (80, 40)
        assert float(pdf.pages[0].MediaBox[2]) > float(pdf.pages[0].MediaBox[3])


def test_pdf_hash_never_reads_entire_file(tmp_path, monkeypatch):
    target = tmp_path / 'large.pdf'
    target.write_bytes(b'PDF bytes' * 1000)
    expected = hashlib.sha256(target.read_bytes()).hexdigest()
    def forbidden(*args):
        raise AssertionError('Arquivo inteiro carregado em RAM')
    monkeypatch.setattr(Path, 'read_bytes', forbidden)
    assert file_hash(target) == expected


async def test_skip_completed_pdf_and_requeue_modified_file(setup_library, image_bytes):
    settings, db, library, mid, ids = setup_library
    await perform(settings, db, Client(image_bytes))
    assert library.enqueue(ids, skip_complete=True) == dict(added=0, skipped=1)
    from app.services.export import pdf_target
    pdf_target(db.chapters(mid)[0]).write_bytes(b'corrupted')
    assert library.enqueue(ids, skip_complete=True) == dict(added=1, skipped=0)


async def test_batch_deduplicates_links_prioritizes_ptbr_and_continues_after_failure(setup_library):
    _, db, library, _, _ = setup_library
    seen = []
    async def fetch(url):
        seen.append(url)
        if url.endswith('/bad'):
            raise ValueError('Fonte indisponível')
        return Manga('Lote', url, chapters=[
            Chapter('Capítulo 1 PT', url + '/pt', 'pt-br'),
            Chapter('Capítulo 1 EN', url + '/en', 'en')]), None, 'fixture'
    result = await add_links('https://example.org/bad\nhttps://example.org/good\nhttps://example.org/good', library, fetch)
    assert len(seen) == 2 and 'error' in result[0]
    assert result[1]['added'] == 1
    tasks = [t for t in db.tasks() if t['manga'] == 'Lote']
    assert len(tasks) == 1 and tasks[0]['chapter'].endswith('PT')


async def test_batch_can_cancel_current_network_request(setup_library):
    import asyncio
    import threading
    _, db, library, _, _ = setup_library
    cancel = threading.Event()
    closed = []
    async def fetch(url):
        cancel.set()
        try:
            await asyncio.sleep(10)
        finally:
            closed.append(url)
    result = await asyncio.wait_for(add_links('https://example.org/a https://example.org/b', library, fetch, cancel), 1)
    assert len(result) == 1 and 'interrompida' in result[0]['error']
    assert closed == ['https://example.org/a']
    assert len(db.tasks()) == 1


def test_streamed_pdf_keeps_embedded_color_profile(tmp_path):
    from PIL import ImageCms
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    folder = tmp_path / 'pages'
    folder.mkdir()
    Image.new('RGB', (40, 80), 'navy').save(folder / 'page.png', icc_profile=profile)
    export_chapter(folder, tmp_path / 'color.pdf', 'pdf')
    with pikepdf.open(tmp_path / 'color.pdf') as pdf:
        color_space = pdf.pages[0].get_images()['/Im0'].ColorSpace
        assert str(color_space[0]) == '/ICCBased'
        assert color_space[1].read_bytes() == profile
        assert not pdf.check_pdf_syntax()
