from pathlib import Path
import json
from app.infrastructure.catalog import read_metadata
from app.models import Manga, Chapter


def test_update_preserves_disappeared_and_records_renames(setup_library):
    settings, db, library, mid, ids = setup_library
    manga = Manga("Obra Á", "https://example.org/manga/a", chapters=[Chapter("Capítulo 1 revisado", "https://example.org/chapter-1"),
                                                                 Chapter("Capítulo 2", "https://example.org/chapter-2")])
    _, new = library.add(manga)
    assert len(new) == 1
    folder = Path(db.mangas()[0]["folder"])
    assert read_metadata(folder)["changes"]["renamed"]
    library.add(Manga(manga.title, manga.url, chapters=manga.chapters[:1]))
    assert len(db.chapters(mid)) == 2
    assert read_metadata(folder)["changes"]["no_longer_listed"] == ["https://example.org/chapter-2"]


def test_correct_existing_site_title_without_moving_downloads(setup_library):
    settings, db, library, mid, ids = setup_library
    before = db.chapters(mid)
    tasks = db.tasks()
    db.execute("UPDATE mangas SET title=?,url=? WHERE id=?", ("Manga Livre", "https://mangalivre.blog/manga/vagabond/", mid))
    folder = db.mangas()[0]["folder"]
    library.repair_site_titles()
    assert db.mangas()[0]["title"] == "Vagabond"
    assert db.mangas()[0]["folder"] == folder and db.chapters(mid) == before
    assert [t["id"] for t in db.tasks()] == [t["id"] for t in tasks]
    library.repair_site_titles()
    assert db.mangas()[0]["title"] == "Vagabond"
