from pathlib import Path
import threading
import time
import pytest
from PIL import Image
from PySide6.QtCore import QTimer
from tests.test_ui import window, qt_app, spin
from tests.test_drive_api import MemoryVault
from tests.test_drive_sync import FakeDrive
from app.services.export import export_chapter, pdf_target
from app.infrastructure.drive_auth import DriveCancelled, DriveError


@pytest.fixture
def configured(window):
    chapter = window.db.query('SELECT * FROM chapters')[0]
    folder = Path(chapter['folder'])
    folder.mkdir(parents=True)
    Image.new('RGB', (40, 80), 'teal').save(folder / 'page.png')
    export_chapter(folder, pdf_target(chapter), 'pdf')
    window.drive.vault = MemoryVault()
    client = FakeDrive(window.drive.cancel)
    window.drive.client_factory = lambda: client
    window.drive.reload_account()
    window.drive.panel.folder.setText('https://drive.google.com/drive/folders/rootfolder')
    window.show_page(6)
    return window, client


def test_drive_preview_and_send_buttons_copy_only_once(configured, qt_app):
    window, client = configured
    panel = window.drive.panel
    panel.check.click()
    spin(qt_app, lambda: not window.jobs)
    assert panel.table.rowCount() == 1
    assert panel.plan['missing'] == 1 and not client.uploaded
    panel.send.click()
    spin(qt_app, lambda: not window.jobs)
    assert len(client.uploaded) == 1 and panel.plan['missing'] == 0
    assert not panel.send.isEnabled()
    assert (window.data_root / 'logs/drive/last_sync.json').is_file()
    assert not window.error_messages


def test_automatic_sync_respects_configured_folder_and_new_folder_edit(configured, qt_app):
    window, client = configured
    panel = window.drive.panel
    panel.use_folder.click()
    spin(qt_app, lambda: not window.jobs)
    panel.automatic.setChecked(True)
    assert window.settings.drive_auto
    panel.folder.setText('https://drive.google.com/drive/folders/otherfolder')
    panel.folder.textEdited.emit(panel.folder.text())
    window.drive.auto_sync()
    assert not window.drive.busy and not client.uploaded
    panel.folder.setText('https://drive.google.com/drive/folders/rootfolder')
    window.drive.auto_sync()
    spin(qt_app, lambda: not window.jobs)
    assert len(client.uploaded) == 1
    text = (window.data_root / 'settings.json').read_text(encoding='utf-8')
    assert 'test-refresh' not in text and 'test-secret' not in text


def test_cancel_interrupts_cloud_worker_without_freezing_ui(configured, qt_app):
    window, client = configured
    panel = window.drive.panel
    panel.check.click()
    spin(qt_app, lambda: not window.jobs)
    entered = threading.Event()
    def upload(*args):
        entered.set()
        while not client.cancel.wait(.01):
            pass
        raise DriveCancelled('Cancelado')
    client.upload = upload
    panel.send.click()
    spin(qt_app, entered.is_set)
    assert panel.cancel.isEnabled()
    panel.cancel.click()
    spin(qt_app, lambda: not window.jobs)
    assert 'cancelada' in panel.summary.text().lower()
    assert not window.error_messages


def test_remote_error_is_inline_and_background_check_keeps_ticking(configured, qt_app):
    window, client = configured
    def listing(parent):
        time.sleep(.25)
        raise DriveError('Drive indisponível')
    client.list_children = listing
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(10)
    window.drive.panel.check.click()
    spin(qt_app, lambda: not window.jobs)
    timer.stop()
    assert len(ticks) > 5
    assert 'Drive indisponível' in window.drive.panel.summary.text()
    assert not window.error_messages
