"""Read-only PE import/export diagnostic for build failures."""
from pathlib import Path
import os
import pefile

root = Path(__file__).resolve().parents[1] / "dist" / "MangaManager" / "_internal"
directories = [root, root / "PySide6", root / "shiboken6", Path(os.environ["WINDIR"]) / "System32"]
for file in [root / "PySide6" / "QtCore.pyd", root / "PySide6" / "Qt6Core.dll", root / "shiboken6" / "Shiboken.pyd"]:
    if not file.exists():
        continue
    print(file.name)
    parsed = pefile.PE(str(file), max_symbol_exports=65536)
    for item in parsed.DIRECTORY_ENTRY_IMPORT:
        name = item.dll.decode()
        candidates = [directory / name for directory in directories if (directory / name).exists()]
        if not candidates:
            print("  DLL absent", name)
            continue
        dependency = pefile.PE(str(candidates[0]), max_symbol_exports=65536)
        names = {symbol.name for symbol in dependency.DIRECTORY_ENTRY_EXPORT.symbols} if hasattr(dependency, "DIRECTORY_ENTRY_EXPORT") else set()
        missing = [i.name.decode(errors="replace") for i in item.imports if i.name and i.name not in names]
        if missing:
            print("  MISSING", candidates[0], missing[:25])
