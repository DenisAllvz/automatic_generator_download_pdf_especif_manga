"""Local reading state, independent of download state and network providers."""
from pathlib import Path
from app.infrastructure.database import timestamp
from app.services.export import pdf_target


class Reading:
    def __init__(self, db):
        self.db = db

    def pdf(self, chapter):
        folder = Path(chapter['folder'])
        return folder if folder.is_file() and folder.suffix.lower() == '.pdf' else pdf_target(chapter)

    def chapters(self, mid):
        return [dict(c, pdf=str(self.pdf(c)), available=self.pdf(c).is_file()) for c in self.db.chapters(mid)]

    def mark(self, ids, read, updated=None):
        updated = updated or timestamp()
        with self.db.connection() as db:
            for cid in dict.fromkeys(ids):
                db.execute('''UPDATE chapters SET is_read=?,read_page=CASE WHEN ?=0 THEN 0 ELSE read_page END,
                    read_x=CASE WHEN ?=0 THEN 0 ELSE read_x END,read_y=CASE WHEN ?=0 THEN 0 ELSE read_y END,
                    read_total=CASE WHEN ?=0 THEN 0 ELSE read_total END,
                    read_scroll=CASE WHEN ?=0 THEN 0 ELSE read_scroll END,
                    read_updated=? WHERE id=? AND read_updated<=?''',
                    (int(read), int(read), int(read), int(read), int(read), int(read), updated, cid, updated))

    def progress(self, cid, page, total, x=0, y=0, zoom=0, finished=False, updated=None, scroll=0):
        updated = updated or timestamp()
        if total < 1 or not 0 <= page < total:
            raise ValueError('Posição de leitura inválida.')
        self.db.execute('''UPDATE chapters SET read_page=?,read_total=?,read_x=?,read_y=?,read_zoom=?,
            read_scroll=?,is_read=CASE WHEN ?=1 THEN 1 ELSE is_read END,read_updated=? WHERE id=? AND read_updated<=?''',
            (page, total, max(0, x), max(0, y), max(0, zoom), min(1, max(0, scroll)), int(finished), updated, cid, updated))

    def rename(self, mid, name):
        name = name.strip()
        if not name or len(name) > 180:
            raise ValueError('Use um nome entre 1 e 180 caracteres.')
        self.db.execute('UPDATE mangas SET title=?,custom_title=1,updated=? WHERE id=?', (name, timestamp(), mid))

    def resume(self, mid):
        chapters = self.chapters(mid)
        progress = [c for c in chapters if c['available'] and c['read_updated'] and not c['is_read']]
        if progress:
            return max(progress, key=lambda c: c['read_updated'])
        return next((c for c in chapters if c['available'] and not c['is_read']),
                    next((c for c in chapters if c['available']), None))
