"""Drive jobs stay off the GUI thread and never overlap or touch reader state."""
import threading
import time
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtWidgets import QFileDialog
from app.infrastructure.drive_auth import DriveVault, DriveError, DriveCancelled, authorize
from app.infrastructure.google_drive import GoogleDrive, folder_id, FOLDER
from app.infrastructure.filesystem import atomic_json
from app.services.drive_sync import DriveSync
from app.ui.drive import DrivePanel, DriveFolders
from app.ui.workers import Job


class DriveController(QObject):
    progress = Signal(object)

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.panel = DrivePanel(owner.settings)
        self.vault = DriveVault(owner.data_root)
        self.cancel = threading.Event()
        self.busy = False
        self.retry_at = 0
        self.dialog = None
        self.client_factory = lambda: GoogleDrive(self.vault, self.cancel)
        self.progress.connect(self.panel.set_progress)
        self.panel.action.connect(self.action)
        self.panel.optionsChanged.connect(self.save_options)
        self.auto_timer = QTimer(self)
        self.auto_timer.setInterval(60000)
        self.auto_timer.timeout.connect(self.auto_sync)
        self.auto_timer.start()
        self.reload_account()

    def reload_account(self):
        try:
            data = self.vault.load()
            self.panel.connected = bool(data.get('token', {}).get('refresh_token'))
            email = data.get('user', {}).get('emailAddress', '')
            self.panel.account.setText(('Conectado' + (f' · {email}' if email else '')) if self.panel.connected
                                       else ('Credencial importada. Conecte sua conta.' if data.get('client') else 'Conta não conectada'))
        except DriveError as exc:
            self.panel.connected = False
            self.panel.account.setText(str(exc))
        self.panel.update_buttons()

    def run(self, function, done=None):
        if self.busy:
            return
        self.busy = True
        self.cancel.clear()
        self.panel.set_busy(True)
        self.panel.summary.setText('Preparando a operação no Google Drive…')
        def work():
            try:
                return True, function()
            except DriveCancelled:
                return False, None
        job = Job(work, self.owner)
        self.owner.jobs.append(job)
        def result(outcome):
            success, value = outcome
            if success and done:
                done(value)
            elif not success:
                self.panel.invalidate()
                self.panel.summary.setText('Operação cancelada. Arquivos existentes foram preservados.')
        job.result.connect(result)
        def error(message):
            self.panel.invalidate()
            self.panel.summary.setText(message)
            self.retry_at = time.monotonic() + 300
        job.error.connect(error)
        def finished():
            self.busy = False
            self.panel.set_busy(False)
            self.owner.jobs.remove(job)
        job.finished.connect(finished)
        job.finished.connect(job.deleteLater)
        job.start()

    def save_options(self):
        settings = self.owner.settings
        settings.drive_manga_id = self.panel.works.currentData() or ''
        settings.drive_grouped = self.panel.grouped.isChecked()
        settings.drive_auto = self.panel.automatic.isChecked()
        try:
            settings.save(self.owner.data_root / 'settings.json')
        except (OSError, ValueError) as exc:
            self.panel.summary.setText(str(exc))

    def select_folder(self, folder):
        settings = self.owner.settings
        settings.drive_folder_id = folder['id']
        settings.drive_folder_name = folder['name']
        self.panel.folder.setText('https://drive.google.com/drive/folders/' + folder['id'])
        self.panel.folder_name.setText(folder['name'])
        self.panel.invalidate()
        self.save_options()
        self.panel.summary.setText('Pasta selecionada. Confira os capítulos antes de enviar.')

    def action(self, action):
        if action == 'cancel':
            self.cancel.set()
            self.panel.summary.setText('Cancelando a operação. Os arquivos já concluídos ficam preservados…')
            return
        if self.busy:
            return
        if action == 'configure':
            self.auto_timer.stop()
            path, _ = QFileDialog.getOpenFileName(self.owner, 'Credencial OAuth Desktop do Google', '', 'JSON (*.json)')
            self.auto_timer.start()
            if path:
                self.run(lambda: self.vault.import_client(path), lambda _: self.reload_account())
        elif action == 'connect':
            def connect():
                previous_email = self.vault.load().get('user', {}).get('emailAddress')
                authorize(self.vault, self.cancel)
                user = self.client_factory().account()
                data = self.vault.load()
                data['user'] = user
                self.vault.save(data)
                return not previous_email or previous_email != user.get('emailAddress')
            def connected(changed_account):
                if changed_account:
                    self.owner.settings.drive_folder_id = ''
                    self.owner.settings.drive_folder_name = ''
                    self.panel.folder.clear()
                    self.panel.folder_name.setText('Nenhuma pasta selecionada')
                    self.panel.automatic.setChecked(False)
                    self.panel.invalidate()
                    self.save_options()
                self.retry_at = 0
                self.reload_account()
                self.panel.summary.setText('Conta conectada. Escolha uma pasta do Drive.')
            self.run(connect, connected)
        elif action == 'disconnect':
            self.vault.disconnect()
            self.panel.automatic.setChecked(False)
            self.panel.invalidate()
            self.reload_account()
            self.panel.summary.setText('Conta desconectada deste aplicativo. Os arquivos do Drive foram preservados.')
        elif action == 'folder':
            value = self.panel.folder.text()
            self.run(lambda: self.client_factory().get_folder(folder_id(value)), self.select_folder)
        elif action == 'browse':
            self.dialog = DriveFolders(self.owner)
            self.dialog.loadRequested.connect(self.load_folder)
            self.dialog.selected.connect(lambda folder: self.run(lambda: self.client_factory().get_folder(folder['id']), self.select_folder))
            self.dialog.show()
            self.load_folder('root')
        elif action == 'check':
            self.check()
        elif action == 'send' and self.panel.plan:
            self.send(self.panel.plan)

    def load_folder(self, ident):
        if self.dialog:
            self.dialog.list.setEnabled(False)
            self.dialog.choose.setEnabled(False)
            self.dialog.back.setEnabled(False)
        def load():
            client = self.client_factory()
            folder = client.get_folder(ident)
            return folder, [f for f in client.list_children(folder['id']) if f.get('mimeType') == FOLDER]
        def show(result):
            if self.dialog and self.dialog.isVisible():
                self.dialog.display(*result)
        self.run(load, show)

    def config(self):
        return (folder_id(self.panel.folder.text()), self.panel.works.currentData() or '', self.panel.grouped.isChecked())

    def emit_progress(self, value):
        current = time.monotonic()
        if current - getattr(self, 'last_progress', 0) >= .12 or (isinstance(value, dict) and value['done'] in (0, value['total'])):
            self.last_progress = current
            self.progress.emit(value)

    def check(self):
        try:
            config = self.config()
        except DriveError as exc:
            self.panel.summary.setText(str(exc))
            return
        self.save_options()
        def work():
            return DriveSync(self.owner.db, self.client_factory()).plan(*config, progress=self.emit_progress)
        def done(plan):
            self.select_folder(plan['root'])
            self.panel.set_plan(plan)
        self.run(work, done)

    def send(self, plan, automatic=False):
        config = (plan['root']['id'], plan['mid'], plan['grouped'])
        def work():
            service = DriveSync(self.owner.db, self.client_factory())
            result = service.send(plan, self.emit_progress)
            atomic_json(self.owner.data_root / 'logs' / 'drive' / 'last_sync.json', result)
            fresh = None
            if not result['cancelled']:
                try:
                    fresh = service.plan(*config, progress=self.emit_progress)
                except DriveError:
                    pass
            return result, fresh
        self.run(work, self.finished_send)

    def finished_send(self, outcome):
        result, fresh = outcome
        if fresh:
            self.panel.set_plan(fresh)
        else:
            self.panel.invalidate()
        prefix = 'Operação cancelada. ' if result['cancelled'] else ''
        self.panel.summary.setText(prefix + f"{result['uploaded']} PDFs enviados · {result['skipped']} já estavam no Drive · "
                                   f"{result['conflicts']} diferentes preservados · {len(result['failed'])} falhas. " +
                                   ('Confira novamente para ver os pendentes.' if fresh is None else f"Ainda faltam {fresh['missing']} PDFs."))

    def auto_sync(self):
        settings = self.owner.settings
        if self.busy or not settings.drive_auto or not settings.drive_folder_id or not self.panel.connected or time.monotonic() < self.retry_at:
            return
        try:
            if folder_id(self.panel.folder.text()) != settings.drive_folder_id:
                return
        except DriveError:
            return
        config = (settings.drive_folder_id, settings.drive_manga_id, settings.drive_grouped)
        def work():
            service = DriveSync(self.owner.db, self.client_factory())
            plan = service.plan(*config, progress=self.emit_progress)
            result = service.send(plan, self.emit_progress)
            atomic_json(self.owner.data_root / 'logs' / 'drive' / 'last_sync.json', result)
            fresh = None
            if not result['cancelled']:
                try:
                    fresh = service.plan(*config, progress=self.emit_progress)
                except DriveError:
                    pass
            return result, fresh
        self.run(work, self.finished_send)

    def stop(self):
        self.auto_timer.stop()
        self.cancel.set()
