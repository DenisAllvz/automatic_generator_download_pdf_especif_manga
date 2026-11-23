import copy
import hashlib
import threading
from pathlib import Path
import pytest
from PIL import Image
from app.models import Manga, Chapter
from app.services.export import export_chapter, pdf_target
from app.infrastructure.drive_auth import DriveError, DriveCancelled
from app.infrastructure.google_drive import FOLDER
from app.services.drive_sync import DriveSync


class FakeDrive:
    def __init__(self, cancel=None):
        self.cancel = cancel or threading.Event()
        self.items = {'rootfolder': dict(id='rootfolder', name='Leituras', mimeType=FOLDER,
                                        capabilities={'canAddChildren': True})}
        self.created, self.uploaded = [], []
        self.fail = set()
        self.cancel_after = False

    def check_cancel(self):
        if self.cancel.is_set():
            raise DriveCancelled('Cancelado')

    def get_folder(self, ident):
        self.check_cancel()
        return copy.deepcopy(self.items['rootfolder' if ident == 'root' else ident])

    def list_children(self, parent):
        self.check_cancel()
        return [copy.deepcopy(v) for v in self.items.values() if parent in v.get('parents', [])]

    def create_folder(self, parent, name, mid):
        ident = f'folder{len(self.items):04}'
        row = dict(id=ident, name=name, mimeType=FOLDER, parents=[parent], appProperties={'mmWork': mid})
        self.items[ident] = row
        self.created.append(ident)
        return copy.deepcopy(row)

    def seed(self, parent, source, name=None, content=None, tagged=True):
        content = Path(source['path']).read_bytes() if content is None else content
        ident = f'file{len(self.items):04}'
        row = dict(id=ident, name=name or Path(source['path']).name, parents=[parent], mimeType='application/pdf',
                   size=str(len(content)), md5Checksum=hashlib.md5(content).hexdigest(),
                   appProperties={'mmChapter': source['cid'], 'mmWork': source['mid']} if tagged else {})
        self.items[ident] = row
        return copy.deepcopy(row)

    def upload(self, parent, source, progress):
        self.check_cancel()
        if source['cid'] in self.fail:
            raise DriveError('Falha simulada')
        result = self.seed(parent, source)
        self.uploaded.append(source['cid'])
        progress(source['size'], source['size'])
        if self.cancel_after:
            self.cancel.set()
        return result


@pytest.fixture
def drive_fixture(setup_library):
    settings, db, library, mid, _ = setup_library
    library.add(Manga('Obra Á', 'https://example.org/manga/a', chapters=[
        Chapter('Capítulo 1', 'https://example.org/chapter-1'), Chapter('Capítulo 2', 'https://example.org/chapter-2')]))
    for index, chapter in enumerate(db.chapters(mid)):
        folder = Path(chapter['folder'])
        folder.mkdir(parents=True)
        with Image.new('RGB', (40, 80), ('navy','teal')[index]) as image:
            image.save(folder / '1.png')
        export_chapter(folder, pdf_target(chapter), 'pdf')
    client = FakeDrive()
    service = DriveSync(db, client)
    return db, library, mid, client, service


def test_preview_is_readonly_and_send_copies_only_missing_pdfs(drive_fixture):
    db, _, mid, client, service = drive_fixture
    source = service.sources()[0]
    parent = client.create_folder('rootfolder', 'Obra Á', mid)['id']
    client.seed(parent, source)
    client.created.clear()
    plan = service.plan('rootfolder')
    assert plan['existing'] == 1 and plan['missing'] == 1
    assert not client.created and not client.uploaded
    result = service.send(plan)
    assert result['uploaded'] == 1 and result['skipped'] == 1
    assert service.plan('rootfolder')['missing'] == 0
    assert all(Path(c['folder']).is_dir() for c in db.chapters(mid))
    assert not [f for f in client.items.values() if f.get('mimeType') not in (FOLDER, 'application/pdf')]


def test_recognizes_existing_manually_renamed_pdf_by_content(drive_fixture):
    _, _, mid, client, service = drive_fixture
    parent = client.create_folder('rootfolder', 'OBRA Á', mid)['id']
    client.seed(parent, service.sources()[0], name='arquivo-que-copiei-no-tablet.pdf', tagged=False)
    assert service.plan('rootfolder')['existing'] == 1


