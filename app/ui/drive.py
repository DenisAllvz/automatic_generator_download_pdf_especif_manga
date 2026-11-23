"""Google Drive connection, folder selection and a compact missing-chapter preview."""
from collections import defaultdict
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QProgressBar, QDialog, QListWidget, QListWidgetItem)


def grid(headers):
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.verticalHeader().hide()
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
    table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    return table


class DrivePanel(QWidget):
    action = Signal(str)
    optionsChanged = Signal()

    def __init__(self, settings):
        super().__init__()
        self.busy = False
        self.connected = False
        self.plan = None
        layout = QVBoxLayout(self)
        title = QLabel('Seus mangás no Google Drive')
        title.setObjectName('heading')
        layout.addWidget(title)
        caption = QLabel('Confira os capítulos que já estão na sua pasta e envie apenas os PDFs que faltam.')
        caption.setWordWrap(True)
        layout.addWidget(caption)
        self.account = QLabel('Conta não conectada')
        self.account.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.account)
        row = QHBoxLayout()
        self.configure = QPushButton('Importar credencial OAuth')
        self.configure.clicked.connect(lambda: self.action.emit('configure'))
        row.addWidget(self.configure)
        self.connect = QPushButton('Conectar Google Drive')
        self.connect.clicked.connect(lambda: self.action.emit('connect'))
        row.addWidget(self.connect)
        self.disconnect = QPushButton('Desconectar')
        self.disconnect.clicked.connect(lambda: self.action.emit('disconnect'))
        row.addWidget(self.disconnect)
        row.addStretch()
        layout.addLayout(row)
        help_text = QLabel('Primeira conexão: importe o JSON OAuth de um aplicativo Desktop com a API do Drive ativada. '
                           '<a style="color:#a99cff" href="https://developers.google.com/workspace/drive/api/quickstart/python#authorize_credentials_for_a_desktop_application">Como configurar no Google Cloud</a>. '
                           'Sua senha é informada somente no navegador do Google.')
        help_text.setWordWrap(True)
        help_text.setOpenExternalLinks(True)
        layout.addWidget(help_text)
        destination = QHBoxLayout()
        self.folder = QLineEdit('https://drive.google.com/drive/folders/' + settings.drive_folder_id if settings.drive_folder_id else '')
        self.folder.setPlaceholderText('Cole o link da pasta do Google Drive')
        self.folder.textEdited.connect(self.invalidate)
        destination.addWidget(self.folder, 1)
        self.use_folder = QPushButton('Usar pasta')
        self.use_folder.clicked.connect(lambda: self.action.emit('folder'))
        destination.addWidget(self.use_folder)
        self.browse = QPushButton('Buscar no Drive')
        self.browse.clicked.connect(lambda: self.action.emit('browse'))
        destination.addWidget(self.browse)
        layout.addLayout(destination)
        self.folder_name = QLabel(settings.drive_folder_name or 'Nenhuma pasta selecionada')
        self.folder_name.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.folder_name)
        controls = QHBoxLayout()
        self.works = QComboBox()
        self.works.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.works.setMinimumContentsLength(18)
        self.works.addItem('Todas as obras', '')
        self.wanted_mid = settings.drive_manga_id
        self.works.currentIndexChanged.connect(self.changed)
        controls.addWidget(self.works, 1)
        self.grouped = QCheckBox('Uma subpasta por obra')
        self.grouped.setChecked(settings.drive_grouped)
        self.grouped.toggled.connect(self.changed)
        controls.addWidget(self.grouped)
        self.automatic = QCheckBox('Enviar PDFs novos automaticamente')
        self.automatic.setChecked(settings.drive_auto)
        self.automatic.toggled.connect(lambda checked: self.optionsChanged.emit())
        controls.addWidget(self.automatic)
        layout.addLayout(controls)
        self.summary = QLabel('Conecte sua conta, selecione a pasta e clique em Conferir capítulos.')
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.hide()
        layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        self.check = QPushButton('Conferir capítulos')
        self.check.clicked.connect(lambda: self.action.emit('check'))
        buttons.addWidget(self.check)
        self.send = QPushButton('Enviar faltantes')
        self.send.setObjectName('primary')
        self.send.clicked.connect(lambda: self.action.emit('send'))
        buttons.addWidget(self.send)
        self.cancel = QPushButton('Cancelar')
        self.cancel.clicked.connect(lambda: self.action.emit('cancel'))
        buttons.addWidget(self.cancel)
        buttons.addStretch()
        self.open_folder = QPushButton('Abrir pasta no Drive')
        self.open_folder.clicked.connect(self.open_remote)
        buttons.addWidget(self.open_folder)
        layout.addLayout(buttons)
        self.table = grid(['Obra', 'PDFs locais', 'Já no Drive', 'Faltam', 'Diferentes'])
        layout.addWidget(self.table, 1)
        self.details_toggle = QPushButton('Ver capítulos pendentes')
        self.details_toggle.setCheckable(True)
        self.details_toggle.toggled.connect(self.show_details)
        layout.addWidget(self.details_toggle, alignment=Qt.AlignmentFlag.AlignLeft)
        self.details = grid(['Obra', 'Capítulo', 'Situação'])
        self.details.setMaximumHeight(190)
        self.details.hide()
        layout.addWidget(self.details)
        note = QLabel('Envio do PC para o Drive. Arquivos remotos diferentes são preservados; nada é apagado do Drive. '
                      'O progresso de leitura no tablet não é sincronizado nesta etapa.')
        note.setWordWrap(True)
        note.setObjectName('caption')
        layout.addWidget(note)
        self.update_buttons()

    def set_mangas(self, mangas):
        signature = [(m['id'], m['title']) for m in mangas]
        if getattr(self, 'mangas', None) == signature:
            return
        self.mangas = signature
        selected = self.works.currentData() or self.wanted_mid
        self.works.blockSignals(True)
        self.works.clear()
        self.works.addItem('Todas as obras', '')
        for mid, title in signature:
            self.works.addItem(title, mid)
        self.works.setCurrentIndex(max(0, self.works.findData(selected)))
        self.works.blockSignals(False)

    def changed(self, *args):
        self.wanted_mid = self.works.currentData() or ''
        self.invalidate()
        self.optionsChanged.emit()

    def invalidate(self, *args):
        self.plan = None
        self.table.setRowCount(0)
        self.details.setRowCount(0)
        self.update_buttons()

    def update_buttons(self):
        for widget in (self.configure, self.connect, self.folder, self.works, self.grouped, self.automatic):
            widget.setEnabled(not self.busy)
        self.disconnect.setEnabled(self.connected and not self.busy)
        for widget in (self.check, self.use_folder, self.browse):
            widget.setEnabled(self.connected and not self.busy)
        self.send.setEnabled(self.connected and not self.busy and bool(self.plan and self.plan['missing']))
        self.cancel.setEnabled(self.busy)
        self.open_folder.setEnabled(bool(self.folder.text()))

    def set_busy(self, busy):
        self.busy = busy
        self.progress.setVisible(busy)
        self.progress.setRange(0, 0 if busy else 100)
        self.update_buttons()

    def set_progress(self, info):
        if isinstance(info, str):
            self.summary.setText(info)
        else:
            self.summary.setText(f"Enviando {info['work']} · {info['chapter']}")
            self.progress.setRange(0, 100)
            self.progress.setValue(round(100*info['done']/max(1, info['total'])))

    def set_plan(self, plan):
        self.plan = plan
        self.summary.setText(f"{plan['existing']} PDFs já estão no Drive · {plan['missing']} faltam · "
                             f"{plan['conflicts']} arquivos diferentes preservados.")
        totals = defaultdict(lambda: defaultdict(int))
        for row in plan['rows']:
            totals[row['work']]['local'] += 1
            totals[row['work']][row['status']] += 1
        self.table.setRowCount(len(totals))
        for i, (name, count) in enumerate(totals.items()):
            for j, text in enumerate((name, count['local'], count['existing'], count['missing'], count['conflict'])):
                self.table.setItem(i, j, QTableWidgetItem(str(text)))
        self.show_details(self.details_toggle.isChecked())
        self.update_buttons()

    def show_details(self, visible):
        self.details.setVisible(visible)
        if visible and self.plan:
            rows = [r for r in self.plan['rows'] if r['status'] != 'existing']
            self.details.setRowCount(len(rows))
            for i, row in enumerate(rows):
                for j, text in enumerate((row['work'], row['chapter'], 'Falta enviar' if row['status']=='missing' else 'Conteúdo diferente: preservado')):
                    self.details.setItem(i, j, QTableWidgetItem(text))

    def open_remote(self):
        from app.infrastructure.google_drive import folder_id
        try:
            ident = folder_id(self.folder.text())
        except Exception:
            return
        QDesktopServices.openUrl(QUrl('https://drive.google.com/drive/folders/' + ident))


