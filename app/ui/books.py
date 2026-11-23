"""Cover library and complete chapter list with bulk reading actions."""
from pathlib import Path
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QIcon
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QAbstractItemView, QLineEdit, QPushButton, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QStackedWidget)


def cover_icon(manga):
    pixmap = QPixmap(150, 214)
    pixmap.fill(QColor('#252a3a'))
    painter = QPainter(pixmap)
    path = Path(manga['cover_file']) if manga['cover_file'] else None
    if path and path.is_file():
        cover = QPixmap(str(path)).scaled(150, 214, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                         Qt.TransformationMode.SmoothTransformation)
        painter.drawPixmap((150-cover.width())//2, (214-cover.height())//2, cover)
    else:
        painter.setPen(QColor('#c1baff'))
        font = painter.font()
        font.setPixelSize(48)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, manga['title'][:1].upper())
    if manga['chapters'] and (manga['read_count'] or 0) >= manga['chapters']:
        painter.setBrush(QColor('#20aa75'))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(122, 186, 23, 23)
        painter.setPen(QPen(QColor('white'), 2.5))
        painter.drawLine(128, 197, 132, 201)
        painter.drawLine(132, 201, 140, 192)
    painter.end()
    return QIcon(pixmap)


class Books(QWidget):
    openWork = Signal(str)
    openChapter = Signal(str)
    resumeWork = Signal(str)
    markChapters = Signal(object, bool)
    renameWork = Signal(str, str)
    downloadChapters = Signal(object)
    refreshCovers = Signal()
    chooseCover = Signal(str)
    importFolder = Signal()

    def __init__(self):
        super().__init__()
        self.mangas, self.chapter_rows = [], []
        self.mid = None
        self.signature = None
        layout = QVBoxLayout(self)
        heading = QLabel('Sua biblioteca')
        heading.setObjectName('heading')
        layout.addWidget(heading)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Buscar na biblioteca…')
        self.search.textChanged.connect(self.filter_books)
        top.addWidget(self.search)
        covers = QPushButton('Atualizar capas')
        covers.clicked.connect(self.refreshCovers.emit)
        top.addWidget(covers)
        import_button = QPushButton('Importar PDFs')
        import_button.clicked.connect(self.importFolder.emit)
        top.addWidget(import_button)
        layout.addLayout(top)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.grid = QListWidget()
        self.grid.setObjectName('coverGrid')
        self.grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.grid.setMovement(QListWidget.Movement.Static)
        self.grid.setIconSize(QSize(150, 214))
        self.grid.setGridSize(QSize(185, 320))
        self.grid.setWordWrap(True)
        self.grid.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.grid.itemClicked.connect(lambda item: self.openWork.emit(item.data(Qt.ItemDataRole.UserRole)))
        self.stack.addWidget(self.grid)
        detail = QWidget()
        body = QVBoxLayout(detail)
        header = QHBoxLayout()
        back = QPushButton('Voltar à biblioteca')
        back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        header.addWidget(back)
        self.name = QLineEdit()
        header.addWidget(self.name, 1)
        rename = QPushButton('Renomear')
        rename.clicked.connect(lambda: self.renameWork.emit(self.mid, self.name.text()))
        header.addWidget(rename)
        cover_button = QPushButton('Trocar capa')
        cover_button.clicked.connect(lambda: self.chooseCover.emit(self.mid))
        header.addWidget(cover_button)
        body.addLayout(header)
        self.summary = QLabel()
        body.addWidget(self.summary)
        self.chapter_search = QLineEdit()
        self.chapter_search.setPlaceholderText('Buscar capítulo…')
        self.chapter_search.textChanged.connect(self.filter_chapters)
        body.addWidget(self.chapter_search)
        controls = QHBoxLayout()
        for text, function in [('Continuar lendo', lambda: self.resumeWork.emit(self.mid)),
                               ('Ler selecionado', self.read_selected),
                               ('Marcar como lidos', lambda: self.markChapters.emit(self.selected(), True)),
                               ('Marcar não lidos', lambda: self.markChapters.emit(self.selected(), False)),
                               ('Baixar selecionados', lambda: self.downloadChapters.emit(self.selected()))]:
            button = QPushButton(text)
            button.clicked.connect(function)
            controls.addWidget(button)
        body.addLayout(controls)
        self.chapters = QTableWidget(0, 4)
        self.chapters.setHorizontalHeaderLabels(['Capítulo', 'Leitura', 'Posição', 'PDF'])
        self.chapters.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.chapters.verticalHeader().hide()
        self.chapters.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.chapters.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.chapters.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.chapters.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.chapters.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.chapters.itemDoubleClicked.connect(lambda item: self.openChapter.emit(self.chapter_rows[item.row()]['id']))
        body.addWidget(self.chapters, 1)
        hint = QLabel('Ctrl ou Shift para selecionar vários capítulos · Ctrl+A para selecionar todos os visíveis')
        body.addWidget(hint)
        self.stack.addWidget(detail)

    def update_mangas(self, mangas):
        signature = [(m['id'], m['title'], m['cover_file'], m['updated'], m['chapters'], m['read_count']) for m in mangas]
        self.mangas = mangas
        if signature == self.signature:
            return
        self.signature = signature
        self.grid.clear()
        for manga in mangas:
            read = manga['read_count'] or 0
            title = manga['title'] if len(manga['title']) <= 54 else manga['title'][:51] + '...'
            item = QListWidgetItem(cover_icon(manga), f"{title}\n{read}/{manga['chapters']} lidos")
            item.setToolTip(manga['title'])
            item.setData(Qt.ItemDataRole.UserRole, manga['id'])
            self.grid.addItem(item)
        self.filter_books()

    def filter_books(self):
        text = self.search.text().casefold().strip()
        for row in range(self.grid.count()):
            self.grid.item(row).setHidden(text not in self.grid.item(row).text().casefold())

    def show_work(self, mid, chapters):
        selected = set(self.selected()) if self.mid == mid else set()
        self.mid = mid
        self.chapter_rows = chapters
        manga = next((m for m in self.mangas if m['id'] == mid), None)
        if manga:
            self.name.setText(manga['title'])
        self.summary.setText(f"{len(chapters)} capítulos · {sum(c['is_read'] for c in chapters)} lidos · "
                             f"{sum(c['available'] for c in chapters)} PDFs disponíveis")
        self.chapters.setUpdatesEnabled(False)
        self.chapters.setRowCount(len(chapters))
        for i, chapter in enumerate(chapters):
            position = f"Página {chapter['read_page']+1}/{chapter['read_total']}" if chapter['read_total'] else ('Concluído' if chapter['is_read'] else 'Não iniciado')
            for j, text in enumerate((chapter['title'], 'Lido' if chapter['is_read'] else 'Não lido', position,
                                      'Disponível' if chapter['available'] else 'Não baixado')):
                item = QTableWidgetItem(text)
                if chapter['is_read']:
                    item.setForeground(QColor('#36bd88'))
                self.chapters.setItem(i, j, item)
                if chapter['id'] in selected:
                    item.setSelected(True)
        self.chapters.setUpdatesEnabled(True)
        self.filter_chapters()
        self.stack.setCurrentIndex(1)

    def filter_chapters(self):
        text = self.chapter_search.text().casefold().strip()
        for row, chapter in enumerate(self.chapter_rows):
            self.chapters.setRowHidden(row, text not in chapter['title'].casefold())

    def selected(self):
        return [self.chapter_rows[i.row()]['id'] for i in self.chapters.selectionModel().selectedRows()
                if i.row() < len(self.chapter_rows) and not self.chapters.isRowHidden(i.row())]

    def read_selected(self):
        ids = self.selected()
        if ids:
            self.openChapter.emit(ids[0])
