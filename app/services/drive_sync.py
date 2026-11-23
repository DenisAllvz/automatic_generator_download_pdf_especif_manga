"""Compare registered PDFs with one Drive folder and append only missing chapters."""
import hashlib
from pathlib import Path
import re
import unicodedata
from app.infrastructure.drive_auth import DriveError, DriveCancelled
from app.infrastructure.google_drive import FOLDER
from app.infrastructure.filesystem import safe_name
from app.services.reading import Reading


def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value).casefold() if c.isalnum() and not unicodedata.combining(c))


def chapter_name(value):
    return normalized(re.sub(r'-[0-9a-f]{12}$', '', Path(value).stem, flags=re.I))


class DriveSync:
    def __init__(self, db, client):
        self.db, self.client = db, client
        with db.connection() as connection:
            connection.execute('''CREATE TABLE IF NOT EXISTS drive_hashes(
                path TEXT PRIMARY KEY,size INTEGER,mtime_ns INTEGER,md5 TEXT)''')
            connection.execute('''CREATE TABLE IF NOT EXISTS drive_folders(
                root_id TEXT,manga_id TEXT,folder_id TEXT,PRIMARY KEY(root_id,manga_id))''')

    def sources(self, mid='', progress=lambda text: None):
        mangas = {m['id']: m for m in self.db.mangas() if not mid or m['id'] == mid}
        cache = {r['path']: r for r in self.db.query('SELECT * FROM drive_hashes')}
        rows = self.db.query('SELECT * FROM chapters')
        sources, seen = [], set()
        for chapter in rows:
            self.client.check_cancel()
            if chapter['manga_id'] not in mangas:
                continue
            path = Reading(self.db).pdf(chapter)
            if path.is_symlink() or not path.is_file() or str(path.resolve()) in seen:
                continue
            with path.open('rb') as stream:
                if stream.read(5) != b'%PDF-':
                    continue
            seen.add(str(path.resolve()))
            progress(f"Conferindo {mangas[chapter['manga_id']]['title']} · {chapter['title']}")
            before = path.stat()
            saved = cache.get(str(path))
            if saved and (saved['size'], saved['mtime_ns']) == (before.st_size, before.st_mtime_ns):
                digest = saved['md5']
            else:
                digestor = hashlib.md5()
                with path.open('rb') as stream:
                    while block := stream.read(1024 * 1024):
                        self.client.check_cancel()
                        digestor.update(block)
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise DriveError('Um PDF mudou durante a conferência. Aguarde a conversão e confira novamente.')
                digest = digestor.hexdigest()
                self.db.execute('INSERT OR REPLACE INTO drive_hashes VALUES(?,?,?,?)',
                                (str(path), before.st_size, before.st_mtime_ns, digest))
            manga = mangas[chapter['manga_id']]
            sources.append(dict(cid=chapter['id'], mid=manga['id'], work=manga['title'],
                                chapter=chapter['title'], path=str(path), md5=digest,
                                size=before.st_size, mtime_ns=before.st_mtime_ns,
                                aliases=[manga['title'], safe_name(manga['title'], 150), Path(manga['folder']).name]))
        from app.infrastructure.filesystem import chapter_key
        return sorted(sources, key=lambda s: (s['work'].casefold(), chapter_key(s['chapter'])))

    def inventory(self, root, progress):
        folders, files = {root['id']: dict(root, ancestors=[])}, []
        pending = [root['id']]
        visited = set()
        while pending:
            self.client.check_cancel()
            parent = pending.pop()
            if parent in visited:
                continue
            visited.add(parent)
            progress('Conferindo arquivos que já estão no Google Drive…')
            for item in self.client.list_children(parent):
                self.client.check_cancel()
                item = dict(item, ancestors=folders[parent]['ancestors'] + [parent])
                if item.get('mimeType') == FOLDER:
                    folders[item['id']] = item
                    pending.append(item['id'])
                elif item.get('mimeType') == 'application/pdf' or item.get('name', '').lower().endswith('.pdf'):
                    files.append(item)
            if len(folders) > 5000 or len(files) > 200000:
                raise DriveError('Esta pasta é muito ampla. Escolha uma pasta específica para os mangás.')
        return folders, files

    def find_parent(self, source, root, folders, grouped, single_work):
        if not grouped or (single_work and normalized(root['name']) in {normalized(a) for a in source['aliases']}):
            return root['id']
        saved = self.db.query('SELECT folder_id FROM drive_folders WHERE root_id=? AND manga_id=?', (root['id'], source['mid']))
        if saved and saved[0]['folder_id'] in folders:
            return saved[0]['folder_id']
        tagged = [f['id'] for f in folders.values() if f.get('appProperties', {}).get('mmWork') == source['mid']]
        if len(tagged) == 1:
            return tagged[0]
        aliases = {normalized(a) for a in source['aliases']}
        matches = [f['id'] for f in folders.values() if f['id'] != root['id'] and normalized(f['name']) in aliases
                   and f.get('appProperties', {}).get('mmWork', source['mid']) == source['mid']]
        if len(matches) > 1 or len(tagged) > 1:
            raise DriveError(f"Há mais de uma pasta possível para {source['work']}. Escolha a pasta exata e confira somente essa obra.")
        return matches[0] if matches else None

    @staticmethod
    def compare(source, files, parent):
        identities = {source['cid']}
        original = re.search(r'-([0-9a-f]{12})\.pdf$', Path(source['path']).name, re.I)
        if original:
            identities.add(original.group(1).lower())
        relevant = [f for f in files if (parent and parent in f.get('ancestors', []))
                    or f.get('appProperties', {}).get('mmChapter') in identities
                    or any(ident in f.get('name', '') for ident in identities)]
        def compatible(file):
            ident = file.get('appProperties', {}).get('mmChapter')
            match = re.search(r'-([0-9a-f]{12})\.pdf$', file.get('name', ''), re.I)
            if ident and ident not in identities:
                return False
            if match and match.group(1).lower() not in identities:
                return False
            pattern = r'(?:cap[ií]tulo|chapter|cap)[\s_-]*(\d+(?:[.,]\d+)?)'
            remote_num = re.search(pattern, file.get('name', ''), re.I)
            local_num = re.search(pattern, source['chapter'], re.I)
            return not (remote_num and local_num and remote_num.group(1).replace(',', '.') != local_num.group(1).replace(',', '.'))
        relevant = [f for f in relevant if compatible(f)]
        identical = next((f for f in relevant if f.get('md5Checksum', '').lower() == source['md5']
                          and int(f.get('size', -1)) == source['size']), None)
        if identical:
            return 'existing', identical['id']
        same_chapter = next((f for f in relevant if f.get('appProperties', {}).get('mmChapter') in identities
                             or any(ident in f.get('name', '') for ident in identities)
                             or chapter_name(f.get('name', '')) == chapter_name(Path(source['path']).name)
                             or chapter_name(f.get('name', '')) == normalized(source['chapter'])), None)
        return ('conflict', same_chapter['id']) if same_chapter else ('missing', None)

    def plan(self, root_id, mid='', grouped=True, progress=lambda text: None):
        root = self.client.get_folder(root_id)
        sources = self.sources(mid, progress)
        folders, files = self.inventory(root, progress)
        rows = []
        parents = {}
        for source in sources:
            self.client.check_cancel()
            if source['mid'] not in parents:
                parents[source['mid']] = self.find_parent(source, root, folders, grouped, bool(mid))
            parent = parents[source['mid']]
            status, remote = self.compare(source, files, parent)
            if status == 'conflict' and parent and getattr(self.client, 'pending_upload', lambda *args: None)(parent, source):
                candidate = next((f for f in files if f['id'] == remote), {})
                if not candidate.get('md5Checksum') and candidate.get('appProperties', {}).get('mmChapter') == source['cid']:
                    status = 'missing'
            rows.append(dict(source, status=status, remote_id=remote, parent=parent))
        return dict(root=root, mid=mid, grouped=grouped, rows=rows,
                    existing=sum(r['status']=='existing' for r in rows),
                    missing=sum(r['status']=='missing' for r in rows),
                    conflicts=sum(r['status']=='conflict' for r in rows))

    def send(self, plan, progress=lambda info: None):
        result = dict(uploaded=0, skipped=plan['existing'], conflicts=plan['conflicts'], failed=[], cancelled=False)
        parents = {}
        for source in plan['rows']:
            if source['status'] != 'missing':
                continue
            try:
                self.client.check_cancel()
                if source['mid'] not in parents:
                    parent = source['parent']
                    if parent is None:
                        children = self.client.list_children(plan['root']['id'])
                        folders = {f['id']: f for f in children if f.get('mimeType') == FOLDER}
                        parent = self.find_parent(source, plan['root'], folders, plan['grouped'], bool(plan['mid']))
                        if parent is None:
                            parent = self.client.create_folder(plan['root']['id'], safe_name(source['work'], 150), source['mid'])['id']
                    parents[source['mid']] = parent
                    if parent != plan['root']['id']:
                        self.db.execute('INSERT OR REPLACE INTO drive_folders VALUES(?,?,?)', (plan['root']['id'], source['mid'], parent))
                parent = parents[source['mid']]
                # Recheck just before sending: files can arrive after the preview.
                files = [dict(f, ancestors=[parent]) for f in self.client.list_children(parent) if f.get('mimeType') != FOLDER]
                status, _ = self.compare(source, files, parent)
                if status == 'existing':
                    result['skipped'] += 1
                    continue
                if status == 'conflict':
                    pending = getattr(self.client, 'pending_upload', lambda *args: None)(parent, source)
                    candidate = next((f for f in files if f['id'] == self.compare(source, files, parent)[1]), {})
                    if not pending or candidate.get('md5Checksum') or candidate.get('appProperties', {}).get('mmChapter') != source['cid']:
                        result['conflicts'] += 1
                        continue
                def update(done, total):
                    progress(dict(work=source['work'], chapter=source['chapter'], done=done, total=total))
                update(0, source['size'])
                self.client.upload(parent, source, update)
                result['uploaded'] += 1
            except DriveCancelled:
                result['cancelled'] = True
                break
            except (DriveError, OSError) as exc:
                result['failed'].append(dict(work=source['work'], chapter=source['chapter'], error=str(exc)))
        return result
