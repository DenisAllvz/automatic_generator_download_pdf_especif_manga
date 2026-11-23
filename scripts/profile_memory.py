"""Windows RAM profile of isolated queue and PDF conversion, sampled every 20 ms."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import threading
import time
from tempfile import TemporaryDirectory

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


class Counters(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
        'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage',
        'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]


def memory():
    data = Counters()
    data.cb = ctypes.sizeof(data)
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not ctypes.windll.psapi.GetProcessMemoryInfo(wintypes.HANDLE(-1), ctypes.byref(data), data.cb):
        raise ctypes.WinError()
    return data.WorkingSetSize, data.PrivateUsage


if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication
    from PIL import Image
    import pikepdf
    from app.infrastructure.database import Database
    from app.core.config import Settings
    from app.models import Manga, Chapter
    from app.services.library import Library
    from app.ui.main_window import MainWindow
    from app.services.export import export_chapter
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--chapter', type=Path)
    args = parser.parse_args()
    samples = []
    stop = threading.Event()
    def monitor():
        while not stop.wait(.02):
            samples.append(memory())
    thread = threading.Thread(target=monitor)
    thread.start()
    app = QApplication([])
    report = dict(version=__import__('app').__version__)
    try:
        with TemporaryDirectory(prefix='manga-ram-') as temporary:
            data = Path(temporary)
            db = Database(data / 'library.sqlite3')
            settings = Settings(library=str(data / 'library'))
            library = Library(db, Path(settings.library))
            _, ids = library.add(Manga('RAM', 'https://example.org/ram', chapters=[
                Chapter(f'Capítulo {i}', f'https://example.org/ram/{i}') for i in range(1000)]))
            library.enqueue(ids)
            window = MainWindow(db, settings, data, start_queue=False)
            window.timer.stop()
            window.show()
            app.processEvents()
            report['queue_start_mb'] = round(memory()[0] / 1024**2, 2)
            for _ in range(50):
                window.refresh_queue()
                app.processEvents()
            report['queue_after_50_updates_mb'] = round(memory()[0] / 1024**2, 2)
            folder = data / 'images'
            folder.mkdir()
            # 20 independent pages, ~120 MiB decoded in total. Only one stays open.
            for i in range(20):
                with Image.effect_noise((1200, 1800), 80) as noise:
                    with noise.convert('RGB') as picture:
                        picture.save(folder / f'{i:04}.png')
            if args.chapter:
                folder = args.chapter.resolve()
                report['source'] = str(folder)
            before_pdf = len(samples)
            target = data / 'chapter.pdf'
            export_chapter(folder, target, 'pdf')
            report['pdf_peak_mb'] = round(max(s[0] for s in samples[before_pdf:]) / 1024**2, 2)
            report['pdf_mb'] = round(target.stat().st_size / 1024**2, 2)
            with pikepdf.open(target) as pdf:
                report['pdf_pages'] = len(pdf.pages)
                assert report['pdf_pages'] > 0 and not pdf.check_pdf_syntax()
            import shutil
            from app.services.export import pdf_target
            first = db.chapters(db.mangas()[0]['id'])[0]
            destination = pdf_target(first)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, destination)
            before_reader = len(samples)
            window.open_reader(first['id'])
            limit = time.monotonic() + 5
            while (window.reader is None or window.reader.restoring) and time.monotonic() < limit:
                app.processEvents()
                time.sleep(.02)
            assert window.reader and window.reader.doc.pageCount() == report['pdf_pages']
            for page in range(report['pdf_pages']):
                window.reader.jump(page)
                app.processEvents()
                time.sleep(.04)
            window.reader.close()
            window.persist_reading()
            while window.jobs or window.pending_read:
                window.persist_reading()
                app.processEvents()
                time.sleep(.02)
            from PySide6.QtCore import QCoreApplication, QEvent
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
            report['reader_peak_mb'] = round(max(s[0] for s in samples[before_reader:]) / 1024**2, 2)
            report['end_mb'] = round(memory()[0] / 1024**2, 2)
            window.close()
    finally:
        stop.set()
        thread.join()
    report['total_peak_mb'] = round(max(s[0] for s in samples) / 1024**2, 2)
    report['private_peak_mb'] = round(max(s[1] for s in samples) / 1024**2, 2)
    version = __import__('app').__version__
    output = root / 'tmp' / (f'memory-profile-{version}-real.json' if args.chapter else f'memory-profile-{version}.json')
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
