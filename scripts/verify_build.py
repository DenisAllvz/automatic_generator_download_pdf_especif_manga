"""Run frozen app with isolated data from a directory unrelated to the source."""
import json
import subprocess
import tempfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-name", default="MangaManager")
    parser.add_argument("--source-check")
    args = parser.parse_args()
    exe = root / "dist" / args.output_name / "MangaManager.exe"
    evidence = root / "tmp" / "build-smoke.json"
    if evidence.exists():
        evidence.unlink()
    screenshot = root / "tmp" / "build-ui.png"
    manifest = json.loads((exe.parent / "build-manifest.json").read_text(encoding="utf-8"))
    import hashlib
    assert hashlib.sha256(exe.read_bytes()).hexdigest() == manifest["exe_sha256"]
    assert all(hashlib.sha256((root / file).read_bytes()).hexdigest() == expected
               for file, expected in manifest["source_sha256"].items()), "Build desatualizado"
    with tempfile.TemporaryDirectory(prefix="manga-build-test-") as temp:
        command = [str(exe), "--data-dir", str(Path(temp) / "data"), "--smoke-test", str(evidence), "--screenshot", str(screenshot)]
        if args.source_check:
            command.extend(["--source-check", args.source_check])
        try:
            result = subprocess.run(command, cwd=temp, timeout=60, capture_output=True)
        except subprocess.TimeoutExpired as exc:
            import shutil
            failure = root / "tmp" / "build-failure"
            shutil.copytree(Path(temp) / "data", failure, dirs_exist_ok=True)
            raise RuntimeError(f"Smoke excedeu 60s. Dados de diagnóstico: {failure}; stderr: {exc.stderr!r}") from exc
        if result.returncode != 0 or not evidence.exists():
            raise RuntimeError(f"Smoke falhou: {result.returncode}: {result.stderr!r}")
        report = json.loads(evidence.read_text(encoding="utf-8"))
        if report.get("error"):
            raise RuntimeError(f"Smoke falhou: {report['error']} (HTTP {report.get('http_status')})")
        assert report["frozen"] and report["screens"] == 7 and report["database"]
        assert report["features"]["download_log"] and report["features"]["queue_cleaned"]
        assert report["features"]["automatic_pdf"]
        assert report["features"]["clean_metadata"]
        assert all(report['features'][name] for name in ('reader', 'reading_state', 'cover', 'pdf_only', 'drive_sync_offline', 'drive_encryption'))
        assert report["features"]["batch_pdf_count"] == 2 and report["features"]["cbz"] and report["features"]["pdf_pages"] == 2
        if args.source_check:
            assert report["features"]["source_check"]["pdf_pages"] > 0
        print(json.dumps(report, ensure_ascii=False, indent=2))
    print("Smoke OK no host atual. Não substitui validação em máquina Windows limpa.")


if __name__ == "__main__":
    main()
