"""Drive API v3, append-only operations and resumable uploads."""
import json
from pathlib import Path
import re
import time
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import Request, build_opener
from urllib.error import HTTPError, URLError
from app.infrastructure.drive_auth import DriveError, DriveCancelled, NoRedirect, token_request

API = 'https://www.googleapis.com/drive/v3'
UPLOAD = 'https://www.googleapis.com/upload/drive/v3/files'
FOLDER = 'application/vnd.google-apps.folder'
FIELDS = 'id,name,mimeType,size,md5Checksum,parents,appProperties,trashed,capabilities(canAddChildren)'
CHUNK = 4 * 1024**2


def folder_id(value):
    value = value.strip()
    if value.startswith('https://'):
        parsed = urlsplit(value)
        if parsed.hostname != 'drive.google.com':
            raise DriveError('Cole um link de pasta do Google Drive.')
        match = re.search(r'/folders/([A-Za-z0-9_-]+)', parsed.path)
        value = match.group(1) if match else parse_qs(parsed.query).get('id', [''])[0]
    if value != 'root' and not re.fullmatch(r'[A-Za-z0-9_-]{5,200}', value):
        raise DriveError('Cole o link ou ID de uma pasta do Google Drive.')
    return value


class GoogleDrive:
    def __init__(self, vault, cancel, opener=None):
        self.vault, self.cancel = vault, cancel
        self.opener = opener or build_opener(NoRedirect)

    def check_cancel(self):
        if self.cancel.is_set():
            raise DriveCancelled('Sincronização cancelada. Os PDFs já enviados foram preservados.')

    def access_token(self, force=False):
        data = self.vault.load()
        token = data.get('token', {})
        if not token.get('refresh_token'):
            raise DriveError('Conecte sua conta do Google Drive primeiro.')
        if force or token.get('expires_at', 0) < time.time() + 60:
            client = data['client']
            refreshed = token_request(dict(client_id=client['client_id'], client_secret=client['client_secret'],
                                           refresh_token=token['refresh_token'], grant_type='refresh_token'))
            token.update(refreshed)
            token['expires_at'] = time.time() + int(refreshed.get('expires_in', 3600))
            data['token'] = token
            self.vault.save(data)
        return token['access_token']

    def call(self, method, url, data=None, headers=None, attempts=4):
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname != 'www.googleapis.com' or method not in ('GET', 'POST', 'PUT'):
            raise DriveError('Endereço de API do Drive inválido.')
        for attempt in range(attempts):
            self.check_cancel()
            auth = dict(headers or {}, Authorization='Bearer ' + self.access_token())
            payload = data
            if method == 'PUT' and data:
                auth['Content-Length'] = str(len(data))
                def blocks():
                    for position in range(0, len(data), 65536):
                        self.check_cancel()
                        yield data[position:position+65536]
                payload = blocks()
            request = Request(url, data=payload, headers=auth, method=method)
            try:
                with self.opener.open(request, timeout=25) as response:
                    return response.status, dict(response.headers), response.read(8 * 1024**2)
            except HTTPError as exc:
                if exc.code == 308:
                    return 308, dict(exc.headers), b''
                if exc.code == 401 and attempt == 0:
                    self.access_token(force=True)
                    continue
                try:
                    details = json.loads(exc.read(1024 * 1024)).get('error', {})
                    reasons = {x.get('reason') for x in details.get('errors', [])}
                except (ValueError, AttributeError):
                    reasons = set()
                if (exc.code == 429 or 500 <= exc.code <= 599 or reasons.intersection({'rateLimitExceeded','userRateLimitExceeded'})) and attempt + 1 < attempts:
                    try:
                        wait = min(30, max(2**attempt, float(exc.headers.get('Retry-After', 0))))
                    except ValueError:
                        wait = 2**attempt
                    if self.cancel.wait(wait):
                        self.check_cancel()
                    continue
                if 'storageQuotaExceeded' in reasons:
                    raise DriveError('O Google Drive está sem espaço para este PDF.') from None
                if exc.code in (401, 403):
                    raise DriveError('O Google não permitiu esta operação. Confira a autorização da conta, a API ativada e a permissão da pasta.') from None
                if exc.code == 404:
                    raise DriveError('A pasta ou arquivo do Drive não está mais disponível para esta conta.', status=404) from None
                raise DriveError(f'O Google Drive retornou erro HTTP {exc.code}. Tente novamente.', status=exc.code) from None
            except (URLError, OSError, TimeoutError):
                # Upload callers query session status before retrying uncertain chunks.
                raise DriveError('A conexão com o Google Drive foi interrompida. Tente novamente.') from None
        raise DriveError('Não foi possível concluir a operação no Google Drive.')

    def json_call(self, method, url, body=None):
        data = None if body is None else json.dumps(body).encode()
        _, _, content = self.call(method, url, data, {'Content-Type': 'application/json; charset=UTF-8'})
        try:
            return json.loads(content)
        except ValueError:
            raise DriveError('O Google Drive retornou uma resposta inválida.') from None

    def account(self):
        return self.json_call('GET', API + '/about?' + urlencode({'fields': 'user(displayName,emailAddress)'}))['user']

    def get_folder(self, ident):
        result = self.json_call('GET', API + '/files/' + folder_id(ident) + '?' + urlencode({'fields': FIELDS, 'supportsAllDrives': 'true'}))
        if result.get('mimeType') != FOLDER or result.get('trashed'):
            raise DriveError('O destino precisa ser uma pasta disponível no Google Drive.')
        if result.get('capabilities', {}).get('canAddChildren') is False:
            raise DriveError('Sua conta não tem permissão para enviar arquivos a esta pasta.')
        return result

    def list_children(self, parent):
        parent = folder_id(parent)
        items, page = [], ''
        while True:
            parameters = dict(q=f"'{parent}' in parents and trashed = false", pageSize=1000,
                              fields=f'nextPageToken,incompleteSearch,files({FIELDS})',
                              supportsAllDrives='true', includeItemsFromAllDrives='true')
            if page:
                parameters['pageToken'] = page
            result = self.json_call('GET', API + '/files?' + urlencode(parameters))
            if result.get('incompleteSearch'):
                raise DriveError('O Google não retornou a pasta inteira. Confira o destino e tente novamente antes de enviar.')
            items.extend(result.get('files', []))
            page = result.get('nextPageToken')
            if not page:
                return items

    def create_folder(self, parent, name, mid):
        return self.json_call('POST', API + '/files?' + urlencode({'fields': FIELDS, 'supportsAllDrives': 'true'}),
                              dict(name=name, parents=[folder_id(parent)], mimeType=FOLDER, appProperties={'mmWork': mid}))

    def pending_upload(self, parent, source):
        saved = self.vault.load().get('uploads', {}).get(parent + ':' + source['cid'])
        return saved if saved and saved.get('md5') == source['md5'] and saved.get('size') == source['size'] else None

    def save_session(self, parent, source, session=None):
        data = self.vault.load()
        uploads = data.setdefault('uploads', {})
        key = parent + ':' + source['cid']
        if session:
            uploads[key] = dict(url=session, md5=source['md5'], size=source['size'])
        else:
            uploads.pop(key, None)
        self.vault.save(data)

    def upload(self, parent, source, progress=lambda done, total: None):
        path = Path(source['path'])
        size = source['size']
        stat = path.stat()
        if (stat.st_size, stat.st_mtime_ns) != (size, source['mtime_ns']):
            raise DriveError('O PDF mudou desde a conferência. Confira novamente antes de enviar.')
        def complete(content):
            try:
                result = json.loads(content)
            except ValueError:
                raise DriveError('O Drive não confirmou o arquivo enviado.') from None
            if result.get('id') and ('size' not in result or 'md5Checksum' not in result):
                result = self.json_call('GET', API + '/files/' + result['id'] + '?' + urlencode({'fields': FIELDS, 'supportsAllDrives':'true'}))
            after = path.stat()
            if (after.st_size, after.st_mtime_ns) != (size, source['mtime_ns']):
                raise DriveError('O PDF mudou durante o envio. Confira novamente a sincronização.')
            if int(result.get('size', -1)) != size or result.get('md5Checksum', '').lower() != source['md5']:
                raise DriveError('O Drive não confirmou a integridade do PDF. O arquivo remoto foi preservado para conferência.')
            self.save_session(parent, source)
            progress(size, size)
            return result
        def acknowledged(headers):
            value = next((v for k, v in headers.items() if k.lower() == 'range'), '')
            match = re.fullmatch(r'bytes=0-(\d+)', value)
            return int(match.group(1)) + 1 if match else 0
        session, offset = None, 0
        pending = self.pending_upload(parent, source)
        if pending and pending['url'].startswith(UPLOAD + '?'):
            try:
                status, headers, content = self.call('PUT', pending['url'], b'', {'Content-Range': f'bytes */{size}'})
                if status in (200, 201):
                    return complete(content)
                session, offset = pending['url'], acknowledged(headers)
            except DriveCancelled:
                raise
            except DriveError as exc:
                if exc.status not in (404, 410):
                    raise
        metadata = dict(name=path.name, parents=[folder_id(parent)], mimeType='application/pdf',
                        appProperties={'mmChapter': source['cid'], 'mmWork': source['mid']})
        url = UPLOAD + '?' + urlencode(dict(uploadType='resumable', supportsAllDrives='true', fields=FIELDS))
        if session is None:
            _, headers, _ = self.call('POST', url, json.dumps(metadata).encode(),
                                   {'Content-Type': 'application/json; charset=UTF-8',
                                    'X-Upload-Content-Type': 'application/pdf', 'X-Upload-Content-Length': str(size)})
            session = next((v for k, v in headers.items() if k.lower() == 'location'), '')
        if not session.startswith(UPLOAD + '?'):
            raise DriveError('O Google não retornou uma sessão válida de envio.')
        self.save_session(parent, source, session)
        failures = 0
        with path.open('rb') as stream:
            while offset < size:
                self.check_cancel()
                stream.seek(offset)
                block = stream.read(min(CHUNK, size - offset))
                if not block:
                    raise DriveError('O PDF foi alterado durante o envio.')
                try:
                    status, headers, content = self.call('PUT', session, block,
                        {'Content-Type': 'application/pdf', 'Content-Range': f'bytes {offset}-{offset+len(block)-1}/{size}'}, attempts=1)
                except DriveCancelled:
                    raise
                except DriveError:
                    failures += 1
                    if failures > 3:
                        raise
                    status, headers, content = self.call('PUT', session, b'', {'Content-Range': f'bytes */{size}'})
                if status in (200, 201):
                    return complete(content)
                new_offset = acknowledged(headers)
                if new_offset <= offset:
                    failures += 1
                    if failures > 3:
                        raise DriveError('O Drive não avançou no envio. Tente sincronizar novamente.')
                else:
                    failures = 0
                offset = new_offset
                progress(offset, size)
        raise DriveError('O Google não confirmou a conclusão do envio.')
