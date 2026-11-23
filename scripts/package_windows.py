"""Assemble portable folder as ZIP after a successful build and smoke test."""
import hashlib
import json
import shutil
import importlib.metadata
from pathlib import Path

root = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(root))
from app import __version__
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--output-name", default="MangaManager")
args = parser.parse_args()
package = root / "dist" / args.output_name
manifest = json.loads((package / "build-manifest.json").read_text(encoding="utf-8"))
smoke = json.loads((root / "tmp" / "build-smoke.json").read_text(encoding="utf-8"))
assert smoke["frozen"] and smoke["features"]["pdf_pages"] == 2
assert hashlib.sha256((package / "MangaManager.exe").read_bytes()).hexdigest() == manifest["exe_sha256"]
assert not (package / "data").exists(), "Não distribua os dados pessoais do modo portátil."
for name in ("README.md", "MANUAL_USUARIO.md", "GUIA_BUILD.md", "THIRD_PARTY_NOTICES.md", "VALIDACAO.md", "RELATORIO_FINAL.md", "REFERENCIAS.md"):
    if (root / name).exists():
        shutil.copy2(root / name, package / name)
for dependency in ("PySide6-Essentials", "shiboken6", "aiohttp", "beautifulsoup4", "Pillow", "pikepdf"):
    distribution = importlib.metadata.distribution(dependency)
    for file in distribution.files or []:
        if "license" in str(file).lower() or "copying" in str(file).lower():
            source = distribution.locate_file(file)
            if source.is_file():
                relative = Path(file)
                if relative.is_absolute() or ".." in relative.parts:
                    continue
                dest = package / "licenses" / dependency / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
archive = shutil.make_archive(str(root / "dist" / f"MangaManager-{__version__}-Windows-x64-portable"), "zip", root_dir=package.parent, base_dir=package.name)
import zipfile
with zipfile.ZipFile(archive) as contents:
    assert contents.testzip() is None
    assert f"{package.name}/MangaManager.exe" in contents.namelist()
    assert not any(name.startswith(f"{package.name}/data/") for name in contents.namelist())
print(archive)
