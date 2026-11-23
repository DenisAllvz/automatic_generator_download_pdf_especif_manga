import asyncio
import time
from pathlib import Path
import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication
from app.ui.main_window import MainWindow
from app.models import Manga, Chapter


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture
def window(qt_app, setup_library, tmp_path):
    settings, db, library, mid, ids = setup_library
    window = MainWindow(db, settings, tmp_path, start_queue=False)
    window.error_messages = []
    window.error = window.error_messages.append
    window.show()
    qt_app.processEvents()
    yield window
    spin(qt_app, lambda: not window.jobs)
    window.close()
    qt_app.processEvents()


def spin(app, condition, limit=3):
    start = time.monotonic()
    while not condition() and time.monotonic() - start < limit:
        app.processEvents()
        time.sleep(.01)
    assert condition()


def test_screens_selection_and_queue_commands(window, qt_app):
    assert window.stack.count() == 7
    assert window.reader is None
    window.show_preview((Manga("Teste", "https://example.org/manga", chapters=[Chapter(f"Chapter {i}", f"https://example.org/chapter-{i}") for i in range(1, 4)]), None, "fixture"))
    window.range.setText("1-2")
    window.select_range()
    assert window.chapter_selection.item(0).checkState() == Qt.CheckState.Checked
    assert window.chapter_selection.item(2).checkState() == Qt.CheckState.Unchecked
    task = window.db.tasks()[0]
    window.manager.command(task["id"], "pause")
    window.refresh_queue()
    assert window.queue_table.item(0, 1).text() == "Pausado"
    assert window.general_progress.value() == 0


def test_analysis_worker_does_not_block_gui(window, qt_app):
    async def fetch(url):
        await asyncio.sleep(.15)
        return Manga("Async", url, chapters=[Chapter("Chapter 1", url+"/chapter-1")]), None, "fixture"
    window.fetch = fetch
    window.url.setText("https://example.org/manga")
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(10)
    window.analyze()
    assert not window.analyze_button.isEnabled()
    spin(qt_app, lambda: window.analyze_button.isEnabled())
    timer.stop()
    assert len(ticks) >= 3
    assert window.preview[0].title == "Async"


def test_worker_error_visible(window, qt_app):
    def fail():
        raise ValueError("layout incompatible")
    window.job(fail, lambda _: None)
    spin(qt_app, lambda: bool(window.error_messages))
    spin(qt_app, lambda: not window.jobs)
    assert "layout incompatible" in window.error_messages[0]


def test_resizing_and_light_theme(window, qt_app):
    window.resize(960, 650)
    window.nav.setCurrentRow(4)
    qt_app.processEvents()
    assert window.width() == 960
    assert window.height() == 650
    window.settings.theme = "light"
    window.apply_theme()
    assert "#f1f4fa" in window.styleSheet()


def test_download_worker_progress_and_clean_shutdown(window, qt_app, image_bytes):
    class Source:
        def __init__(self, settings):
            self.settings = settings
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def text(self, url):
            return '<div id="reader"><img data-src="https://example.org/page.png"></div>'
        async def image(self, url, referer=""):
            await asyncio.sleep(.15)
            return image_bytes
    window.manager.client_factory = Source
    window.worker.start()
    spin(qt_app, lambda: window.db.tasks()[0]["status"] == "complete", limit=5)
    window.refresh_queue()
    assert window.queue_table.rowCount() == 0
    window.close()
    assert not window.worker.isRunning()


def test_simplified_ui_and_editable_title(window, qt_app):
    assert window.queue_table.columnCount() == 4
    assert any(window.nav.item(i).text() == "Biblioteca" for i in range(window.nav.count()))
    assert window.books is not None
    window.show_preview((Manga("Nome errado", "https://example.org/new", chapters=[Chapter("Capítulo 1", "https://example.org/new/chapter-1")]), None, "fixture"))
    window.work_name.setText("Nome corrigido")
    window.confirm_preview(True)
    spin(qt_app, lambda: not window.jobs)
    manga = next(m for m in window.db.mangas() if m['url'] == "https://example.org/new")
    assert manga['title'] == "Nome corrigido"
    assert Path(manga['folder']).name == "Nome corrigido"


