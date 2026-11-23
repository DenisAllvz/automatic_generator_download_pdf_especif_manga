"""Windows x64 onedir build; no browser runtime is bundled."""
import argparse
import os
import platform
import subprocess
import shutil
import hashlib
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--portable", action="store_true")
    parser.add_argument("--output-name", default="MangaManager")
    args = parser.parse_args()
    if sys.platform != "win32" or platform.architecture()[0] != "64bit":
        raise SystemExit("Execute em Windows x64 com Python 64 bits.")
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    if not args.output_name.replace("-", "").replace("_", "").replace(".", "").isalnum():
        raise SystemExit("Nome de pasta inválido.")
    output = root / "dist" / args.output_name
    if (output / "data").exists():
        raise SystemExit("O diretório de build contém dados portáteis. Preserve/mova esses dados antes de reconstruir; nada foi apagado.")
    source_files = [root / "main.py", *sorted((root / "app").rglob("*.py"))]
    source_hashes = {str(file.relative_to(root)): hashlib.sha256(file.read_bytes()).hexdigest() for file in source_files}
    # Code-native icon drawn locally; no external asset/license dependency.
    from PIL import Image, ImageDraw
    icon = Image.new("RGBA", (256, 256), "#0d1220")
    draw = ImageDraw.Draw(icon)
    draw.rounded_rectangle((25, 25, 231, 231), radius=45, fill="#366be0")
    draw.polygon([(59, 193), (59, 70), (91, 70), (128, 132), (165, 70), (197, 70), (197, 193), (167, 193), (167, 123), (128, 185), (89, 123), (89, 193)], fill="white")
    asset = root / "assets" / "app.ico"
    asset.parent.mkdir(exist_ok=True)
    icon.save(asset, sizes=[(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)])
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--windowed", "--onedir",
                    "--name", args.output_name, "--icon", str(asset), "--add-data", f"{root / 'assets'};assets",
                    "--distpath", str(root / "dist"), "--workpath", str(root / "tmp" / "build"),
                    "--specpath", str(root / "tmp"), "--exclude-module", "PySide6.QtWebEngineCore",
                    "--exclude-module", "PySide6.QtWebEngineWidgets", "--exclude-module", "playwright",
                    "--exclude-module", "customtkinter", "--exclude-module", "tkinter",
                    str(root / "main.py")], cwd=root, check=True)
    # Python 3.13.0 ships an older VC runtime than current Qt. Keep the runtime
    # loaded by the bootloader compatible with the Qt wheel instead of mixing DLLs.
    import PySide6
    qt_root = Path(PySide6.__file__).parent
    internal = output / "_internal"
    # Qt uses the Windows ICU API (unsuffixed exports). A developer PATH may
    # contain another icuuc.dll with version-suffixed exports. Do not ship that
    # unrelated DLL: use the ICU API provided by the supported Windows system.
    conflicting_icu = internal / "icuuc.dll"
    if conflicting_icu.exists() and conflicting_icu.resolve().is_relative_to((root / "dist").resolve()):
        conflicting_icu.unlink()
    for name in ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "msvcp140_1.dll",
                 "msvcp140_2.dll", "msvcp140_codecvt_ids.dll", "concrt140.dll"):
        runtime = qt_root / name
        if runtime.exists():
            shutil.copy2(runtime, internal / name)
    for document in ("README.md", "MANUAL_USUARIO.md", "GUIA_BUILD.md", "THIRD_PARTY_NOTICES.md"):
        if (root / document).exists():
            shutil.copy2(root / document, output / document)
    if args.portable:
        (output / "portable.flag").touch()
    assert source_hashes == {str(file.relative_to(root)): hashlib.sha256(file.read_bytes()).hexdigest() for file in source_files}, "Código mudou durante o build; reconstrua."
    from app.infrastructure.filesystem import atomic_json
    exe = output / f"{args.output_name}.exe"
    if args.output_name != "MangaManager":
        exe = exe.rename(output / "MangaManager.exe")
    atomic_json(exe.parent / "build-manifest.json", dict(python=platform.python_version(), windows=platform.platform(),
        qt=PySide6.__version__, source_sha256=source_hashes, exe_sha256=hashlib.sha256(exe.read_bytes()).hexdigest()))
    print(exe)


if __name__ == "__main__":
    main()
