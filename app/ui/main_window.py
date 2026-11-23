import asyncio
import json
import platform
import sys
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSize, QUrl, Signal, QItemSelectionModel
from PySide6.QtGui import QDesktopServices, QPixmap, QIcon, QColor
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
    QListWidgetItem, QStackedWidget, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QProgressBar, QTextEdit,
    QFileDialog, QMessageBox, QComboBox, QSpinBox, QFormLayout, QCheckBox, QStyle, QScrollArea, QFrame, QMenu)

from app import __version__
from app.core.config import Settings
from app.core.exceptions import ExtractionError
from app.core.security import safe_url
from app.extractors.registry import Registry
from app.infrastructure.filesystem import atomic_json, atomic_bytes
from app.infrastructure.http_client import HttpClient
from app.infrastructure.database import timestamp
from app.services.download_manager import DownloadManager
from app.services.recovery import recover_downloads
from app.services.download_reports import DownloadReports
from app.services.integrity import inspect_image
from app.services.library import Library
from app.ui.workers import Job, QueueWorker
from app.ui.icons import icon
from app.ui.theme import stylesheet


STATUS = {"queued": "Na fila", "running": "Baixando", "paused": "Pausado", "cancelled": "Cancelado",
          "failed": "Falhou", "complete": "Concluído", "pending": "Pendente", "downloading": "Baixando",
          "downloaded": "Páginas locais íntegras", "verified": "Verificado pela fonte",
          "unverifiable": "Completude não comprovada", "incomplete": "Incompleto", "legacy": "PDF legado"}


def table(headers):
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    widget.verticalHeader().hide()
    widget.setShowGrid(False)
    widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
    widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return widget


def fill(widget, rows):
    widget.setUpdatesEnabled(False)
    try:
        widget.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                text = str(value)
                item = widget.item(r, c)
                if item is None:
                    widget.setItem(r, c, QTableWidgetItem(text))
                elif item.text() != text:
                    item.setText(text)
    finally:
        widget.setUpdatesEnabled(True)


