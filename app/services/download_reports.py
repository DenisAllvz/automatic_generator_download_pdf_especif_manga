"""Persist finished downloads before removing them from the working queue."""
import json
from pathlib import Path
from app.infrastructure.database import timestamp
from app.infrastructure.filesystem import atomic_json, atomic_bytes, safe_name
from app.services.export import pdf_target


class DownloadReports:
    def __init__(self, db, destination):
        self.db, self.destination = db, Path(destination)
        db.execute('''CREATE TABLE IF NOT EXISTS download_history(
            task_id INTEGER PRIMARY KEY, payload TEXT NOT NULL, report TEXT NOT NULL)''')

    def finish_ready(self):
        reports = []
        # Same lock as the scheduler: a new task cannot enter between snapshot and cleanup.
        with self.db.connection() as connection:
            works = connection.execute('''SELECT m.id,m.title FROM mangas m
                WHERE EXISTS(SELECT 1 FROM chapters c JOIN tasks t ON t.chapter_id=c.id
                    WHERE c.manga_id=m.id AND t.status IN ('complete','cancelled'))
                AND NOT EXISTS(SELECT 1 FROM chapters c JOIN tasks t ON t.chapter_id=c.id
                    WHERE c.manga_id=m.id AND t.status IN ('queued','running','paused'))''').fetchall()
            for work in works:
                rows = [dict(r) for r in connection.execute('''SELECT t.*,c.title chapter,c.folder,
                    c.id chapter_identity,m.title manga FROM tasks t JOIN chapters c ON c.id=t.chapter_id
                    JOIN mangas m ON m.id=c.manga_id WHERE m.id=? AND t.status IN ('complete','cancelled')
                    ORDER BY t.id''', (work['id'],))]
                failures = connection.execute('''SELECT COUNT(*) FROM tasks t JOIN chapters c ON c.id=t.chapter_id
                    WHERE c.manga_id=? AND t.status='failed' ''', (work['id'],)).fetchone()[0]
                for row in rows:
                    target = pdf_target(dict(folder=row['folder'], title=row['chapter'], id=row['chapter_identity']))
                    row['pdf'] = str(target)
                    row['pdf_exists'] = target.is_file()
                base = self.destination / f"{safe_name(work['title'])}-{work['id']}-{rows[-1]['id']}"
                report = dict(work=work['title'], created=timestamp(), failed=failures,
                              completed=sum(r['status']=='complete' for r in rows),
                              cancelled=sum(r['status']=='cancelled' for r in rows), tasks=rows,
                              missing_pdf=sum(r['status']=='complete' and not r['pdf_exists'] for r in rows),
                              file=str(base) + '.txt')
                lines = [f"Obra: {work['title']}", f"Data UTC: {report['created']}",
                         f"Concluídos: {report['completed']} | Falhas mantidas na fila: {failures} | Cancelados: {report['cancelled']}", '']
                for row in rows:
                    state = 'CONCLUÍDO' if row['status']=='complete' else 'CANCELADO'
                    lines.extend([f"[{state}] {row['chapter']} — {row['done']}/{row['total']} páginas",
                                  f"PDF: {row['pdf']}" if row['pdf_exists'] else 'PDF não encontrado (registro anterior ou arquivo movido).', ''])
                # On any write failure, the transaction leaves every task untouched.
                atomic_json(Path(str(base) + '.json'), report)
                atomic_bytes(Path(report['file']), '\n'.join(lines).encode('utf-8-sig'))
                for row in rows:
                    connection.execute('INSERT INTO download_history(task_id,payload,report) VALUES(?,?,?)',
                                       (row['id'], json.dumps(row, ensure_ascii=False), report['file']))
                    connection.execute("DELETE FROM tasks WHERE id=? AND status IN ('complete','cancelled')", (row['id'],))
                reports.append(report)
        return reports
