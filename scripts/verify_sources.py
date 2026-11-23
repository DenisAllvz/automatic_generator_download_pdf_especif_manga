"""Small live check of the requested sources, isolated from the user's library."""
import asyncio
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from app.core.config import Settings
from app.infrastructure.http_client import HttpClient
from app.extractors.registry import Registry
from app.services.integrity import inspect_image
from app.services.library import Library
from app.services.download_manager import DownloadManager
from app.services.export import export_chapter
from app.infrastructure.database import Database
from app.models import Manga


async def main():
    output = root / "tmp" / "source-review"
    output.mkdir(parents=True, exist_ok=True)
    evidence = {}
    async with HttpClient(Settings()) as client:
        for name, url in [("vagabond", "https://mangalivre.blog/manga/vagabond/"),
                          ("mangadex", "https://mangadex.org/title/39e55355-dfb4-44e9-bd0b-df1fc3a0e33e")]:
            try:
                extractor = Registry(client).select(url)
                manga = await extractor.get_manga_info(url)
                evidence[name] = dict(title=manga.title, chapters=len(manga.chapters), source=manga.url,
                                      listing_complete=manga.listing_complete)
                if name == "mangadex":
                    languages = sorted({c.language for c in manga.chapters})
                    chapter = next((c for c in manga.chapters if c.language == "pt-br"), manga.chapters[0])
                    pages = await extractor.get_chapter_pages(chapter.url)
                    content = await client.image(pages.urls[0], chapter.url)
                    info = inspect_image(content)
                    evidence[name].update(languages=languages, checked_chapter=chapter.title,
                                          pages=len(pages.urls), first_page=info)
                    if "--full-chapter" in sys.argv:
                        import time
                        run_root = output / f"chapter-check-{time.time_ns()}"
                        settings = Settings(library=str(run_root / "library"))
                        db = Database(run_root / "library.sqlite3")
                        library = Library(db, Path(settings.library))
                        mid, ids = library.add(Manga(manga.title, manga.url, manga.description, chapters=[chapter]))
                        library.enqueue(ids)
                        task = db.tasks()[0]
                        db.execute("UPDATE tasks SET status='running' WHERE id=?", (task["id"],))
                        manager = DownloadManager(db, settings)
                        manager.running = True
                        await manager.download(task, client, Registry(client))
                        local = db.chapters(mid)[0]
                        assert db.tasks()[0]["status"] == "complete", db.tasks()[0]["error"]
                        pdf = run_root / "chapter.pdf"
                        export_chapter(Path(local["folder"]), pdf, "pdf")
                        import pikepdf
                        with pikepdf.open(pdf) as document:
                            assert len(document.pages) == len(pages.urls)
                            pdf_pages = len(document.pages)
                        evidence[name].update(download_status=local["status"], pdf_pages=pdf_pages,
                                              full_chapter_evidence=str(run_root))
                print(name, json.dumps(evidence[name], ensure_ascii=False), flush=True)
            except Exception as exc:
                evidence[name] = dict(error=f"{type(exc).__name__}: {exc}")
                print(name, evidence[name]["error"], flush=True)
    (output / "live-evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
