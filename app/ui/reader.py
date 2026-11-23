"""Native, lazily rendered PDF reader. Reading state is saved by the owner worker."""
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QPointF, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                              QLabel, QSpinBox, QComboBox, QLineEdit)
from PySide6.QtPdf import QPdfDocument, QPdfSearchModel
from PySide6.QtPdfWidgets import QPdfView


class Reader(QMainWindow):
    progress = Signal(object)
    moveChapter = Signal(int)
    failure = Signal(str)
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resize(1080, 850)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.chapter = None
        self.restoring = False
        self.finished = False
        self.cache_origin = 0
        self.doc = QPdfDocument(self)
        self.search_model = QPdfSearchModel(self)
        self.search_model.setDocument(self.doc)
        shell = QWidget()
        shell.setObjectName('page')
        self.setCentralWidget(shell)
        layout = QVBoxLayout(shell)
        self.title = QLabel('Leitor')
        self.title.setObjectName('sectionTitle')
        layout.addWidget(self.title)
        controls = QHBoxLayout()
        for text, callback in [('Biblioteca', self.close), ('Capítulo anterior', lambda: self.moveChapter.emit(-1)),
                               ('Próximo capítulo', lambda: self.moveChapter.emit(1))]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            controls.addWidget(button)
        self.page_number = QSpinBox()
        self.page_number.setMinimum(1)
        self.page_number.setPrefix('Página ')
        self.page_number.valueChanged.connect(lambda p: self.jump(p - 1))
        controls.addWidget(self.page_number)
        self.total = QLabel('/ 0')
        controls.addWidget(self.total)
        self.zoom = QComboBox()
        self.zoom.addItems(['Largura', 'Página inteira', '75%', '100%', '125%', '150%', '200%'])
        self.zoom.currentIndexChanged.connect(self.change_zoom)
        controls.addWidget(self.zoom)
        full = QPushButton('Tela cheia')
        full.clicked.connect(self.toggle_fullscreen)
        controls.addWidget(full)
        layout.addLayout(controls)
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Buscar texto no PDF (Ctrl+F). Imagens escaneadas não têm texto pesquisável.')
        self.search.returnPressed.connect(self.find_next)
        self.search.textChanged.connect(self.search_model.setSearchString)
        self.search.textChanged.connect(lambda _: setattr(self, 'search_index', -1))
        search_row.addWidget(self.search)
        find = QPushButton('Próximo resultado')
        find.clicked.connect(self.find_next)
        search_row.addWidget(find)
        layout.addLayout(search_row)
        self.view = QPdfView()
        self.view.setDocument(self.doc)
        self.view.setSearchModel(self.search_model)
        self.view.setPageMode(QPdfView.PageMode.MultiPage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        layout.addWidget(self.view, 1)
        self.note = QLabel('Rolagem contínua · posição salva automaticamente')
        layout.addWidget(self.note)
        nav = self.view.pageNavigator()
        nav.currentPageChanged.connect(self.changed)
        nav.currentLocationChanged.connect(self.changed)
        self.view.verticalScrollBar().valueChanged.connect(self.changed)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(450)
        self.save_timer.timeout.connect(self.flush)
        self.end_timer = QTimer(self)
        self.end_timer.setSingleShot(True)
        self.end_timer.setInterval(1500)
        self.end_timer.timeout.connect(self.reached_end)
        for sequence, callback in [('Ctrl+F', self.search.setFocus), ('F11', self.toggle_fullscreen),
                                   ('Escape', self.leave_fullscreen), ('Ctrl++', lambda: self.zoom_by(1.2)),
                                   ('Ctrl+-', lambda: self.zoom_by(1 / 1.2))]:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)
        self.doc.statusChanged.connect(self.document_ready)
        self.search_index = -1

    def open_chapter(self, chapter):
        self.flush()
        self.end_timer.stop()
        self.restoring = True
        self.chapter = chapter
        self.finished = bool(chapter['is_read'])
        self.cache_origin = chapter['read_page']
        self.doc.close()
        self.view.setDocument(self.doc)
        self.title.setText(chapter['title'])
        self.note.setText('Rolagem contínua · posição salva automaticamente')
        self.setWindowTitle(f"{chapter['title']} · Manga Manager")
        self.search.clear()
        self.search_index = -1
        self.doc.load(str(Path(chapter['pdf'])))
        self.show()
        self.raise_()

    def document_ready(self, status):
        if status == QPdfDocument.Status.Error:
            self.restoring = False
            self.failure.emit('Não foi possível abrir este PDF. Confira o arquivo ou repita a conversão.')
        elif status == QPdfDocument.Status.Ready and self.chapter:
            self.page_number.setMaximum(max(1, self.doc.pageCount()))
            self.total.setText(f'/ {self.doc.pageCount()}')
            QTimer.singleShot(100, self.restore)

    def restore(self):
        if not self.chapter or not self.doc.pageCount():
            return
        page = min(self.chapter['read_page'], self.doc.pageCount() - 1)
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        zoom = self.chapter['read_zoom']
        if zoom > 0:
            self.view.setZoomMode(QPdfView.ZoomMode.Custom)
            self.view.setZoomFactor(zoom)
        self.view.pageNavigator().jump(page, QPointF(self.chapter['read_x'], self.chapter['read_y']))
        if self.chapter.get('read_scroll', 0):
            self.view.verticalScrollBar().setValue(round(self.chapter['read_scroll'] * self.view.verticalScrollBar().maximum()))
        self.restoring = False
        self.changed()

    def jump(self, page):
        if not self.restoring and 0 <= page < self.doc.pageCount():
            self.view.pageNavigator().jump(page, QPointF())

    def change_zoom(self, index):
        if index < 2:
            self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth if index == 0 else QPdfView.ZoomMode.FitInView)
        else:
            self.view.setZoomMode(QPdfView.ZoomMode.Custom)
            self.view.setZoomFactor(float(self.zoom.itemText(index).strip('%')) / 100)
        self.changed()

    def zoom_by(self, factor):
        self.view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.view.setZoomFactor(max(.25, min(4, self.view.zoomFactor() * factor)))
        self.changed()

    def changed(self, *args):
        if self.restoring or not self.chapter or self.doc.status() != QPdfDocument.Status.Ready:
            return
        page = self.view.pageNavigator().currentPage()
        # Qt keeps a cache by page count, which is expensive for long manhwa pages.
        # Recycle it through public zoom APIs every third page, preserving the view.
        if abs(page - self.cache_origin) >= 3:
            self.cache_origin = page
            position = self.view.verticalScrollBar().value()
            mode, zoom = self.view.zoomMode(), self.view.zoomFactor()
            self.restoring = True
            self.view.setZoomMode(QPdfView.ZoomMode.FitInView if mode != QPdfView.ZoomMode.FitInView else QPdfView.ZoomMode.FitToWidth)
            self.view.setZoomMode(mode)
            if mode == QPdfView.ZoomMode.Custom:
                self.view.setZoomFactor(zoom)
            self.view.verticalScrollBar().setValue(position)
            self.restoring = False
        self.page_number.blockSignals(True)
        self.page_number.setValue(page + 1)
        self.page_number.blockSignals(False)
        self.save_timer.start()
        bar = self.view.verticalScrollBar()
        if page == self.doc.pageCount() - 1 and bar.value() >= bar.maximum() - 3:
            if not self.end_timer.isActive():
                self.end_timer.start()
        else:
            self.end_timer.stop()

    def reached_end(self):
        bar = self.view.verticalScrollBar()
        if self.view.pageNavigator().currentPage() == self.doc.pageCount() - 1 and bar.value() >= bar.maximum() - 3:
            self.finished = True
            self.note.setText('Capítulo concluído · leitura salva')
            self.flush()

    def flush(self):
        self.save_timer.stop()
        if self.restoring or not self.chapter or self.doc.status() != QPdfDocument.Status.Ready:
            return
        nav = self.view.pageNavigator()
        location = nav.currentLocation()
        zoom = self.view.zoomFactor() if self.view.zoomMode() == QPdfView.ZoomMode.Custom else 0
        self.progress.emit(dict(cid=self.chapter['id'], page=nav.currentPage(), total=self.doc.pageCount(),
                                x=location.x(), y=location.y(), zoom=zoom, finished=self.finished,
                                scroll=self.view.verticalScrollBar().value()/max(1, self.view.verticalScrollBar().maximum())))

    def find_next(self):
        count = self.search_model.rowCount()
        if not count:
            self.note.setText('Nenhum texto encontrado. Páginas em imagem não possuem busca sem OCR.')
            return
        self.search_index = (self.search_index + 1) % count
        link = self.search_model.resultAtIndex(self.search_index)
        self.view.setCurrentSearchResultIndex(self.search_index)
        self.view.pageNavigator().jump(link.page(), link.location())

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def leave_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()

    def closeEvent(self, event):
        self.flush()
        self.end_timer.stop()
        self.view.setDocument(None)
        self.doc.close()
        self.closed.emit()
        event.accept()
