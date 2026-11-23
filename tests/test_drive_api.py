import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit, parse_qs
from urllib.request import urlopen
from urllib.error import HTTPError, URLError
import pytest
from app.infrastructure.drive_auth import DriveVault, DriveError, DriveCancelled, authorize, AUTH_URL
from app.infrastructure.google_drive import GoogleDrive, UPLOAD, CHUNK, folder_id


class MemoryVault:
    def __init__(self):
        self.data = dict(client=dict(client_id='example.apps.googleusercontent.com', client_secret='test-secret'),
                         token=dict(access_token='test-access', refresh_token='test-refresh', expires_at=time.time()+3600))
    def load(self): return copy.deepcopy(self.data)
    def save(self, data): self.data = copy.deepcopy(data)
    def disconnect(self): self.data = {'client': self.data['client']}


class Response:
    def __init__(self, content=b'{}', status=200, headers=None):
        self.status, self.headers, self.content = status, headers or {}, content
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, limit): return self.content[:limit]


def test_oauth_pkce_state_and_loopback_flow_without_real_google_login():
    vault, cancel = MemoryVault(), threading.Event()
    requests, seen = [], {}
    threads = []
    def browser(url):
        assert url.startswith(AUTH_URL + '?')
        values = parse_qs(urlsplit(url).query)
        seen.update(values)
        def callback():
            try:
                urlopen(values['redirect_uri'][0] + '?code=invalid&state=wrong-state', timeout=3)
            except HTTPError as error:
                assert error.code == 400
            with urlopen(values['redirect_uri'][0] + '?code=test-code&state=' + values['state'][0], timeout=3) as response:
                assert response.status == 200
        thread = threading.Thread(target=callback)
        threads.append(thread)
        thread.start()
        return True
    def exchange(values):
        requests.append(values)
        return dict(access_token='new-access', refresh_token='new-refresh', expires_in=3600)
    authorize(vault, cancel, browser=browser, exchange=exchange, timeout=3)
    for thread in threads: thread.join(3)
    assert len(requests) == 1 and requests[0]['code'] == 'test-code'
    challenge = base64.urlsafe_b64encode(hashlib.sha256(requests[0]['code_verifier'].encode()).digest()).decode().rstrip('=')
    assert seen['code_challenge'] == [challenge]
    assert urlsplit(requests[0]['redirect_uri']).hostname == '127.0.0.1'
    assert vault.load()['token']['refresh_token'] == 'new-refresh'


def test_oauth_cancel_preserves_existing_credentials():
    vault, cancel = MemoryVault(), threading.Event()
    original = vault.load()
    def browser(url):
        cancel.set()
        return True
    with pytest.raises(DriveCancelled):
        authorize(vault, cancel, browser=browser)
    assert vault.load() == original


@pytest.mark.skipif(os.name != 'nt', reason='Windows DPAPI')
def test_vault_encrypts_tokens_and_client_secret_and_disconnects(tmp_path):
    vault = DriveVault(tmp_path)
    expected = MemoryVault().load()
    vault.save(expected)
    raw = vault.path.read_bytes()
    assert b'test-refresh' not in raw and b'test-secret' not in raw
    assert DriveVault(tmp_path).load() == expected
    vault.disconnect()
    assert vault.load() == {'client': expected['client']}


def test_import_rejects_web_credentials(tmp_path):
    file = tmp_path / 'credentials.json'
    file.write_text(json.dumps({'web': MemoryVault().load()['client']}))
    with pytest.raises(DriveError, match='Desktop'):
        DriveVault(tmp_path).import_client(file)


@pytest.mark.parametrize('value', ['https://evil.example/folders/abcdef', '../folder', 'root:secret', 'https://drive.google.com/file/d/abcdef/view'])
def test_folder_ids_reject_other_urls_and_paths(value):
    with pytest.raises(DriveError): folder_id(value)


def test_folder_url_and_id_parse():
    assert folder_id('https://drive.google.com/drive/folders/abcdef_12-?usp=sharing') == 'abcdef_12-'
    assert folder_id('abcdef_12-') == 'abcdef_12-'


