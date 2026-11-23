import hashlib
import json
import os
import re
import unicodedata
import time
from pathlib import Path
from app.core.exceptions import SecurityError


def safe_name(value: str, limit: int = 70) -> str:
    value = unicodedata.normalize("NFC", value)
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")[:limit].rstrip(" .")
    if not value or value in (".", ".."):
        value = "Sem título"
    if value.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))}:
        value = "_" + value
    return value


def identity(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:12]


def contained(root: Path, name: str) -> Path:
    result = (root / name).resolve()
    if not result.is_relative_to(root.resolve()) or result == root.resolve():
        raise SecurityError("Caminho fora da biblioteca.")
    return result


def atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    with temporary.open("wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    # Antivirus/indexing can briefly hold the destination open on Windows.
    for attempt in range(5):
        try:
            os.replace(temporary, path)
            break
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))


def atomic_json(path: Path, data) -> None:
    atomic_bytes(path, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))


def natural_key(value: str):
    return tuple((0, int(p)) if p.isdigit() else (1, p.casefold()) for p in re.split(r"(\d+)", value))


def chapter_key(title: str):
    match = re.search(r"(?:cap[ií]tulo|chapter|chap|cap|ch|第)[\s._-]*(\d+(?:[.,]\d+)?)", title, re.I)
    if match:
        from decimal import Decimal
        return (1, Decimal(match.group(1).replace(",", ".")), natural_key(title))
    if re.search(r"pr[oó]logo|prologue", title, re.I):
        return (0, 0, natural_key(title))
    return (2, 0, natural_key(title))