class MainWindow(QMainWindow):

    def __init__(self, db, settings: Settings, data_root: Path, start_queue: bool = True):
        super().__init__()
        self.db, self.settings, self.data_root = db, settings, data_root
        self.library = Library(db, Path(settings.library), settings.chapter_pattern)
        self.refresh_busy = False
        self.closing = False
        self.last_queue_snapshot = None
        self.session_started = timestamp()
        self.failed_tasks = []
        self.jobs = []
        self.reports = DownloadReports(db, data_root / 'logs' / 'downloads')
        self.finish_enabled, self.completion_busy = False, False
        self.completion_notices = []
        self.preview = None
        self.selected_manga = None
        self.task_rows, self.chapter_rows, self.manga_rows, self.diagnostic_rows = [], [], [], []
        self.setWindowTitle("Manga Manager · Baixe e receba seus PDFs")
        self.resize(1240, 810)
        self.setMinimumSize(960, 650)
        asset_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
        self.setWindowIcon(QIcon(str(asset_root / "assets" / "app.ico")))
        shell = QWidget()
        shell.setObjectName("main")
        self.setCentralWidget(shell)
        root = QHBoxLayout(shell)
        root.setContentsMargins(0, 0, 0, 0)
        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(208)
        sidebar = QVBoxLayout(side)
        brand = QLabel("Manga Manager")
        brand.setObjectName("brand")
        sidebar.addWidget(brand)
        subtitle = QLabel("   Seu espaço de leitura")
        subtitle.setWordWrap(True)
        sidebar.addWidget(subtitle)
        self.nav = QListWidget()
        self.nav.setObjectName("navigation")
        self.nav.setIconSize(QSize(22, 22))
        self.nav.addItems(["Início", "Biblioteca", "Adicionar obra", "Downloads", "Google Drive", "Diagnóstico", "Configurações"])
        for index, name in enumerate(('home', 'book', 'add', 'download', 'cloud', 'check', 'settings')):
            self.nav.item(index).setIcon(icon(name))
        sidebar.addWidget(self.nav, 1)
        sidebar.addWidget(QLabel(f"v{__version__} · PDFs automáticos"))
        root.addWidget(side)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.dashboard_ui()
        self.add_ui()
        self.queue_ui()
        self.diagnostic_ui()
        self.settings_ui()
        self.library_ui()
        from app.ui.drive_controller import DriveController
        self.drive = DriveController(self)
        self.stack.addWidget(self.drive.panel)
        self.nav.currentRowChanged.connect(self.navigate)
        self.show_page(5)
        self.manager = DownloadManager(db, settings)
        self.worker = QueueWorker(self.manager, self)
        self.worker.error.connect(self.error)
        # Network/page events can arrive much faster than the screen needs to paint.
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.setInterval(200)
        self.refresh_timer.timeout.connect(self.request_refresh)
        self.worker.changed.connect(self.schedule_refresh)
        if start_queue:
            def recover():
                self.library.repair_site_titles()
                result = recover_downloads(self.library, Path(self.settings.library))
                if not self.settings.keep_images:
                    from app.services.cleanup import cleanup_library
                    cleanup_library(self.db)
                return result
            self.job(recover, self.recovery_finished,
                     cleanup=self.start_downloads)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.request_refresh)
        self.timer.start(1000)
        self.apply_theme()
        if start_queue:
            self.request_refresh()
        else:
            self.refresh_queue()

    def show_page(self, index):
        self.nav.setCurrentRow([0, 5, 1, 2, 6, 3, 4].index(index))

    def navigate(self, index):
        index = [0, 5, 1, 2, 6, 3, 4][index]
        self.stack.setCurrentIndex(index)
        page = self.stack.widget(index)
        if page and hasattr(page, 'verticalScrollBar'):
            QTimer.singleShot(0, lambda: page.verticalScrollBar().setValue(0))

    def page(self, title, subtitle):
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(12)
        eyebrow = QLabel("MANGA MANAGER  /  SEU ESPAÇO")
        eyebrow.setObjectName("eyebrow")
        layout.addWidget(eyebrow)
        heading = QLabel(title)
        heading.setObjectName("heading")
        layout.addWidget(heading)
        caption = QLabel(subtitle)
        caption.setWordWrap(True)
        caption.setObjectName("caption")
        layout.addWidget(caption)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(page)
        self.stack.addWidget(scroll)
        return layout

    def library_ui(self):
        from app.ui.books import Books
        from app.services.reading import Reading
        self.reading = Reading(self.db)
        self.books = Books()
        self.stack.addWidget(self.books)
        self.reader = None
        self.pending_read = {}
        self.latest_read = {}
        self.read_busy = False
        self.covers_busy = False
        import threading
        self.covers_cancelled = threading.Event()
        self.read_timer = QTimer(self)
        self.read_timer.setSingleShot(True)
        self.read_timer.setInterval(300)
        self.read_timer.timeout.connect(self.persist_reading)
        self.books.openWork.connect(self.open_work)
        self.books.openChapter.connect(self.open_reader)
        self.books.resumeWork.connect(self.resume_work)
        self.books.markChapters.connect(self.mark_read)
        self.books.renameWork.connect(self.rename_work)
        self.books.downloadChapters.connect(self.download_from_books)
        self.books.refreshCovers.connect(self.update_covers)
        self.books.chooseCover.connect(self.choose_cover)
        self.books.importFolder.connect(self.import_folder)

    def choose_cover(self, mid):
        path, _ = QFileDialog.getOpenFileName(self, 'Capa da obra', '', 'Imagens (*.jpg *.jpeg *.png *.webp)')
        if path:
            from app.services.covers import save_cover
            self.job(lambda: save_cover(self.db, mid, Path(path).read_bytes(), self.data_root), lambda _: self.request_refresh())

    def open_work(self, mid):
        self.requested_work = mid
        def show(chapters):
            if self.requested_work == mid:
                self.books.show_work(mid, chapters)
                self.show_page(5)
        self.job(lambda: self.reading.chapters(mid), show)

    def mark_read(self, ids, read):
        if ids:
            for cid in ids:
                self.latest_read.pop(cid, None)
                self.pending_read.pop(cid, None)
            if self.reader and self.reader.chapter and self.reader.chapter['id'] in ids:
                self.reader.finished = read
            updated = timestamp()
            self.job(lambda: self.reading.mark(ids, read, updated), lambda _: self.refresh_books())

    def refresh_books(self):
        self.request_refresh()
        if self.books.mid:
            self.open_work(self.books.mid)

    def rename_work(self, mid, name):
        self.job(lambda: self.reading.rename(mid, name), lambda _: self.refresh_books())

    def download_from_books(self, ids):
        if ids:
            self.job(lambda: self.library.enqueue(ids, skip_complete=True),
                     lambda _: (self.request_refresh(), self.show_page(2)))

    def update_covers(self):
        if self.covers_busy:
            return
        from app.services.covers import refresh_covers
        self.covers_busy = True
        self.covers_cancelled.clear()
        def done(report):
            self.request_refresh()
            self.statusBar().showMessage(f"{report['saved']} capas atualizadas · {len(report['failed'])} indisponíveis.", 10000)
        self.job(lambda: asyncio.run(refresh_covers(self.db, self.data_root, self.settings, self.covers_cancelled)), done,
                 lambda: setattr(self, 'covers_busy', False))

    def resume_work(self, mid):
        self.job(lambda: self.reading.resume(mid),
                 lambda chapter: self.display_reader(chapter) if chapter else self.statusBar().showMessage('Baixe um capítulo para começar a ler.', 10000))

    def open_reader(self, cid):
        def load():
            rows = self.db.query('SELECT * FROM chapters WHERE id=?', (cid,))
            return dict(rows[0], pdf=str(self.reading.pdf(rows[0]))) if rows else None
        self.job(load, self.display_reader)

    def display_reader(self, chapter):
        if not chapter or not Path(chapter['pdf']).is_file():
            self.statusBar().showMessage('Este capítulo ainda não tem PDF. Selecione-o e clique em Baixar selecionados.', 15000)
            return
        if self.reader is None:
            from app.ui.reader import Reader
            self.reader = Reader(self)
            self.reader.progress.connect(self.queue_read_progress)
            self.reader.failure.connect(self.error)
            self.reader.moveChapter.connect(self.move_reader)
            self.reader.closed.connect(lambda: setattr(self, 'reader', None))
        saved = self.latest_read.get(chapter['id'])
        if saved:
            chapter = dict(chapter, read_page=saved['page'], read_total=saved['total'], read_x=saved['x'],
                           read_y=saved['y'], read_zoom=saved['zoom'], read_scroll=saved['scroll'], is_read=chapter['is_read'] or saved['finished'])
        self.reader.setStyleSheet(self.styleSheet())
        self.reader.open_chapter(chapter)

    def move_reader(self, delta):
        if not self.reader or not self.reader.chapter:
            return
        chapter = self.reader.chapter
        def adjacent():
            chapters = self.reading.chapters(chapter['manga_id'])
            position = next(i for i, c in enumerate(chapters) if c['id'] == chapter['id']) + delta
            return chapters[position] if 0 <= position < len(chapters) else None
        self.job(adjacent, lambda c: self.display_reader(c) if c else self.statusBar().showMessage('Fim da lista de capítulos.', 8000))

    def queue_read_progress(self, progress):
        progress = dict(progress, updated=timestamp())
        self.latest_read[progress['cid']] = progress
        self.pending_read[progress['cid']] = progress
        self.read_timer.start()

    def persist_reading(self):
        if self.read_busy or not self.pending_read:
            return
        progress = list(self.pending_read.values())
        self.pending_read.clear()
        self.read_busy = True
        def save():
            for position in progress:
                self.reading.progress(**position)
        def done(_):
            self.request_refresh()
            if self.books.mid and (self.reader is None or not self.reader.isVisible()):
                self.open_work(self.books.mid)
        def finished():
            self.read_busy = False
            if self.pending_read:
                self.read_timer.start()
        self.job(save, done, finished)

    def buttons(self, layout, actions):
        actions = list(actions)
        for start in range(0, len(actions), 4):
            row = QHBoxLayout()
            for label, function in actions[start:start+4]:
                button = QPushButton(label)
                button.clicked.connect(function)
                if label.startswith(("Baixar e gerar", "Adicionar uma obra", "Salvar configurações")):
                    button.setObjectName("primary")
                row.addWidget(button)
            layout.addLayout(row)

    def error(self, message):
        self.statusBar().showMessage(message, 15000)
        QMessageBox.warning(self, "Não foi possível concluir", message)

    def job(self, function, result, cleanup=None):
        job = Job(function, self)
        self.jobs.append(job)
        job.result.connect(result)
        job.error.connect(self.error)
        if cleanup:
            job.finished.connect(cleanup)
        job.finished.connect(lambda: self.jobs.remove(job))
        job.finished.connect(job.deleteLater)
        job.start()
        return job

    def dashboard_ui(self):
        layout = self.page("Seu próximo capítulo começa aqui", "Baixe suas obras e receba os PDFs, com tudo organizado em uma pasta.")
        hero = QFrame()
        hero.setObjectName('hero')
        content = QHBoxLayout(hero)
        content.setContentsMargins(24, 16, 24, 16)
        copy = QVBoxLayout()
        title = QLabel("Menos trabalho.\nMais histórias.")
        title.setObjectName('heroTitle')
        copy.addWidget(title)
        caption = QLabel("Escolha os capítulos. Nós cuidamos do PDF.")
        caption.setObjectName('heroCaption')
        copy.addWidget(caption)
        content.addLayout(copy, 1)
        add = QPushButton('Novo download')
        add.setObjectName('heroButton')
        add.clicked.connect(lambda: self.show_page(1))
        content.addWidget(add)
        layout.addWidget(hero)
        cards = QHBoxLayout()
        self.stat_values = []
        for label in ('Obras', 'Na fila', 'Capítulos locais'):
            card = QFrame()
            card.setObjectName('statCard')
            body = QVBoxLayout(card)
            body.setContentsMargins(22, 10, 22, 10)
            value = QLabel('0')
            value.setObjectName('statValue')
            self.stat_values.append(value)
            body.addWidget(value)
            text = QLabel(label)
            text.setObjectName('statLabel')
            body.addWidget(text)
            cards.addWidget(card)
        layout.addLayout(cards)
        self.stats = QLabel()
        self.stats.setObjectName('caption')
        layout.addWidget(self.stats)
        self.general_progress = QProgressBar()
        layout.addWidget(self.general_progress)
        title = QLabel('Suas obras em progresso')
        title.setObjectName('sectionTitle')
        layout.addWidget(title)
        self.work_progress = table(['Obra', 'Capítulos locais', 'Downloads'])
        self.work_progress.setMinimumHeight(120)
        self.work_progress.setMaximumHeight(160)
        layout.addWidget(self.work_progress, 1)
        self.recent = QTextEdit()
        self.recent.setReadOnly(True)
        self.recent.setFixedHeight(65)
        layout.addWidget(self.recent)
        self.buttons(layout, [('Abrir PDFs', self.open_output), ('Consultar novos capítulos', self.update_all),
                              ('Relatórios', self.open_download_reports)])

    def add_ui(self):
        layout = self.page("Adicionar obra", "Cole uma URL pública e autorizada. Analise, confira os capítulos e escolha o que baixar.")
        row = QHBoxLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://fonte-autorizada.com/manga/obra")
        self.url.setAccessibleName("URL da obra ou capítulo")
        self.url.returnPressed.connect(self.analyze)
        row.addWidget(self.url, 1)
        self.analyze_button = QPushButton("Analisar URL")
        self.analyze_button.clicked.connect(self.analyze)
        row.addWidget(self.analyze_button)
        layout.addLayout(row)
        batch_toggle = QPushButton('Vários links')
        batch_toggle.setObjectName('link')
        batch_toggle.setCheckable(True)
        layout.addWidget(batch_toggle, alignment=Qt.AlignmentFlag.AlignLeft)
        self.batch_panel = QWidget()
        batch_layout = QVBoxLayout(self.batch_panel)
        batch_layout.setContentsMargins(0, 0, 0, 0)
        self.batch_urls = QTextEdit()
        self.batch_urls.setMaximumHeight(95)
        self.batch_urls.setPlaceholderText('Um link por linha. Prioriza PT-BR e pula PDFs já prontos.')
        batch_layout.addWidget(self.batch_urls)
        self.batch_button = QPushButton('Baixar lista de links')
        self.batch_button.clicked.connect(self.download_links)
        batch_layout.addWidget(self.batch_button)
        import threading
        self.batch_cancelled = threading.Event()
        self.batch_cancel = QPushButton('Parar lista')
        self.batch_cancel.setEnabled(False)
        self.batch_cancel.clicked.connect(self.batch_cancelled.set)
        batch_layout.addWidget(self.batch_cancel)
        batch_toggle.toggled.connect(self.batch_panel.setVisible)
        self.batch_panel.hide()
        layout.addWidget(self.batch_panel)
        preview_row = QHBoxLayout()
        self.preview_cover = QLabel("Capa")
        self.preview_cover.setFixedSize(90, 125)
        self.preview_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_row.addWidget(self.preview_cover)
        self.preview_text = QLabel("Sua prévia aparecerá aqui.")
        self.preview_text.setTextFormat(Qt.TextFormat.PlainText)
        self.preview_text.setWordWrap(True)
        preview_row.addWidget(self.preview_text, 1)
        layout.addLayout(preview_row)
        self.work_name = QLineEdit()
        self.work_name.setPlaceholderText("Nome da obra (você pode corrigir antes de baixar)")
        layout.addWidget(self.work_name)
        self.chapter_language = QComboBox()
        self.chapter_language.addItem("Todos os idiomas", "")
        self.chapter_language.currentIndexChanged.connect(self.filter_preview_chapters)
        self.chapter_language.hide()
        layout.addWidget(self.chapter_language)
        self.skip_existing = QCheckBox('Pular capítulos com PDF já pronto')
        self.skip_existing.setChecked(True)
        layout.addWidget(self.skip_existing)
        self.chapter_selection = QListWidget()
        layout.addWidget(self.chapter_selection, 1)
        select = QHBoxLayout()
        for title, state in (("Selecionar todos", Qt.CheckState.Checked), ("Limpar seleção", Qt.CheckState.Unchecked)):
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False, value=state: self.select_all(value))
            select.addWidget(button)
        self.range = QLineEdit()
        self.range.setPlaceholderText("Posições: 1-20, 35, 50-60")
        select.addWidget(self.range)
        button = QPushButton("Selecionar intervalo")
        button.clicked.connect(self.select_range)
        select.addWidget(button)
        layout.addLayout(select)
        self.buttons(layout, [("Baixar e gerar PDFs", lambda: self.confirm_preview(True)),
                              ("Abrir pasta dos PDFs", self.open_output)])

    async def fetch(self, url):
        async with HttpClient(self.settings) as client:
            extractor = Registry(client).select(url)
            try:
                manga = await extractor.get_manga_info(url)
            except ExtractionError:
                if not self.settings.render_javascript:
                    raise
                from app.infrastructure.browser_renderer import BrowserRenderer
                extractor = Registry(BrowserRenderer(client)).select(url)
                manga = await extractor.get_manga_info(url)
            cover = None
            if manga.cover:
                try:
                    cover = await client.image(manga.cover, manga.url)
                    inspect_image(cover)
                except (OSError, ValueError, RuntimeError):
                    cover = None
                except Exception as exc:
                    from app.core.exceptions import MangaError
                    if not isinstance(exc, MangaError):
                        raise
            return manga, cover, extractor.name

    def analyze(self):
        if not self.analyze_button.isEnabled():
            return
        url = self.url.text().strip()
        if not url:
            return
        self.analyze_button.setEnabled(False)
        self.analyze_button.setText("Analisando…")
        self.statusBar().showMessage("Consultando metadados e páginas de listagem…")
        def analyze_work():
            try:
                result = asyncio.run(self.fetch(url))
                old = self.db.query('''SELECT c.title,c.url,c.status FROM chapters c
                    JOIN mangas m ON c.manga_id=m.id WHERE m.url=?''', (result[0].url,))
                return (*result, old)
            except Exception as exc:
                from app.core.security import scrub
                self.db.execute('''INSERT INTO errors(url,category,message,attempts,created,action)
                    VALUES(?,?,?,?,?,?)''', (safe_url(url), 'AnalysisError', scrub(str(exc)), 1, timestamp(),
                    'Confira URL, permissão e adaptador da fonte.'))
                raise
        self.job(analyze_work, self.show_preview, self.analysis_finished)

    def download_links(self):
        if not self.batch_button.isEnabled():
            return
        text = self.batch_urls.toPlainText().strip()
        if not text:
            self.statusBar().showMessage('Cole os links, um por linha.', 5000)
            return
        from app.services.batch import add_links
        self.batch_button.setEnabled(False)
        self.batch_cancelled.clear()
        self.batch_cancel.setEnabled(True)
        self.batch_button.setText('Preparando a lista…')
        def done(results):
            self.request_refresh()
            self.show_page(2)
            self.statusBar().showMessage(f"{sum('error' not in r for r in results)} obras processadas · "
                f"{sum(r.get('skipped', 0) for r in results)} PDFs já prontos · "
                f"{sum('error' in r for r in results)} falhas. Relatório em logs.", 30000)
        def work():
            results = asyncio.run(add_links(text, self.library, self.fetch, self.batch_cancelled))
            atomic_json(self.data_root / 'logs' / 'ultimo-lote-de-links.json', results)
            return results
        def finished():
            self.batch_button.setEnabled(True)
            self.batch_cancel.setEnabled(False)
            self.batch_button.setText('Baixar lista de links')
        self.job(work, done, finished)

    def analysis_finished(self):
        self.analyze_button.setEnabled(True)
        self.analyze_button.setText("Analisar URL")

    def show_preview(self, result):
        manga, cover, adapter = result[:3]
        self.preview = (manga, cover)
        old = result[3] if len(result) > 3 else self.db.query("SELECT c.title,c.url,c.status FROM chapters c JOIN mangas m ON c.manga_id=m.id WHERE m.url=?", (manga.url,))
        self.preview_states = {c['url']: c['status'] for c in old}
        incoming = {c.url: c.title for c in manga.chapters}
        absent = sum(c["url"] not in incoming for c in old)
        changed = sum(c["url"] in incoming and incoming[c["url"]] != c["title"] for c in old)
        comparison = f"{changed} títulos alterados · {absent} capítulos anteriores ausentes na listagem (preservados).\n" if old else ""
        self.work_name.setText(manga.title)
        self.preview_text.setText(f"{manga.title}\n{len(manga.chapters)} capítulos únicos · {adapter}\n{comparison}"
            f"{manga.description[:350]}\n" + ("Listagem da API percorrida." if manga.listing_complete else
             "Listagem HTML percorrida; conteúdo oculto pode não estar disponível."))
        self.preview_cover.clear()
        if cover:
            pixmap = QPixmap()
            pixmap.loadFromData(cover)
            self.preview_cover.setPixmap(pixmap.scaled(90, 125, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.chapter_language.blockSignals(True)
        self.chapter_language.clear()
        self.chapter_language.addItem("Todos os idiomas", "")
        languages = sorted({c.language for c in manga.chapters if c.language})
        for language in languages:
            self.chapter_language.addItem(f"Idioma: {language.upper()}", language)
        self.chapter_language.setVisible(bool(languages))
        preferred = next((lang for lang in ("pt-br", "pt", "en") if lang in languages), "")
        self.chapter_language.setCurrentIndex(max(0, self.chapter_language.findData(preferred)))
        self.chapter_language.blockSignals(False)
        self.filter_preview_chapters()
        self.show_page(1)
        self.statusBar().showMessage("Prévia pronta. Selecione os capítulos e confirme.", 15000)

    def filter_preview_chapters(self, *args):
        if not self.preview:
            return
        manga = self.preview[0]
        language = self.chapter_language.currentData()
        self.preview_chapters = [c for c in manga.chapters if not language or c.language == language]
        self.chapter_selection.clear()
        existing = self.preview_states
        for chapter in self.preview_chapters:
            state = existing.get(chapter.url, "pending")
            item = QListWidgetItem(f"{chapter.title}   ·   {STATUS.get(state, state)}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked if state in ("verified", "downloaded") else Qt.CheckState.Checked)
            self.chapter_selection.addItem(item)

    def select_all(self, state):
        for i in range(self.chapter_selection.count()):
            self.chapter_selection.item(i).setCheckState(state)

    def select_range(self):
        try:
            indexes = set()
            for part in self.range.text().split(","):
                bounds = [int(p.strip()) for p in part.split("-")]
                first, last = bounds if len(bounds) == 2 else (bounds[0], bounds[0])
                if not 1 <= first <= last <= self.chapter_selection.count():
                    raise ValueError
                indexes.update(range(first-1, last))
            self.select_all(Qt.CheckState.Unchecked)
            for index in indexes:
                self.chapter_selection.item(index).setCheckState(Qt.CheckState.Checked)
        except ValueError:
            self.error("Use posições válidas, por exemplo 1-20, 35. A posição é a ordem exibida, não a numeração da fonte.")

    def confirm_preview(self, enqueue):
        if getattr(self, 'persist_busy', False):
            return
        if not self.preview:
            self.error("Analise uma URL antes de confirmar.")
            return
        manga, cover = self.preview
        from dataclasses import replace
        name = self.work_name.text().strip()
        if not name:
            self.error("Informe o nome da obra antes de baixar.")
            return
        manga = replace(manga, title=name)
        # Capture selections on GUI thread before worker access.
        from app.infrastructure.filesystem import identity
        selected = [identity(c.url) for i, c in enumerate(self.preview_chapters) if self.chapter_selection.item(i).checkState() == Qt.CheckState.Checked]
        skip_existing = self.skip_existing.isChecked()
        def persist():
            mid, new = self.library.add(manga)
            if cover:
                folder = Path(self.db.query("SELECT folder FROM mangas WHERE id=?", (mid,))[0]["folder"])
                from app.services.covers import save_cover
                save_cover(self.db, mid, cover, self.data_root)
            if enqueue:
                self.library.enqueue(selected, skip_complete=skip_existing)
            return mid, len(new)
        def complete(result):
            self.request_refresh()
            self.statusBar().showMessage(f"Obra salva · {result[1]} capítulos novos.", 15000)
            self.show_page(2)
        self.persist_busy = True
        self.statusBar().showMessage('Preparando os capítulos para download…')
        def finished():
            self.persist_busy = False
        self.job(persist, complete, finished)

    def queue_ui(self):
        layout = self.page('Downloads', 'Dois capítulos em paralelo por padrão. Aqui ficam só tarefas atuais e falhas recentes.')
        hero = QFrame()
        hero.setObjectName('queueHero')
        content = QVBoxLayout(hero)
        content.setContentsMargins(22, 18, 22, 18)
        self.queue_hint = QLabel('Sua fila está pronta para uma nova história.')
        self.queue_hint.setObjectName('sectionTitle')
        self.queue_hint.setWordWrap(True)
        content.addWidget(self.queue_hint)
        self.queue_progress = QProgressBar()
        self.queue_progress.setTextVisible(False)
        content.addWidget(self.queue_progress)
        layout.addWidget(hero)
        row = QHBoxLayout()
        self.queue_buttons = {}
        for label, action in [('Pausar', 'pause'), ('Retomar', 'resume'), ('Tentar novamente', 'retry')]:
            button = QPushButton(label)
            button.setToolTip('Aplica aos capítulos selecionados. Sem seleção, aplica à fila inteira.')
            button.clicked.connect(lambda checked=False, value=action: self.queue_action(value))
            self.queue_buttons[action] = button
            row.addWidget(button)
        row.addStretch()
        for label, callback in [('Abrir PDFs', self.open_output), ('Relatórios', self.open_download_reports)]:
            button = QPushButton(label)
            button.setObjectName('link')
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.queue_table = table(['Obra / capítulo', 'Status', 'Progresso', 'Erro'])
        self.queue_search = QLineEdit()
        self.queue_search.setPlaceholderText('Buscar obra, capítulo ou erro na fila…')
        self.queue_search.textChanged.connect(self.filter_queue)
        layout.addWidget(self.queue_search)
        self.queue_table.verticalHeader().setDefaultSectionSize(64)
        self.queue_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.queue_table.itemDoubleClicked.connect(self.show_task_error)
        self.queue_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.queue_table.customContextMenuRequested.connect(self.queue_menu)
        self.queue_table.itemSelectionChanged.connect(self.update_queue_buttons)
        layout.addWidget(self.queue_table, 1)
        self.empty_queue = QLabel('Tudo em dia.\n\nAdicione uma obra para começar. Seus PDFs ficam na pasta escolhida.')
        self.empty_queue.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_queue.setWordWrap(True)
        self.empty_queue.setObjectName('sectionTitle')
        layout.addWidget(self.empty_queue, 1)
        hint = QLabel('Clique com o botão direito em um capítulo para cancelar ou remover da fila.')
        hint.setObjectName('caption')
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def update_queue_buttons(self):
        if not hasattr(self, 'queue_buttons'):
            return
        selected = {i.row() for i in self.queue_table.selectionModel().selectedRows()}
        candidates = [t for i, t in enumerate(self.task_rows) if not self.queue_table.isRowHidden(i) and (not selected or i in selected)]
        states = {'pause': ('queued', 'running'), 'resume': ('paused',), 'retry': ('failed', 'cancelled')}
        for action, button in self.queue_buttons.items():
            eligible = self.retry_candidates() if action == 'retry' and not selected else candidates
            button.setEnabled(any(t['status'] in states[action] for t in eligible))

    def retry_candidates(self):
        text = self.queue_search.text().strip().casefold()
        return [t for t in self.failed_tasks if text in f"{t['manga']} {t['chapter']} {t['error']} falhou".casefold()]

    def queue_menu(self, point):
        item = self.queue_table.itemAt(point)
        if not item:
            return
        self.queue_table.selectRow(item.row())
        menu = QMenu(self)
        for label, command in [('Cancelar capítulo', 'cancel'), ('Remover da lista', 'remove')]:
            action = menu.addAction(label)
            action.triggered.connect(lambda checked=False, value=command: self.queue_action(value))
        self.queue_contextmenu = menu
        menu.popup(self.queue_table.viewport().mapToGlobal(point))

    def filter_queue(self):
        text = self.queue_search.text().strip().casefold()
        self.queue_table.selectionModel().blockSignals(True)
        for row, task in enumerate(self.task_rows):
            match = text in f"{task['manga']} {task['chapter']} {STATUS.get(task['status'], task['status'])} {task['error']}".casefold()
            self.queue_table.setRowHidden(row, not match)
            if not match:
                for column in range(self.queue_table.columnCount()):
                    self.queue_table.item(row, column).setSelected(False)
        self.queue_table.selectionModel().blockSignals(False)
        self.update_queue_buttons()

    def open_download_reports(self):
        self.reports.destination.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.reports.destination.resolve())))

    def enable_completion(self):
        self.finish_enabled = True
        self.request_refresh()

    def start_downloads(self):
        self.enable_completion()
        self.worker.start()
        self.update_covers()

    def completion_finished(self, reports):
        if not reports:
            return
        self.request_refresh()
        if self.settings.drive_auto:
            QTimer.singleShot(1500, self.drive.auto_sync)
        message = '\n'.join(f"{r['work']}: {r['completed']} capítulos concluídos" +
                            (f", {r['failed']} falhas para repetir" if r['failed'] else '') +
                            (f", {r['cancelled']} cancelados" if r['cancelled'] else '') +
                            (f", {r['missing_pdf']} registros anteriores sem PDF localizado" if r['missing_pdf'] else '') for r in reports)
        success = all(not r['failed'] and not r['cancelled'] and not r['missing_pdf'] for r in reports)
        box = QMessageBox(self)
        box.setWindowTitle('Downloads concluídos' if success else 'Downloads finalizados com pendências')
        box.setIcon(QMessageBox.Icon.Information if success else QMessageBox.Icon.Warning)
        box.setText(('Todos os capítulos destas obras foram finalizados!\n\n' if success else '') + message +
                    '\n\nRelatório salvo. As tarefas finalizadas foram removidas da lista.')
        box.setDetailedText('\n'.join(r['file'] for r in reports))
        show = box.addButton('Ver relatório', QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Ok)
        box.buttonClicked.connect(lambda button: QDesktopServices.openUrl(QUrl.fromLocalFile(reports[-1]['file'])) if button is show else None)
        self.completion_notices.append(box)
        box.finished.connect(lambda _: self.completion_notices.remove(box))
        box.open()
        self.statusBar().showMessage(message + ' · Relatório salvo em logs/downloads', 30000)

    def queue_action(self, action):
        indexes = {index.row() for index in self.queue_table.selectionModel().selectedRows()}
        states = {'pause': ('queued', 'running'), 'resume': ('paused',), 'retry': ('failed','cancelled'),
                  'cancel': ('queued','running','paused','failed'), 'remove': tuple(STATUS)}
        candidates = [task for i, task in enumerate(self.task_rows) if not self.queue_table.isRowHidden(i) and (not indexes or i in indexes)]
        if action == 'retry' and not indexes:
            candidates = self.retry_candidates()
        ids = [task['id'] for task in candidates if task['status'] in states[action]]
        def complete(count):
            self.statusBar().showMessage(f'{count} capítulos atualizados.', 5000)
            self.request_refresh()
        self.job(lambda: self.manager.commands(ids, action), complete)

    def resume_all(self):
        for task in self.db.tasks():
            if task["status"] == "paused":
                self.manager.command(task["id"], "resume")

    def show_task_error(self, item):
        row = item.row()
        if row >= len(self.task_rows):
            return
        task = self.task_rows[row]
        errors = self.db.query("SELECT * FROM errors WHERE task_id=? ORDER BY id DESC LIMIT 1", (task["id"],))
        if errors:
            error = errors[0]
            QMessageBox.information(self, "Detalhes da falha", f"Obra: {task['manga']}\nCapítulo: {task['chapter']}\n"
                f"Página: {error['page'] or 'desconhecida'}\nURL: {error['url']}\nCategoria: {error['category']}\n"
                f"Data UTC: {error['created']}\nTentativas: {error['attempts']}\nHTTP: {error['http_status'] or 'indisponível'}\n"
                f"Causa: {error['message']}\nAção: {error['action']}")

    def retry_all(self):
        for task in self.db.tasks():
            if task["status"] == "failed":
                self.manager.command(task["id"], "retry")

    def schedule_refresh(self):
        if not self.refresh_timer.isActive() and not self.closing:
            self.refresh_timer.start()

    def queue_snapshot(self):
        return (self.db.tasks(), self.db.mangas(),
                self.db.query('SELECT message,created FROM errors ORDER BY id DESC LIMIT 4'),
                self.db.query('SELECT title FROM mangas ORDER BY updated DESC LIMIT 4'))

    def request_refresh(self):
        if self.refresh_busy or self.closing:
            return
        self.refresh_busy = True
        def finished():
            self.refresh_busy = False
        self.job(self.queue_snapshot, self.apply_queue_snapshot, finished)

    def refresh_queue(self):
        """Immediate refresh for explicit actions/tests; background polling uses request_refresh."""
        if not hasattr(self, "manager"):
            return
        self.apply_queue_snapshot(self.queue_snapshot())

    def apply_queue_snapshot(self, snapshot):
        all_tasks, mangas, errors, recent = snapshot
        latest = {}
        for task in all_tasks:
            if task['chapter_id'] not in latest or task['id'] > latest[task['chapter_id']]['id']:
                latest[task['chapter_id']] = task
        self.failed_tasks = [t for t in latest.values() if t['status'] == 'failed']
        tasks = [t for t in all_tasks if latest[t['chapter_id']]['id'] == t['id'] and t['status'] not in ('complete', 'cancelled')
                 and (t['status'] != 'failed' or (t['updated'] or '') >= self.session_started)]
        selected = {self.task_rows[i.row()]["id"] for i in self.queue_table.selectionModel().selectedRows() if i.row() < len(self.task_rows)}
        changed_order = [t['id'] for t in tasks] != [t['id'] for t in self.task_rows]
        self.task_rows = tasks
        if self.finish_enabled and not self.completion_busy and any(t['status'] in ('complete','cancelled') for t in all_tasks):
            self.completion_busy = True
            report_job = self.job(self.reports.finish_ready, self.completion_finished,
                                  cleanup=lambda: setattr(self, 'completion_busy', False))
            # Avoid repeating a disk/permission error dialog every timer tick.
            report_job.error.connect(lambda _: setattr(self, 'finish_enabled', False))
        if snapshot == self.last_queue_snapshot:
            return
        self.last_queue_snapshot = snapshot
        rows = []
        for task in self.task_rows:
            percent = f"{task['done']/task['total']:.0%}" if task['total'] else "0%"
            status = "Gerando PDF" if task['status'] == 'running' and task['error'] == 'Gerando PDF…' else STATUS.get(task['status'], task['status'])
            rows.append([f"{task['manga']}\n{task['chapter']}", status, percent,
                         task['error'] if task['status'] == 'failed' else ""])
        self.queue_table.selectionModel().blockSignals(True)
        fill(self.queue_table, rows)
        if changed_order:
            self.queue_table.clearSelection()
        for i, task in enumerate(self.task_rows):
            colors = {'complete': '#4abf94', 'failed': '#ec7b85', 'running': '#9988ff', 'paused': '#d8af61'}
            self.queue_table.item(i, 1).setForeground(QColor(colors.get(task['status'], '#8993a9')))
        self.queue_table.setVisible(bool(rows))
        self.empty_queue.setVisible(not rows)
        for i, task in enumerate(self.task_rows):
            if changed_order and task["id"] in selected:
                self.queue_table.selectionModel().select(self.queue_table.model().index(i, 0), QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        self.queue_table.selectionModel().blockSignals(False)
        self.filter_queue()
        active = [t for t in self.task_rows if t["status"] == "running"]
        failed = self.failed_tasks
        completed = sum(t["status"] == "complete" for t in all_tasks)
        pending = sum(t["status"] in ("queued", "paused", "running") for t in self.task_rows)
        self.books.update_mangas(mangas)
        self.drive.panel.set_mangas(mangas)
        self.update_queue_buttons()
        for label, value in zip(self.stat_values, (len(mangas), pending, sum(m['completed'] or 0 for m in mangas))):
            label.setText(str(value))
        self.stats.setText(f"{len(active)} em andamento · {pending} na fila · {len(failed)} precisam de atenção")
        current = next(iter(active), None)
        self.queue_hint.setText(f"{current['manga']} · {current['chapter']}" if current else
                                ('Downloads pausados. Retome quando quiser.' if any(t['status']=='paused' for t in self.task_rows) else
                                 (f'{pending} capítulos aguardando download.' if pending else
                                  (f'{len(failed)} capítulos com falha anterior. Use Tentar novamente; os detalhes ficam nos logs.' if failed else 'Tudo em dia. Seus relatórios estão salvos.'))))
        self.queue_progress.setRange(0, current['total'] if current and current['total'] else 1)
        self.queue_progress.setValue(current['done'] if current else 0)
        self.queue_progress.setVisible(bool(current))
        denominator = completed + pending + len(failed)
        self.general_progress.setRange(0, denominator or 1)
        self.general_progress.setValue(completed)
        self.general_progress.setFormat("%p% das tarefas de capítulos concluídas" if denominator else "Fila vazia")
        fill(self.work_progress, [[m["title"], f"{m['completed'] or 0}/{m['chapters']}",
              f"{sum(t['status']=='running' and t['manga']==m['title'] for t in self.task_rows)} ativas"] for m in mangas])
        text = ("Adicionadas recentemente: " + ", ".join(m["title"] for m in recent) + "\n\nFalhas recentes:\n" +
                "\n".join(f"{e['created']} · {e['message']}" for e in errors))
        if self.recent.toPlainText() != text:
            self.recent.setPlainText(text)

    def import_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Importar biblioteca (sem alterar arquivos)")
        if path:
            self.job(lambda: self.library.import_folder(Path(path)),
                     lambda count: (self.request_refresh(), self.statusBar().showMessage(f"{count} capítulos importados.", 15000)))

    def backup(self):
        path, _ = QFileDialog.getSaveFileName(self, "Backup de metadados (não inclui imagens)", "biblioteca-backup.sqlite3", "SQLite (*.sqlite3)")
        if path:
            self.job(lambda: self.db.backup(Path(path)), lambda _: self.statusBar().showMessage("Backup salvo.", 10000))

    def update_all(self):
        urls = [m["url"] for m in self.db.mangas() if m["url"]]
        if not urls:
            self.statusBar().showMessage("Não há fontes registradas.", 10000)
            return
        async def update():
            results = []
            async with HttpClient(self.settings) as client:
                for url in urls:
                    from app.core.exceptions import MangaError
                    try:
                        try:
                            manga = await Registry(client).select(url).get_manga_info(url)
                        except ExtractionError:
                            if not self.settings.render_javascript:
                                raise
                            from app.infrastructure.browser_renderer import BrowserRenderer
                            manga = await Registry(BrowserRenderer(client)).select(url).get_manga_info(url)
                        mid, new = self.library.add(manga)
                        results.append((manga.title, new, ""))
                    except (MangaError, OSError) as exc:
                        results.append((safe_url(url), [], str(exc)))
            return results
        def display(results):
            total = sum(len(r[1]) for r in results)
            report = "\n".join(f"{title}: {len(new)} novos" + (f" · {error}" if error else "") for title, new, error in results)
            box = QMessageBox(self)
            box.setWindowTitle("Atualizações da biblioteca")
            box.setText(report + f"\n\nBaixar os {total} capítulos novos?")
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if box.exec() == QMessageBox.StandardButton.Yes:
                self.library.enqueue([cid for _, ids, _ in results for cid in ids])
                self.show_page(2)
        self.job(lambda: asyncio.run(update()), display)

    def open_output(self):
        rows = self.queue_table.selectionModel().selectedRows()
        path = Path(self.settings.library)
        if rows:
            task = self.task_rows[rows[0].row()]
            chapter = self.db.query('SELECT folder FROM chapters WHERE id=?', (task['chapter_id'],))[0]
            path = Path(chapter['folder']).parent / 'PDF'
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def recovery_finished(self, report):
        self.request_refresh()
        if report['queued'] or report['relocated']:
            self.statusBar().showMessage(f"{report['queued']} capítulos prontos para gerar PDF · {report['relocated']} pastas reencontradas.", 20000)

    def recover_folder(self):
        path = QFileDialog.getExistingDirectory(self, 'Localizar pasta de imagens já baixadas', self.settings.library)
        if path:
            self.job(lambda: recover_downloads(self.library, Path(path)), self.recovery_finished)

    def diagnostic_ui(self):
        layout = self.page("Diagnóstico dos arquivos", "Verifique imagens ausentes ou corrompidas e repare os capítulos com falha.")
        self.diagnostic_table = table(["Obra", "Capítulo", "Integridade", "Problemas"])
        self.diagnostic_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.diagnostic_table, 1)
        self.buttons(layout, [("Verificar biblioteca", self.diagnose), ("Reparar selecionados", self.repair),
                              ("Exportar erros", self.export_errors), ("Diagnóstico do sistema", self.system_diagnostic), ("Recuperar pasta movida", self.recover_folder)])
        self.diagnostic_text = QTextEdit()
        self.diagnostic_text.setReadOnly(True)
        self.diagnostic_text.setMaximumHeight(150)
        layout.addWidget(self.diagnostic_text)

    def diagnose(self):
        self.show_page(3)
        self.statusBar().showMessage("Verificando arquivos locais…")
        def display(results):
            self.diagnostic_rows = results
            fill(self.diagnostic_table, [[r["manga"], r["chapter"], STATUS.get(r["status"], r["status"]),
                                          "; ".join(r["issues"]) or "Imagens e hashes correspondem ao manifesto"] for r in results])
            self.statusBar().showMessage(f"{len(results)} capítulos examinados.", 15000)
        self.job(self.library.diagnostic, display)

    def repair(self):
        ids = [self.diagnostic_rows[i.row()]["id"] for i in self.diagnostic_table.selectionModel().selectedRows()]
        valid = [c["id"] for cid in ids for c in self.db.query("SELECT id FROM chapters WHERE id=? AND url IS NOT NULL", (cid,))]
        self.library.enqueue(valid)
        self.show_page(2)
        self.request_refresh()

    def export_errors(self):
        path, _ = QFileDialog.getSaveFileName(self, "Relatório de erros", "erros.json", "JSON (*.json)")
        if path:
            errors = self.db.query("""SELECT e.*,c.title chapter,m.title manga FROM errors e
                LEFT JOIN chapters c ON c.id=e.chapter_id LEFT JOIN mangas m ON m.id=c.manga_id""")
            atomic_json(Path(path), errors)
            self.statusBar().showMessage("Relatório salvo.", 10000)

    def system_diagnostic(self):
        import shutil
        def inspect():
            root = Path(self.settings.library)
            while not root.exists():
                root = root.parent
            return f"Manga Manager {__version__}\n{platform.platform()} · Python {platform.python_version()}\n" + \
                f"Banco: SQLite v2 · Qt {__import__('PySide6').__version__}\n" + \
                f"Disco livre: {shutil.disk_usage(root).free/1024**3:.2f} GB\nBiblioteca: {self.library.storage()/1024**3:.2f} GB\n" + \
                "Modo: HTML público; Chromium opcional na instalação Python, ausente do pacote portátil."
        self.job(inspect, self.diagnostic_text.setPlainText)

    def settings_ui(self):
        layout = self.page("Do seu jeito", "Escolha onde guardar os PDFs e o tema que combina com você.")
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.destination = QLineEdit(self.settings.library)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.destination)
        choose = QPushButton("Escolher pasta")
        choose.clicked.connect(self.choose_folder)
        folder_row.addWidget(choose)
        form.addRow("Pasta dos downloads", folder_row)
        self.theme = QComboBox()
        self.theme.addItems(["Escuro", "Claro"])
        self.theme.setCurrentIndex(self.settings.theme == "light")
        form.addRow("Tema", self.theme)
        self.download_workers = QSpinBox()
        self.download_workers.setRange(1, 3)
        self.download_workers.setValue(self.settings.download_workers)
        form.addRow("Capítulos simultâneos", self.download_workers)
        layout.addLayout(form)
        toggle = QPushButton('Opções avançadas')
        toggle.setObjectName('link')
        toggle.setCheckable(True)
        layout.addWidget(toggle, alignment=Qt.AlignmentFlag.AlignLeft)
        self.advanced_settings = QWidget()
        advanced = QVBoxLayout(self.advanced_settings)
        advanced.setContentsMargins(0, 8, 0, 8)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        advanced.addLayout(form)
        toggle.toggled.connect(self.advanced_settings.setVisible)
        self.advanced_settings.hide()
        self.javascript = QCheckBox("Renderizar com Chromium se o HTML não reconhecer o conteúdo")
        self.javascript.setChecked(self.settings.render_javascript)
        form.addRow("JavaScript opcional", self.javascript)
        self.setting_spins = {}
        for key, label, low, high in (("per_domain", "Conexões por domínio", 1, 4),
                                      ("timeout", "Tempo limite (s)", 5, 120), ("retries", "Tentativas", 1, 5),
                                      ("max_image_mb", "Tamanho máximo por imagem (MB)", 1, 200),
                                      ("max_listing_pages", "Limite de páginas de listagem", 1, 1000)):
            spin = QSpinBox()
            spin.setRange(low, high)
            spin.setValue(getattr(self.settings, key))
            self.setting_spins[key] = spin
            form.addRow(label, spin)
        self.naming = QComboBox()
        self.naming.addItems(["{title}", "Capítulo {number} - {title}"])
        self.naming.setCurrentText(self.settings.chapter_pattern)
        form.addRow("Nome do capítulo", self.naming)
        layout.addWidget(self.advanced_settings)
        self.buttons(layout, [("Salvar configurações", self.save_settings), ("Backup dos registros", self.backup), ("Exportar configurações", self.export_settings),
                              ("Importar configurações", self.import_settings), ("Abrir logs", self.open_logs)])
        info = QLabel("Atualizações do aplicativo: instalação manual de versões publicadas pelo mantenedor.\n"
                      "Alterar a pasta afeta obras novas; os downloads existentes continuam em seus locais registrados.\n"
                      "Use somente fontes com permissão. Conteúdo que exige login, CAPTCHA ou acesso restrito será informado.")
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addStretch()

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Pasta da biblioteca")
        if path:
            self.destination.setText(path)

    def save_settings(self):
        candidate = Settings(**asdict(self.settings))
        candidate.library = self.destination.text()
        candidate.theme = "light" if self.theme.currentIndex() else "dark"
        candidate.chapter_pattern = self.naming.currentText()
        candidate.export_format = "pdf"
        candidate.concurrent_tasks = 1
        candidate.download_workers = self.download_workers.value()
        candidate.render_javascript = self.javascript.isChecked()
        for key, spin in self.setting_spins.items():
            setattr(candidate, key, spin.value())
        try:
            candidate.save(self.data_root / "settings.json")
        except (OSError, ValueError) as exc:
            self.error(str(exc))
            return
        self.settings = candidate
        self.manager.settings.download_workers = candidate.download_workers
        self.library = Library(self.db, Path(candidate.library), candidate.chapter_pattern)
        self.apply_theme()
        self.statusBar().showMessage("Configurações salvas. Reinicie para aplicar limites de rede.", 15000)

    def export_settings(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exportar configurações", "configuracoes.json", "JSON (*.json)")
        if path:
            self.settings.save(Path(path))

    def import_settings(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importar configurações", "", "JSON (*.json)")
        if path:
            try:
                candidate = Settings.load(Path(path))
                candidate.save(self.data_root / "settings.json")
                self.statusBar().showMessage("Configurações importadas. Reinicie para aplicar.", 15000)
            except (OSError, ValueError, TypeError) as exc:
                self.error(str(exc))

    def open_logs(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.data_root / "logs")))

    def apply_theme(self):
        self.setStyleSheet(stylesheet(self.settings.theme == 'dark'))

    def closeEvent(self, event):
        self.drive.stop()
        self.covers_cancelled.set()
        if self.reader and self.reader.isVisible():
            self.reader.close()
        if self.pending_read or self.read_busy:
            self.persist_reading()
            QTimer.singleShot(350, self.close)
            event.ignore()
            return
        if any(job.isRunning() for job in self.jobs):
            if self.covers_busy or self.drive.busy:
                QTimer.singleShot(350, self.close)
            self.statusBar().showMessage("Aguarde a análise, diagnóstico ou exportação terminar antes de fechar.", 15000)
            event.ignore()
            return
        self.timer.stop()
        self.refresh_timer.stop()
        self.closing = True
        self.manager.stop()
        if self.worker.isRunning() and not self.worker.wait(5000):
            self.statusBar().showMessage("Encerrando a conexão. Tente fechar novamente em alguns segundos.")
            self.timer.start(1000)
            self.closing = False
            event.ignore()
            return
        event.accept()