class DriveFolders(QDialog):
    loadRequested = Signal(str)
    selected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Escolher pasta no Google Drive')
        self.resize(600, 500)
        self.history = []
        self.current = None
        layout = QVBoxLayout(self)
        self.label = QLabel('Carregando Meu Drive…')
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.label)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda item: self.loadRequested.emit(item.data(Qt.ItemDataRole.UserRole)['id']))
        layout.addWidget(self.list)
        buttons = QHBoxLayout()
        self.back = QPushButton('Voltar')
        self.back.clicked.connect(self.go_back)
        buttons.addWidget(self.back)
        self.choose = QPushButton('Usar esta pasta')
        self.choose.clicked.connect(self.pick)
        buttons.addWidget(self.choose)
        layout.addLayout(buttons)

    def display(self, folder, children):
        if self.current and self.current['id'] != folder['id']:
            self.history.append(self.current)
        self.current = folder
        self.list.setEnabled(True)
        self.choose.setEnabled(True)
        self.label.setText(folder['name'])
        self.list.clear()
        for child in sorted(children, key=lambda x: x['name'].casefold()):
            item = QListWidgetItem(child['name'])
            item.setData(Qt.ItemDataRole.UserRole, child)
            self.list.addItem(item)
        self.back.setEnabled(bool(self.history))

    def go_back(self):
        if self.history:
            folder = self.history.pop()
            self.current = None
            self.loadRequested.emit(folder['id'])

    def pick(self):
        item = self.list.currentItem()
        chosen = item.data(Qt.ItemDataRole.UserRole) if item else self.current
        if chosen:
            self.selected.emit(chosen)
            self.accept()
