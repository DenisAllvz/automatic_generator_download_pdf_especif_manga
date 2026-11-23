"""Google Desktop OAuth with PKCE; Windows DPAPI keeps credentials out of settings/logs."""
import base64
import ctypes
from ctypes import wintypes
import hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import secrets
import time
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
import webbrowser
from app.infrastructure.filesystem import atomic_bytes

TOKEN_URL = 'https://oauth2.googleapis.com/token'
AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
SCOPE = 'https://www.googleapis.com/auth/drive'


class DriveError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class DriveCancelled(DriveError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def token_request(values):
    request = Request(TOKEN_URL, data=urlencode(values).encode(), method='POST',
                      headers={'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with build_opener(NoRedirect).open(request, timeout=20) as response:
            return json.loads(response.read(1024 * 1024))
    except HTTPError:
        raise DriveError('O Google não autorizou a conexão. Confira a credencial Desktop, a API do Drive e os usuários de teste; depois conecte novamente.') from None
    except (URLError, OSError):
        raise DriveError('Não foi possível conectar ao Google. Confira a internet e tente novamente.') from None
    except ValueError:
        raise DriveError('O Google retornou uma resposta inválida para o login. Tente conectar novamente.') from None


def protect(content, decrypt=False):
    if os.name != 'nt':
        raise DriveError('O armazenamento protegido desta versão requer Windows.')
    class Blob(ctypes.Structure):
        _fields_ = [('length', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(content)
    source = Blob(len(content), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    crypt = ctypes.windll.crypt32
    operation = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    operation.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    operation.restype = wintypes.BOOL
    if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise DriveError('Não foi possível abrir a conexão protegida. Reconecte o Google Drive neste usuário do Windows.')
    try:
        return ctypes.string_at(result.data, result.length)
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(ctypes.cast(result.data, ctypes.c_void_p))


class DriveVault:
    def __init__(self, data_root):
        self.path = Path(data_root) / 'drive' / 'account.bin'

    def load(self):
        if not self.path.exists():
            return {}
        try:
            return json.loads(protect(self.path.read_bytes(), decrypt=True))
        except (OSError, ValueError):
            raise DriveError('A conexão salva não está disponível. Importe a credencial e conecte novamente.') from None

    def save(self, data):
        atomic_bytes(self.path, protect(json.dumps(data).encode()))

    def import_client(self, path):
        try:
            path = Path(path)
            if path.stat().st_size > 1024 * 1024:
                raise ValueError()
            client = json.loads(path.read_text(encoding='utf-8')).get('installed', {})
            if not client.get('client_id', '').endswith('.apps.googleusercontent.com') or not client.get('client_secret'):
                raise ValueError()
        except (OSError, ValueError, AttributeError):
            raise DriveError('Escolha o JSON de uma credencial OAuth do tipo Aplicativo para computador (Desktop), baixado do Google Cloud.') from None
        self.save({'client': {'client_id': client['client_id'], 'client_secret': client['client_secret']}})

    def disconnect(self):
        data = self.load()
        self.save({'client': data['client']} if data.get('client') else {})


def authorize(vault, cancel, browser=webbrowser.open, exchange=token_request, timeout=300):
    data = vault.load()
    client = data.get('client')
    if not client:
        raise DriveError('Primeiro importe a credencial OAuth Desktop do aplicativo.')
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    outcome = {}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            if parsed.path != '/oauth/callback' or not secrets.compare_digest(query.get('state', [''])[0], state):
                self.send_response(400)
                self.end_headers()
                return
            outcome['code'] = query.get('code', [''])[0]
            outcome['error'] = query.get('error', [''])[0]
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write('Autorização recebida. Volte ao Manga Manager.'.encode())
    with HTTPServer(('127.0.0.1', 0), Handler) as server:
        server.timeout = .2
        redirect = f'http://127.0.0.1:{server.server_port}/oauth/callback'
        parameters = dict(client_id=client['client_id'], redirect_uri=redirect, response_type='code',
                          scope=SCOPE, access_type='offline', prompt='consent', state=state,
                          code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='),
                          code_challenge_method='S256')
        if browser(AUTH_URL + '?' + urlencode(parameters)) is False:
            raise DriveError('Não foi possível abrir o navegador. Confira o navegador padrão e tente conectar novamente.')
        deadline = time.monotonic() + timeout
        while not outcome:
            if cancel.is_set():
                raise DriveCancelled('Conexão cancelada.')
            if time.monotonic() >= deadline:
                raise DriveError('O login expirou. Clique em Conectar e conclua a autorização no navegador.')
            server.handle_request()
    if outcome.get('error') or not outcome.get('code'):
        raise DriveError('A autorização não foi concluída no Google.')
    if cancel.is_set():
        raise DriveCancelled('Conexão cancelada.')
    token = exchange(dict(client_id=client['client_id'], client_secret=client['client_secret'],
                          code=outcome['code'], code_verifier=verifier, redirect_uri=redirect,
                          grant_type='authorization_code'))
    if not token.get('access_token') or not token.get('refresh_token'):
        raise DriveError('O Google não retornou uma autorização de uso offline. Revogue a conexão anterior e autorize novamente.')
    token['expires_at'] = time.time() + int(token.get('expires_in', 3600))
    vault.save(dict(client=client, token=token))
