import json
from pathlib import Path
import pytest
from app.services.export import export_chapter
from app.services.integrity import inspect_image
from app.infrastructure.filesystem import atomic_json
from app.core.exceptions import DownloadError


def test_pdf_preserves_page_count_and_dimensions(tmp_path, image_bytes):
    folder = tmp_path / "chapter"
    folder.mkdir()
    (folder / "1.png").write_bytes(image_bytes)
    info = inspect_image(image_bytes)
    info.pop("extension")
    atomic_json(folder / "manifest.json", dict(expected=1, pages=[dict(file="1.png", **info)]))
    target = tmp_path / "sample.pdf"
    export_chapter(folder, target, "pdf")
    import pikepdf
    with pikepdf.open(target) as pdf:
        assert len(pdf.pages) == 1
        box = pdf.pages[0].MediaBox
        assert float(box[2])/float(box[3]) == pytest.approx(.5)
    with pytest.raises(DownloadError, match="já existe"):
        export_chapter(folder, target, "pdf")


def test_incomplete_export_rejected(tmp_path, image_bytes):
    folder = tmp_path / "chapter"
    folder.mkdir()
    (folder / "1.png").write_bytes(image_bytes)
    info = inspect_image(image_bytes)
    info.pop("extension")
    atomic_json(folder / "manifest.json", dict(expected=2, pages=[dict(file="1.png", **info)]))
    with pytest.raises(DownloadError, match="incompleto"):
        export_chapter(folder, tmp_path / "bad.cbz", "cbz")


def test_batch_pdf_continues_failures_and_preserves_existing(tmp_path, image_bytes):
    from app.services.export import export_chapters
    chapters = []
    for index in range(4):
        folder = tmp_path / str(index) / "Capítulo"
        folder.mkdir(parents=True)
        (folder / "1.png").write_bytes(image_bytes if index != 1 else b"broken")
        chapters.append(dict(id=index, title=f"Capítulo {index}", folder=str(folder)))
    destination = tmp_path / "pdfs"
    destination.mkdir()
    existing = destination / "Capítulo.pdf"
    existing.write_bytes(b"keep existing")
    ticks = []
    report = export_chapters(chapters, destination, "pdf", lambda *args: ticks.append(args))
    assert len(report["created"]) == 2
    assert len(report["skipped"]) == 1
    assert len(report["failed"]) == 1
    assert ticks[-1][:2] == (4, 4)
    assert existing.read_bytes() == b"keep existing"
    import pikepdf
    for path in report["created"]:
        with pikepdf.open(path) as pdf:
            assert len(pdf.pages) == 1
    assert not list(destination.glob("*.part"))
