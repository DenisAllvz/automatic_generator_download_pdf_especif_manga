import json
from pathlib import Path
import pytest
from app.infrastructure.catalog import Catalog, CATALOG_NAME, read_manifest
from tests.test_downloads import Client, perform


async def test_download_has_one_catalog_and_no_json(setup_library, image_bytes):
    settings, db, library, mid, ids = setup_library
    await perform(settings, db, Client(image_bytes))
    work = Path(db.mangas()[0]['folder'])
    assert not list(work.rglob('*.json'))
    assert len(list(work.rglob(CATALOG_NAME))) == 1
    chapter = db.chapters(mid)[0]
    assert read_manifest(chapter['folder'])['expected'] == 2
    assert list((work / 'PDF').glob('*.pdf'))


def test_500_legacy_records_consolidated_and_unrelated_json_preserved(tmp_path):
    catalog = Catalog(tmp_path)
    for i in range(500):
        folder = tmp_path / f'Chapter {i}'
        folder.mkdir()
        (folder / 'manifest.json').write_text(json.dumps({'expected': 1, 'pages': [], 'chapter_url': f'https://example.org/{i}'}))
    unrelated = tmp_path / 'personal.json'
    unrelated.write_text('{"mine": true}')
    broken = tmp_path / 'Chapter 500'
    broken.mkdir()
    (broken / 'manifest.json').write_text('incomplete file')
    assert catalog.migrate() == 500
    assert len(catalog.manifests()) == 500
    assert catalog.migrate() == 0
    assert unrelated.exists() and (broken / 'manifest.json').exists()
    assert read_manifest(tmp_path / 'Chapter 499')['expected'] == 1


def test_failed_catalog_commit_keeps_original(tmp_path, monkeypatch):
    folder = tmp_path / 'Chapter 1'
    folder.mkdir()
    original = folder / 'manifest.json'
    original.write_text('{"expected": 1, "pages": []}')
    from contextlib import contextmanager
    @contextmanager
    def fail(self):
        raise OSError('Disco cheio')
        yield
    monkeypatch.setattr(Catalog, 'connection', fail)
    with pytest.raises(OSError, match='Disco cheio'):
        Catalog(tmp_path).migrate()
    assert original.exists()