def test_language_filter_queues_only_visible_selected_chapters(window, qt_app):
    manga = Manga("Nome da obra", "https://example.org/new", chapters=[
        Chapter("Capítulo 1 [EN]", "https://example.org/en", "en"),
        Chapter("Capítulo 1 [PT-BR]", "https://example.org/pt", "pt-br")])
    window.show_preview((manga, None, "MangaDex — API oficial"))
    assert window.chapter_language.currentData() == "pt-br"
    assert window.chapter_selection.count() == 1
    assert window.preview_chapters[0].url.endswith("/pt")
    window.confirm_preview(True)
    spin(qt_app, lambda: not window.jobs)
    tasks = window.db.tasks()
    assert len(tasks) == 2
    new = next(t for t in tasks if t["manga"] == "Nome da obra")
    assert "PT-BR" in new["chapter"]


def test_completed_queue_is_logged_notified_and_cleared(window, qt_app):
    window.db.execute("UPDATE tasks SET status='complete'")
    window.enable_completion()
    spin(qt_app, lambda: not window.jobs)
    assert window.queue_table.rowCount() == 0
    assert window.db.tasks() == []
    assert len(list(window.reports.destination.glob('*.txt'))) == 1
    assert len(window.completion_notices) == 1
    for box in list(window.completion_notices):
        box.accept()
    window.refresh_queue()
    qt_app.processEvents()
    assert not window.completion_notices
    assert not window.jobs


def test_actual_queue_buttons_apply_without_selection_and_respect_selection(window, qt_app):
    from PySide6.QtWidgets import QPushButton
    buttons = {b.text(): b for b in window.findChildren(QPushButton)}
    buttons['Pausar'].click()
    spin(qt_app, lambda: not window.jobs)
    assert window.db.tasks()[0]['status'] == 'paused'
    buttons['Retomar'].click()
    spin(qt_app, lambda: not window.jobs)
    assert window.db.tasks()[0]['status'] == 'queued'
    window.db.execute("UPDATE tasks SET status='failed',error='Falha simulada'")
    window.refresh_queue()
    buttons['Tentar novamente'].click()
    spin(qt_app, lambda: not window.jobs)
    assert window.db.tasks()[0]['status'] == 'queued'
    mid, ids = window.library.add(Manga('Outra', 'https://example.org/other', chapters=[Chapter('Capítulo 2', 'https://example.org/other/2')]))
    window.library.enqueue(ids)
    window.refresh_queue()
    window.queue_table.selectRow(0)
    buttons['Pausar'].click()
    spin(qt_app, lambda: not window.jobs)
    assert [t['status'] for t in window.db.tasks()] == ['paused', 'queued']
    point = window.queue_table.visualItemRect(window.queue_table.item(0, 0)).center()
    window.queue_menu(point)
    window.queue_contextmenu.actions()[0].trigger()
    spin(qt_app, lambda: not window.jobs)
    assert window.db.tasks()[0]['status'] == 'cancelled'
    window.queue_menu(point)
    window.queue_contextmenu.actions()[1].trigger()
    spin(qt_app, lambda: not window.jobs)
    assert len(window.db.tasks()) == 1
    assert len(window.db.chapters(mid)) == 1
    assert not any('prioridade' in b.text().lower() for b in buttons.values())


def test_dashboard_utility_buttons_present_and_open_folders(window, monkeypatch):
    from PySide6.QtWidgets import QPushButton
    from PySide6.QtGui import QDesktopServices
    urls = []
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: urls.append(url.toLocalFile()) or True)
    buttons = {b.text(): b for b in window.findChildren(QPushButton)}
    buttons['Novo download'].click()
    assert window.nav.currentRow() == 2
    buttons['Abrir PDFs'].click()
    buttons['Relatórios'].click()
    assert len(urls) == 2
    assert all(Path(url).is_dir() for url in urls)


def test_large_queue_reuses_items_without_per_chapter_widgets(window, qt_app):
    from PySide6.QtWidgets import QProgressBar
    _, ids = window.library.add(Manga('Grande', 'https://example.org/large', chapters=[
        Chapter(f'Capítulo {i}', f'https://example.org/large/{i}') for i in range(1000)]))
    window.library.enqueue(ids)
    window.refresh_queue()
    item = window.queue_table.item(500, 0)
    window.queue_table.selectRow(500)
    window.queue_table.verticalScrollBar().setValue(400)
    for _ in range(3):
        window.refresh_queue()
    assert window.queue_table.item(500, 0) is item
    assert window.queue_table.selectionModel().selectedRows()[0].row() == 500
    assert len(window.findChildren(QProgressBar)) == 3
    assert window.queue_table.cellWidget(500, 2) is None


