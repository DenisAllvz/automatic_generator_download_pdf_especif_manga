"""CLI compatível: capítulo autorizado para PDF, preservando imagens."""
import argparse
import asyncio
import tempfile
from pathlib import Path
from app.core.config import Settings
from app.extractors.registry import Registry
from app.infrastructure.database import Database
from app.models import Manga, Chapter
from app.services.library import Library
from app.services.download_manager import DownloadManager
from app.services.export import export_chapter


def baixar_capitulo(url: str, nome_arquivo_pdf: str):
    target = Path(nome_arquivo_pdf).resolve()
    settings = Settings(library=str(target.parent / "Imagens_Capitulos"))
    with tempfile.TemporaryDirectory() as temp:
        db = Database(Path(temp) / "cli.sqlite3")
        library = Library(db, Path(settings.library))
        _, ids = library.add(Manga(target.stem, url, chapters=[Chapter(target.stem, url)]))
        library.enqueue(ids)
        manager = DownloadManager(db, settings)
        async def run():
            from app.infrastructure.http_client import HttpClient
            async with HttpClient(settings) as client:
                manager.running = True
                task = db.tasks()[0]
                db.execute("UPDATE tasks SET status='running' WHERE id=?", (task["id"],))
                await manager.download(task, client, Registry(client))
        asyncio.run(run())
        task = db.tasks()[0]
        if task["status"] != "complete":
            raise RuntimeError(task["error"] or "Download interrompido")
        chapter = db.query("SELECT * FROM chapters WHERE id=?", (task["chapter_id"],))[0]
        export_chapter(Path(chapter["folder"]), target, "pdf")
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("pdf", help="Destino PDF; imagens são preservadas ao lado")
    args = parser.parse_args()
    print(baixar_capitulo(args.url, args.pdf))
