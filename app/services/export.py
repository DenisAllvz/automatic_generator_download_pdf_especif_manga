import json
import os
import zipfile
import hashlib
import threading
from tempfile import TemporaryDirectory
from pathlib import Path
from app.core.exceptions import DownloadError
from app.infrastructure.filesystem import contained, natural_key, safe_name
from app.services.integrity import valid_page, inspect_image
from app.infrastructure.catalog import Catalog, read_manifest
from app.services.pdf_stream import write_pdf


_pdf_lock = threading.Lock()


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def has_current_pdf(chapter):
    """Check a trusted PDF without decoding every original page or reading it all into RAM."""
    try:
        folder = Path(chapter['folder'])
        target = pdf_target(chapter)
        if not target.is_file():
            return False
        saved = Catalog(folder.parent).get('receipt', target.name) or {}
        manifest = read_manifest(folder)
        if not manifest or len(manifest['pages']) != manifest['expected']:
            return False
        fingerprint = hashlib.sha256(b''.join(bytes.fromhex(p['sha256']) for p in manifest['pages'])).hexdigest()
        if saved.get('images') != fingerprint:
            return False
        stat = target.stat()
        if saved.get('size') == stat.st_size and saved.get('mtime_ns') == stat.st_mtime_ns:
            return True
        return saved.get('pdf') == file_hash(target)
    except (OSError, ValueError, TypeError, KeyError):
        return False


def pdf_target(chapter):
    folder = Path(chapter["folder"])
    # Identity prevents two releases with the same chapter number colliding.
    return folder.parent / "PDF" / f"{safe_name(chapter['title'])}-{chapter['id']}.pdf"


def ensure_pdf(chapter):
    """Generate atomically; a receipt ties an existing PDF to these exact images."""
    folder, target = Path(chapter["folder"]), pdf_target(chapter)
    with _pdf_lock:
        if has_current_pdf(chapter):
            return target
        paths = local_pages(folder)
        fingerprint = hashlib.sha256(b''.join(bytes.fromhex(file_hash(p)) for p in paths)).hexdigest()
        catalog = Catalog(folder.parent)
        if (folder / 'manifest.json').exists() or target.with_suffix('.pdf.json').exists() or (folder.parent / 'metadata.json').exists():
            catalog.migrate()
        replace_existing = False
        if target.exists():
            try:
                saved = catalog.get('receipt', target.name) or {}
                if saved['pdf'] == file_hash(target):
                    if saved['images'] == fingerprint:
                        return target
                    replace_existing = True
            except (OSError, ValueError, KeyError):
                pass
            if not replace_existing:
                raise DownloadError(f"PDF existente sem confirmação de integridade: {target.name}. Mova esse PDF para outra pasta e tente novamente; as imagens serão reutilizadas.")
        export_chapter(folder, target, 'pdf', replace_existing=replace_existing)
        stat = target.stat()
        catalog.put('receipt', target.name, dict(images=fingerprint, pdf=file_hash(target), pages=len(paths),
                                               size=stat.st_size, mtime_ns=stat.st_mtime_ns))
        return target


def local_pages(folder: Path, validate: bool = True) -> list[Path]:
    if not folder.is_dir():
        return []
    data = read_manifest(folder)
    if data is not None:
        if len(data["pages"]) != data["expected"] or not data["pages"]:
            raise DownloadError("Capítulo incompleto; repare antes de ler ou exportar.")
        if validate and not all(valid_page(folder, p) for p in data["pages"]):
            raise DownloadError("Página ausente ou inválida; execute o diagnóstico.")
        return [contained(folder, p["file"]) for p in data["pages"]]
    return sorted([p for p in folder.iterdir() if not p.is_symlink() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".avif")], key=lambda p: natural_key(p.name))


def export_chapter(folder: Path, target: Path, fmt: str, *, replace_existing=False):
    paths = local_pages(folder)
    if not paths:
        raise DownloadError("Nenhuma página local para exportar.")
    if target.exists() and not replace_existing:
        raise DownloadError("O arquivo de destino já existe. Escolha outro nome.")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".part")
    try:
        if fmt == "cbz":
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
                for index, path in enumerate(paths, 1):
                    inspect_image(path.read_bytes())
                    archive.write(path, f"{index:04d}{path.suffix}")
        elif fmt == "pdf":
            write_pdf(paths, temporary)
            import pikepdf
            with pikepdf.open(temporary) as document:
                if len(document.pages) != len(paths):
                    raise DownloadError('O PDF gerado não contém todas as páginas.')
        else:
            raise ValueError("Formato inválido")
        os.replace(temporary, target)
    except Exception as exc:
        if isinstance(exc, (DownloadError, ValueError, OSError)):
            raise
        raise DownloadError(f'Não foi possível gerar o PDF: {exc}') from exc
    finally:
        if temporary.exists():
            temporary.unlink()


def export_chapters(chapters, destination: Path, fmt: str, progress=None):
    """One file per chapter; preserve existing outputs and continue after failures."""
    if fmt not in ("pdf", "cbz"):
        raise ValueError("Formato inválido")
    destination.mkdir(parents=True, exist_ok=True)
    report = dict(created=[], skipped=[], failed=[])
    used = set()
    for index, chapter in enumerate(chapters, 1):
        folder = Path(chapter["folder"])
        # Library folder names include source identity, keeping versions distinct.
        name = safe_name(folder.name, limit=120)
        if name.casefold() in used:
            name += f"-{chapter['id']}"
        used.add(name.casefold())
        target = destination / f"{name}.{fmt}"
        try:
            if folder.is_file():
                report["skipped"].append(chapter["title"])
            elif target.exists():
                report["skipped"].append(chapter["title"])
            else:
                export_chapter(folder, target, fmt)
                report["created"].append(str(target))
        except Exception as exc:
            report["failed"].append(dict(chapter=chapter["title"], error=str(exc)))
        if progress:
            progress(index, len(chapters), chapter["title"])
    return report
