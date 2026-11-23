"""Remove only registered page images after the chapter PDF is verified."""
from pathlib import Path
from app.infrastructure.catalog import read_manifest, save_manifest
from app.infrastructure.filesystem import contained
from app.services.export import has_current_pdf, file_hash, pdf_target


def cleanup_images(chapter):
    folder = Path(chapter['folder'])
    manifest = read_manifest(folder)
    if not manifest or not has_current_pdf(chapter):
        return 0
    count = 0
    for page in manifest['pages']:
        path = contained(folder, page['file'])
        if path.is_file() and not path.is_symlink() and file_hash(path) == page.get('sha256'):
            path.unlink()
            count += 1
    save_manifest(folder, dict(manifest, cached_pages=[], pdf_only=True, pdf_name=pdf_target(chapter).name))
    # An empty cache directory is unnecessary; other user files always keep it alive.
    if folder.is_dir() and not any(folder.iterdir()):
        folder.rmdir()
    return count


def cleanup_library(db):
    removed = 0
    for chapter in db.query("SELECT * FROM chapters WHERE url IS NOT NULL"):
        try:
            removed += cleanup_images(chapter)
        except (OSError, ValueError, KeyError):
            continue
    return removed