def test_preserves_conflicting_remote_and_unrelated_files(drive_fixture):
    _, _, mid, client, service = drive_fixture
    parent = client.create_folder('rootfolder', 'Obra Á', mid)['id']
    source = service.sources()[0]
    different = client.seed(parent, source, content=b'%PDF-different')
    before = copy.deepcopy(client.items[different['id']])
    plan = service.plan('rootfolder')
    assert plan['conflicts'] == 1 and plan['missing'] == 1
    assert service.send(plan)['uploaded'] == 1
    assert client.items[different['id']] == before


def test_same_bytes_in_different_chapters_do_not_skip_a_chapter(drive_fixture):
    db, _, mid, client, service = drive_fixture
    chapters = db.chapters(mid)
    pdf_target(chapters[1]).write_bytes(pdf_target(chapters[0]).read_bytes())
    parent = client.create_folder('rootfolder', 'Obra Á', mid)['id']
    client.seed(parent, service.sources()[0])
    plan = service.plan('rootfolder')
    assert plan['existing'] == 1 and plan['missing'] == 1
    assert service.send(plan)['uploaded'] == 1


def test_no_duplicate_after_manual_copy_between_preview_and_upload(drive_fixture):
    _, _, mid, client, service = drive_fixture
    parent = client.create_folder('rootfolder', 'Obra Á', mid)['id']
    plan = service.plan('rootfolder')
    client.seed(parent, plan['rows'][0])
    result = service.send(plan)
    assert result['uploaded'] == 1 and result['skipped'] == 1


def test_cancel_then_resume_does_not_repeat_completed_transfers(drive_fixture):
    _, _, _, client, service = drive_fixture
    plan = service.plan('rootfolder')
    client.cancel_after = True
    result = service.send(plan)
    assert result['uploaded'] == 1 and result['cancelled']
    client.cancel.clear()
    client.cancel_after = False
    plan = service.plan('rootfolder')
    assert plan['existing'] == plan['missing'] == 1
    assert service.send(plan)['uploaded'] == 1
    assert len(set(client.uploaded)) == 2


def test_work_rename_reuses_remote_folder(drive_fixture):
    db, _, mid, client, service = drive_fixture
    service.send(service.plan('rootfolder'))
    created = list(client.created)
    from app.services.reading import Reading
    Reading(db).rename(mid, 'Nome novo')
    plan = service.plan('rootfolder')
    assert plan['existing'] == 2 and plan['missing'] == 0
    assert client.created == created


def test_upload_failure_does_not_abort_other_chapters(drive_fixture):
    _, _, _, client, service = drive_fixture
    plan = service.plan('rootfolder')
    client.fail.add(plan['rows'][0]['cid'])
    result = service.send(plan)
    assert len(result['failed']) == 1 and result['uploaded'] == 1


def test_hashes_stream_and_cache_updates_after_file_change(drive_fixture, monkeypatch):
    _, _, _, _, service = drive_fixture
    def no_read_bytes(*args):
        raise AssertionError('PDF inteiro lido na memória')
    monkeypatch.setattr(Path, 'read_bytes', no_read_bytes)
    before = service.sources()
    assert before == service.sources()
    path = Path(before[0]['path'])
    with path.open('ab') as stream:
        stream.write(b'\nmodified')
    after = service.sources()
    assert before[0]['md5'] != after[0]['md5']


def test_ambiguous_existing_folders_are_not_guessed(drive_fixture):
    _, _, _, client, service = drive_fixture
    for ident in ('firstfolder','secondfolder'):
        client.items[ident] = dict(id=ident, name='Obra Á', mimeType=FOLDER, parents=['rootfolder'])
    with pytest.raises(DriveError, match='mais de uma'):
        service.plan('rootfolder')
    assert not client.created and not client.uploaded


def test_one_work_can_sync_directly_to_its_existing_folder(drive_fixture):
    _, _, mid, client, service = drive_fixture
    client.items['rootfolder']['name'] = 'Obra Á'
    result = service.send(service.plan('rootfolder', mid=mid))
    assert result['uploaded'] == 2 and not client.created
