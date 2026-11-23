import hashlib
import io
import json
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from app.core.exceptions import DownloadError, SecurityError
from app.infrastructure.filesystem import contained
from app.infrastructure.catalog import read_manifest


FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif", "BMP": ".bmp", "TIFF": ".tiff", "AVIF": ".avif"}


def inspect_image(data: bytes) -> dict:
    try:
        with Image.open(io.BytesIO(data)) as image:
            fmt = image.format
            width, height = image.size
            if width * height > 40_000_000:
                raise DownloadError("Dimensões da imagem excedem o limite seguro de 40 megapixels.")
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
        if fmt not in FORMATS:
            raise DownloadError("Formato de imagem não suportado.")
        return dict(extension=FORMATS[fmt], format=fmt, width=width, height=height,
                    size=len(data), sha256=hashlib.sha256(data).hexdigest())
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise DownloadError("Imagem inválida ou corrompida; tente reparar a página.") from exc


def valid_page(folder: Path, page: dict) -> bool:
    try:
        path = contained(folder, page["file"])
        info = inspect_image(path.read_bytes())
        return all(info[k] == page[k] for k in ("sha256", "size", "width", "height"))
    except (OSError, KeyError, DownloadError, SecurityError, ValueError):
        return False


def diagnose(folder: Path) -> dict:
    try:
        data = read_manifest(folder)
        if data is None:
            return dict(status="unverifiable", issues=["Sem manifesto de páginas esperadas"], pages=0)
        if data.get('pdf_only'):
            from app.infrastructure.catalog import Catalog
            from app.services.export import file_hash
            target = contained(folder.parent / 'PDF', data['pdf_name'])
            receipt = Catalog(folder.parent).get('receipt', target.name) or {}
            if target.is_file() and receipt.get('pdf') == file_hash(target):
                return dict(status='verified' if data.get('authoritative') else 'unverifiable',
                            issues=[], pages=data['expected'], valid_pages=data['expected'], expected=data['expected'])
            return dict(status='incomplete', issues=['PDF ausente ou modificado; baixe novamente.'], pages=0)
        pages = data["pages"]
        valid = [valid_page(folder, page) for page in pages]
        issues = [f"Página {i+1}: ausente ou corrompida" for i, ok in enumerate(valid) if not ok]
        expected = data["expected"]
        if not expected or len(pages) != expected:
            issues.append("Manifesto incompleto")
        if list(folder.glob("*.part")):
            issues.append("Arquivo temporário incompleto")
        hashes = [p.get("sha256") for p in pages if p.get("sha256")]
        duplicates = len(hashes) != len(set(hashes))
        if duplicates:
            issues.append("Conteúdo duplicado: confirme se é intencional na fonte")
        status = "incomplete" if issues else ("verified" if data.get("authoritative") else "unverifiable")
        return dict(status=status, issues=issues, pages=len(pages), valid_pages=sum(valid), expected=expected)
    except (OSError, ValueError, KeyError, TypeError):
        return dict(status="incomplete", issues=["Manifesto inválido"], pages=0)
