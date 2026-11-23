import json
from pathlib import Path
import pytest
from app.models import Manga, Chapter
from app.services.download_reports import DownloadReports
from tests.test_downloads import Client, perform


async def test_log_precedes_cleanup_and_preserves_pdfs(setup_library, image_bytes, tmp_path):
    settings, db, library, mid, ids = setup_library
    await perform(settings, db, Client(image_bytes))
    reports = DownloadReports(db, tmp_path / 'reports')
    result = reports.finish_ready()
    assert len(result) == 1 and result[0]['completed'] == 1
    assert result[0]['missing_pdf'] == 0
    text = Path(result[0]['file']).read_text(encoding='utf-8-sig')
    assert 'Capítulo 1' in text and 'CONCLUÍDO' in text
    saved = json.loads(Path(result[0]['file']).with_suffix('.json').read_text(encoding='utf-8'))
    assert saved['tasks'][0]['pdf_exists']
    assert Path(saved['tasks'][0]['pdf']).exists()
    assert db.tasks() == []
    assert db.chapters(mid)[0]['status'] == 'downloaded'
    assert len(db.query('SELECT * FROM download_history')) == 1
    assert reports.finish_ready() == []


def test_write_failure_keeps_queue(setup_library, tmp_path, monkeypatch):
    _, db, _, _, _ = setup_library
    db.execute("UPDATE tasks SET status='complete'")
    service = DownloadReports(db, tmp_path / 'reports')
    import app.services.download_reports as module
    def fail(*args):
        raise OSError('Disco cheio')
    monkeypatch.setattr(module, 'atomic_bytes', fail)
    with pytest.raises(OSError, match='Disco cheio'):
        service.finish_ready()
    assert db.tasks()[0]['status'] == 'complete'
    assert not db.query('SELECT * FROM download_history')


def test_500_chapters_wait_until_last_task_and_keep_failures(setup_library, tmp_path):
    _, db, library, _, _ = setup_library
    manga = Manga('Obra 1.5', 'https://example.org/large', chapters=[Chapter(f'Capítulo {i}', f'https://example.org/large/{i}') for i in range(500)])
    mid, ids = library.add(manga)
    library.enqueue(ids)
    db.execute("UPDATE tasks SET status='complete' WHERE chapter_id IN (SELECT id FROM chapters WHERE manga_id=?)", (mid,))
    db.execute("UPDATE tasks SET status='paused' WHERE chapter_id=?", (ids[-1],))
    reports = DownloadReports(db, tmp_path / 'reports')
    assert reports.finish_ready() == []
    db.execute("UPDATE tasks SET status='failed',error='Falha PDF' WHERE chapter_id=?", (ids[-1],))
    result = reports.finish_ready()
    assert result[0]['completed'] == 499 and result[0]['failed'] == 1
    assert len(result[0]['tasks']) == 499
    assert len(db.tasks()) == 2
    assert db.query("SELECT error FROM tasks WHERE status='failed'")[0]['error'] == 'Falha PDF'
    assert 'Obra 1.5-' in Path(result[0]['file']).name