def test_refresh_coalesces_and_gui_keeps_ticking_while_database_is_busy(window, qt_app):
    import threading
    locked, release = threading.Event(), threading.Event()
    def hold_database():
        with window.db.connection():
            locked.set()
            release.wait(3)
    thread = threading.Thread(target=hold_database)
    thread.start()
    assert locked.wait(1)
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(10)
    try:
        before = time.monotonic()
        for _ in range(100):
            window.request_refresh()
        assert time.monotonic() - before < .2
        assert len(window.jobs) == 1
        spin(qt_app, lambda: len(ticks) >= 8)
        assert window.refresh_busy
    finally:
        release.set()
        thread.join(2)
        timer.stop()
    spin(qt_app, lambda: not window.jobs)


def test_download_link_persistence_keeps_gui_responsive_and_ignores_double_click(window, qt_app, monkeypatch):
    import threading
    from app.services.library import Library
    calls = []
    original = Library.add
    def slow_add(service, manga):
        calls.append(manga.url)
        with service.db.connection():
            time.sleep(.3)
        return original(service, manga)
    window.show_preview((Manga('Link grande', 'https://example.org/link', chapters=[
        Chapter(f'Capítulo {i}', f'https://example.org/link/{i}') for i in range(500)]), None, 'fixture'))
    monkeypatch.setattr(Library, 'add', slow_add)
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(10)
    window.confirm_preview(True)
    window.confirm_preview(True)
    window.request_refresh()
    spin(qt_app, lambda: not window.jobs, limit=8)
    timer.stop()
    assert len(ticks) >= 10
    assert calls == ['https://example.org/link']
    assert len(window.db.tasks()) == 501
    assert not window.error_messages


def test_queue_search_limits_bulk_actions_to_visible_rows(window, qt_app):
    _, ids = window.library.add(Manga('Outra', 'https://example.org/other', chapters=[
        Chapter('Capítulo 5', 'https://example.org/other/5')]))
    window.library.enqueue(ids)
    window.refresh_queue()
    window.queue_search.setText('Outra')
    assert window.queue_table.isRowHidden(0)
    assert not window.queue_table.isRowHidden(1)
    window.queue_buttons['pause'].click()
    spin(qt_app, lambda: not window.jobs)
    assert [t['status'] for t in window.db.tasks()] == ['queued', 'paused']


def test_multiple_links_button_runs_batch_and_writes_report(window, qt_app):
    async def fetch(url):
        await asyncio.sleep(.02)
        return Manga('Lote', url, chapters=[Chapter('Capítulo 1', url + '/1')]), None, 'fixture'
    window.fetch = fetch
    window.batch_urls.setPlainText('https://example.org/a\nhttps://example.org/b')
    window.batch_button.click()
    window.download_links()
    assert not window.batch_button.isEnabled()
    spin(qt_app, lambda: not window.jobs)
    assert len(window.db.tasks()) == 3
    assert (window.data_root / 'logs' / 'ultimo-lote-de-links.json').is_file()


def test_stop_batch_button_cancels_current_analysis(window, qt_app):
    import threading
    entered = threading.Event()
    async def fetch(url):
        entered.set()
        await asyncio.sleep(10)
    window.fetch = fetch
    window.batch_urls.setPlainText('https://example.org/slow')
    window.batch_button.click()
    spin(qt_app, entered.is_set)
    window.batch_cancel.click()
    spin(qt_app, lambda: not window.jobs)
    assert window.batch_button.isEnabled() and not window.batch_cancel.isEnabled()
    assert len(window.db.tasks()) == 1


def test_queue_hides_completed_and_old_attempts(window):
    chapter_id = window.db.tasks()[0]['chapter_id']
    window.db.execute("UPDATE tasks SET status='complete'")
    window.db.execute("INSERT INTO tasks(chapter_id,status,error) VALUES(?,'failed','Falha antiga')", (chapter_id,))
    window.db.execute("INSERT INTO tasks(chapter_id,status) VALUES(?,'queued')", (chapter_id,))
    window.refresh_queue()
    assert window.queue_table.rowCount() == 1
    assert window.task_rows[0]['status'] == 'queued'
    assert window.queue_table.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOn


