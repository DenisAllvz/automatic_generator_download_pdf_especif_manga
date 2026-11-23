"""Exercise the shipped EXE offline with 1,000 tasks and one real local chapter."""
import ctypes
from ctypes import wintypes
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from app.core.config import Settings
from app.infrastructure.database import Database
from app.infrastructure.catalog import read_manifest, save_manifest
from app.models import Manga, Chapter
from app.services.library import Library
from profile_memory import Counters

source = Path(sys.argv[1]).resolve()
manifest = read_manifest(source)
assert manifest and len(manifest['pages']) == manifest['expected']
exe = root / 'dist' / 'MangaManager-2.3.0' / 'MangaManager.exe'
peak, private = 0, 0
with TemporaryDirectory(prefix='manga-frozen-ram-') as temporary:
    data = Path(temporary)
    settings = Settings(library=str(data / 'library'))
    settings.save(data / 'settings.json')
    db = Database(data / 'library.sqlite3')
    library = Library(db, Path(settings.library))
    mid, ids = library.add(Manga('RAM offline', 'https://example.org/offline', chapters=[
        Chapter(f'Capítulo {i}', f'https://example.org/offline/{i}') for i in range(1000)]))
    library.enqueue(ids)
    db.execute("UPDATE tasks SET status='paused'")
    first = db.chapters(mid)[0]
    folder = Path(first['folder'])
    folder.mkdir(parents=True)
    for page in manifest['pages']:
        shutil.copy2(source / page['file'], folder / page['file'])
    save_manifest(folder, dict(manifest, chapter_url=first['url']))
    db.execute("UPDATE chapters SET status='downloaded' WHERE id=?", (first['id'],))
    db.execute("UPDATE tasks SET status='queued' WHERE chapter_id=?", (first['id'],))
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    process = subprocess.Popen([str(exe), '--data-dir', str(data)], startupinfo=startup)
    get_info = ctypes.windll.psapi.GetProcessMemoryInfo
    get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    done_at = None
    deadline = time.monotonic() + 60
    try:
        while process.poll() is None and time.monotonic() < deadline:
            counters = Counters()
            counters.cb = ctypes.sizeof(counters)
            if get_info(wintypes.HANDLE(int(process._handle)), ctypes.byref(counters), counters.cb):
                peak = max(peak, counters.WorkingSetSize)
                private = max(private, counters.PrivateUsage)
            with closing(sqlite3.connect(data / 'library.sqlite3')) as connection:
                state = connection.execute('SELECT status FROM tasks WHERE chapter_id=?', (first['id'],)).fetchone()[0]
            if state == 'complete':
                done_at = done_at or time.monotonic()
                if time.monotonic() - done_at > 2:
                    break
            time.sleep(.05)
        assert state == 'complete', f'Conversão offline não terminou: {state}'
    finally:
        # Close only the isolated process created above, allowing its normal shutdown.
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        windows = []
        forced = False
        ctypes.windll.user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        ctypes.windll.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        ctypes.windll.user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        def close_window(hwnd, lparam):
            pid = wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == process.pid:
                title = ctypes.create_unicode_buffer(512)
                ctypes.windll.user32.GetWindowTextW(hwnd, title, 512)
                windows.append(title.value)
                if title.value.startswith('Manga Manager ·'):
                    ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)
            return True
        callback = callback_type(close_window)
        for _ in range(4):
            if process.poll() is not None:
                break
            ctypes.windll.user32.EnumWindows(callback, 0)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        if process.poll() is None:
            forced = True
            process.terminate()
            process.wait(timeout=5)
    report = dict(version='2.3.0', frozen=True, tasks=1000, pages=manifest['expected'],
                  status=state, peak_mb=round(peak/1024**2, 2), private_peak_mb=round(private/1024**2, 2),
                  exit_code=process.returncode, forced_close=forced, windows=list(dict.fromkeys(windows)))
    assert peak < 512 * 1024**2, report
(root / 'tmp' / 'memory-frozen.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
