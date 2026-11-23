"""Characterization reads AST; never imports/destructively runs original GUI."""
import ast
from pathlib import Path


def test_legacy_entries_and_selectors_preserved():
    source = Path("legacy/app_manga_original.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert {n.name for n in tree.body if isinstance(n, ast.ClassDef)} == {"AppManga", "ExtratorMangaAssincrono"}
    assert "wp-manga-chapter-img" in source and "chapter-image" in source
    assert "Downloads_Mangas" in source


def test_original_cli_pdf_function_preserved_in_snapshot():
    tree = ast.parse(Path("legacy/download_manga_original.py").read_text(encoding="utf-8"))
    assert any(isinstance(n, ast.FunctionDef) and n.name == "baixar_capitulo" for n in tree.body)