def test_old_failures_are_summarized_but_can_be_retried(window, qt_app):
    window.db.execute("UPDATE tasks SET status='failed',error='Erro anterior',updated='2020-01-01T00:00:00+00:00'")
    window.refresh_queue()
    assert window.queue_table.rowCount() == 0
    assert window.queue_buttons['retry'].isEnabled()
    window.queue_buttons['retry'].click()
    spin(qt_app, lambda: not window.jobs)
    assert window.queue_table.rowCount() == 1
    assert window.db.tasks()[0]['status'] == 'queued'


def test_library_lists_all_chapters_and_bulk_marks_read(window, qt_app):
    manga = window.db.mangas()[0]
    window.open_work(manga['id'])
    spin(qt_app, lambda: not window.jobs)
    assert window.books.chapters.rowCount() == 1
    window.books.chapters.selectAll()
    window.mark_read(window.books.selected(), True)
    spin(qt_app, lambda: not window.jobs)
    assert window.books.chapters.item(0, 1).text() == 'Lido'
    assert window.db.mangas()[0]['read_count'] == 1


def test_native_reader_saves_page_and_restores_progress(window, qt_app, tmp_path):
    from app.services.export import export_chapter, pdf_target
    from PIL import Image
    chapter = window.db.chapters(window.db.mangas()[0]['id'])[0]
    folder = Path(chapter['folder'])
    folder.mkdir(parents=True)
    for i in range(3):
        Image.new('RGB', (500, 1400), ('navy','teal','purple')[i]).save(folder / f'{i}.png')
    export_chapter(folder, pdf_target(chapter), 'pdf')
    window.open_reader(chapter['id'])
    spin(qt_app, lambda: window.reader is not None and not window.reader.restoring)
    window.reader.jump(1)
    qt_app.processEvents()
    window.reader.view.verticalScrollBar().setValue(window.reader.view.verticalScrollBar().value() + 77)
    qt_app.processEvents()
    expected_scroll = window.reader.view.verticalScrollBar().value()
    window.reader.flush()
    window.persist_reading()
    spin(qt_app, lambda: not window.jobs)
    assert window.db.chapters(chapter['manga_id'])[0]['read_page'] == 1
    assert not window.db.chapters(chapter['manga_id'])[0]['is_read']
    window.reader.close()
    spin(qt_app, lambda: not window.jobs)
    window.open_reader(chapter['id'])
    spin(qt_app, lambda: not window.jobs and not window.reader.restoring)
    assert window.reader.page_number.value() == 2
    assert abs(window.reader.view.verticalScrollBar().value() - expected_scroll) <= 5
    window.reader.close()
    window.persist_reading()
    spin(qt_app, lambda: not window.jobs)


def test_reaching_pdf_end_marks_read_and_badges_cover(window, qt_app):
    from app.services.export import export_chapter, pdf_target
    from PIL import Image
    chapter = window.db.chapters(window.db.mangas()[0]['id'])[0]
    folder = Path(chapter['folder'])
    folder.mkdir(parents=True)
    for i in range(2):
        Image.new('RGB', (500, 1400), 'teal').save(folder / f'{i}.png')
    export_chapter(folder, pdf_target(chapter), 'pdf')
    from app.services.covers import cover_from_pdf
    assert cover_from_pdf(window.db, window.db.mangas()[0], window.data_root)
    window.open_reader(chapter['id'])
    spin(qt_app, lambda: window.reader is not None and not window.reader.restoring)
    bar = window.reader.view.verticalScrollBar()
    bar.setValue(bar.maximum())
    spin(qt_app, lambda: bool(window.db.chapters(chapter['manga_id'])[0]['is_read']), limit=5)
    spin(qt_app, lambda: not window.jobs)
    badge = window.books.grid.item(0).icon().pixmap(150, 214).toImage().pixelColor(140, 200)
    assert badge.green() > badge.red() * 2
    window.reader.close()
    window.persist_reading()
    spin(qt_app, lambda: not window.jobs)