def test_resumable_upload_recovers_server_acknowledged_bytes_after_lost_response(tmp_path):
    file = tmp_path / 'chapter.pdf'
    data = b'%PDF-' + b'x' * (CHUNK + 123456)
    file.write_bytes(data)
    stat = file.stat()
    source = dict(path=str(file), size=len(data), mtime_ns=stat.st_mtime_ns,
                  md5=hashlib.md5(data).hexdigest(), cid='chapter000001', mid='manga000001')
    class Opener:
        offset = 0
        ranges = []
        lost = False
        def open(self, request, timeout):
            if request.get_method() == 'POST':
                return Response(status=200, headers={'Location': UPLOAD+'?upload_id=fixture'})
            content_range = request.get_header('Content-range')
            self.ranges.append(content_range)
            if content_range.startswith('bytes */'):
                return Response(status=308, headers={'Range':f'bytes=0-{self.offset-1}'})
            block = request.data if isinstance(request.data, bytes) else b''.join(request.data)
            self.offset += len(block)
            if not self.lost:
                self.lost = True
                raise URLError('Resposta perdida')
            return Response(json.dumps(dict(id='remote1', size=str(len(data)), md5Checksum=source['md5'])).encode())
    opener = Opener()
    progress = []
    client = GoogleDrive(MemoryVault(), threading.Event(), opener=opener)
    result = client.upload('rootfolder', source, lambda done, total: progress.append(done))
    assert result['id'] == 'remote1'
    assert opener.offset == len(data)
    assert opener.ranges[1] == f'bytes */{len(data)}'
    assert opener.ranges[2].startswith(f'bytes {CHUNK}-')
    assert progress[-1] == len(data)


def test_upload_rejects_changed_source_before_creating_remote(tmp_path):
    file = tmp_path / 'chapter.pdf'
    file.write_bytes(b'%PDF-test')
    client = GoogleDrive(MemoryVault(), threading.Event())
    with pytest.raises(DriveError, match='mudou'):
        client.upload('rootfolder', dict(path=str(file), size=1, mtime_ns=0), lambda *args: None)


def test_api_paginates_and_rejects_incomplete_listings():
    class Opener:
        calls = []
        def open(self, request, timeout):
            query = parse_qs(urlsplit(request.full_url).query)
            self.calls.append(query)
            return Response(json.dumps(dict(files=[{'id':'second'}]) if query.get('pageToken') else
                                       dict(files=[{'id':'first'}], nextPageToken='next')).encode())
    opener = Opener()
    client = GoogleDrive(MemoryVault(), threading.Event(), opener=opener)
    assert [f['id'] for f in client.list_children('rootfolder')] == ['first','second']
    assert opener.calls[1]['pageToken'] == ['next']


def test_api_refreshes_expired_authorization_without_logging_tokens(monkeypatch):
    import app.infrastructure.google_drive as module
    vault = MemoryVault()
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request.get_header('Authorization'))
            if len(calls) == 1:
                raise HTTPError(request.full_url, 401, 'Unauthorized', {}, None)
            return Response(b'{"user":{"displayName":"Teste"}}')
    monkeypatch.setattr(module, 'token_request', lambda values: dict(access_token='fresh', expires_in=3600))
    client = GoogleDrive(vault, threading.Event(), opener=Opener())
    assert client.account()['displayName'] == 'Teste'
    assert calls == ['Bearer test-access', 'Bearer fresh']


def test_api_will_not_send_bearer_token_to_other_hosts():
    client = GoogleDrive(MemoryVault(), threading.Event())
    with pytest.raises(DriveError, match='inválido'):
        client.call('GET', 'https://example.org/drive')
    with pytest.raises(DriveError, match='inválido'):
        client.call('DELETE', 'https://www.googleapis.com/drive/v3/files/abcdef')


def test_cancelled_upload_resumes_same_session_after_app_restart(tmp_path):
    file = tmp_path / 'chapter.pdf'
    data = b'%PDF-' + b'y' * (CHUNK + 1000)
    file.write_bytes(data)
    stat = file.stat()
    source = dict(path=str(file), size=len(data), mtime_ns=stat.st_mtime_ns,
                  md5=hashlib.md5(data).hexdigest(), cid='chapter000001', mid='manga000001')
    class Opener:
        offset = 0
        creates = 0
        def open(self, request, timeout):
            if request.get_method() == 'POST':
                self.creates += 1
                return Response(headers={'Location': UPLOAD+'?upload_id=same-session'})
            content_range = request.get_header('Content-range')
            if content_range.startswith('bytes */'):
                return Response(status=308, headers={'Range':f'bytes=0-{self.offset-1}'})
            body = request.data if isinstance(request.data, bytes) else b''.join(request.data)
            self.offset += len(body)
            if self.offset < len(data):
                return Response(status=308, headers={'Range':f'bytes=0-{self.offset-1}'})
            return Response(json.dumps(dict(id='remote1', size=str(len(data)), md5Checksum=source['md5'])).encode())
    vault, cancel, opener = MemoryVault(), threading.Event(), Opener()
    first = GoogleDrive(vault, cancel, opener=opener)
    with pytest.raises(DriveCancelled):
        first.upload('rootfolder', source, lambda done, total: cancel.set() if done < total else None)
    assert first.pending_upload('rootfolder', source)
    second = GoogleDrive(vault, threading.Event(), opener=opener)
    assert second.upload('rootfolder', source)['id'] == 'remote1'
    assert opener.creates == 1 and opener.offset == len(data)
    assert not second.pending_upload('rootfolder', source)
