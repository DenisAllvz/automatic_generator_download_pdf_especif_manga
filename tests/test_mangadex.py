from urllib.parse import urlsplit, parse_qs
from uuid import UUID
import json
import pytest
from app.core.exceptions import ExtractionError, SecurityError, DownloadError
from app.core.config import Settings
from app.extractors.mangadex import MangaDexExtractor
from app.extractors.registry import Registry
from app.infrastructure.http_client import HttpClient

MID = "39e55355-dfb4-44e9-bd0b-df1fc3a0e33e"
CID = "575bf739-4c3b-4473-a011-74e70087385d"


def entity(identifier=CID, lang="pt-br", number="1", **extra):
    return dict(id=identifier, attributes=dict(chapter=number, translatedLanguage=lang, title="", pages=2, **extra),
                relationships=[dict(type="scanlation_group", attributes=dict(name="Grupo A")), dict(type="manga", id=MID)])


class Client:
    def __init__(self):
        self.calls = []
        self.images = []
        self.base = "https://uploads.mangadex.org/token-one"

    def register_api_images(self, urls):
        self.images.extend(urls)

    async def api_json(self, url):
        self.calls.append(url)
        path, query = urlsplit(url).path, parse_qs(urlsplit(url).query)
        if path.startswith("/at-home/"):
            assert query["forcePort443"] == ["true"]
            return dict(result="ok", baseUrl=self.base, chapter=dict(hash="digest", data=["1.png", "2.png"], dataSaver=["low.jpg"]))
        if path.startswith("/chapter/"):
            return dict(result="ok", data=entity())
        if path.endswith("/feed"):
            assert query["includeExternalUrl"] == ["0"]
            offset = int(query["offset"][0])
            items = ([entity(), entity(lang="en", identifier=str(UUID(int=2)))] if offset == 0 else
                     [entity(), entity(number="1.5", identifier=str(UUID(int=3)))])
            return dict(result="ok", data=items, total=4)
        return dict(result="ok", data=dict(attributes=dict(title={"ko-ro": "Romanized"}, altTitles=[{"pt-br": "Nome da obra"}],
                    description={"pt-br": "Sinopse"}), relationships=[dict(type="cover_art", attributes=dict(fileName="cover.jpg"))]))


async def test_metadata_title_languages_groups_pagination_and_versions():
    client = Client()
    extractor = MangaDexExtractor(client)
    manga = await extractor.get_manga_info(f"https://mangadex.org/title/{MID}/slug")
    assert manga.title == "Nome da obra" and manga.listing_complete
    assert manga.url == f"https://mangadex.org/title/{MID}"
    assert len(manga.chapters) == 3
    assert [c.language for c in manga.chapters].count("pt-br") == 2
    assert "Grupo A" in manga.chapters[0].title
    assert manga.cover in client.images
    assert len([url for url in client.calls if "/feed?" in url]) == 2


async def test_direct_chapter_uses_work_title_and_identity():
    manga = await MangaDexExtractor(Client()).get_manga_info(f"https://mangadex.org/chapter/{CID}")
    assert manga.title == "Nome da obra" and manga.url.endswith(MID)
    assert len(manga.chapters) == 1 and manga.chapters[0].url.endswith(CID)


async def test_original_page_order_and_stable_keys_across_server_rotation():
    client = Client()
    extractor = MangaDexExtractor(client)
    pages = await extractor.get_chapter_pages(f"https://mangadex.org/chapter/{CID}")
    assert pages.authoritative and pages.urls[0].endswith("/data/digest/1.png")
    assert not any("data-saver" in url for url in pages.urls)
    client.base = "https://uploads.mangadex.org/token-two"
    rotated = await extractor.get_chapter_pages(f"https://mangadex.org/chapter/{CID}")
    assert rotated.urls != pages.urls and rotated.cache_keys == pages.cache_keys


@pytest.mark.parametrize("base", ["https://127.0.0.1", "http://uploads.mangadex.org", "https://uploads.mangadex.org:444"])
async def test_reject_unsafe_page_server(base):
    client = Client()
    client.base = base
    with pytest.raises((SecurityError, ExtractionError)):
        await MangaDexExtractor(client).get_chapter_pages(f"https://mangadex.org/chapter/{CID}")


async def test_empty_or_interrupted_api_feed_is_explicit():
    client = Client()
    async def empty(url):
        return dict(result="ok", data=[], total=10)
    client.api_json = empty
    with pytest.raises(ExtractionError, match="interrompida"):
        await MangaDexExtractor(client).get_chapters(f"https://mangadex.org/title/{MID}")


def test_exact_domain_and_bad_id():
    assert isinstance(Registry(None).select(f"https://mangadex.org/title/{MID}"), MangaDexExtractor)
    assert not MangaDexExtractor(None).can_handle(f"https://mangadex.org.evil.org/title/{MID}")
    with pytest.raises(ExtractionError):
        MangaDexExtractor(None).resource("https://mangadex.org/title/invalid")


async def test_api_json_is_limited_to_documented_public_routes():
    client = HttpClient(Settings())
    calls = []
    async def request(url, limit, **kwargs):
        calls.append(kwargs)
        return b'{"result":"ok"}', "application/json"
    client._request = request
    assert await client.api_json(f"https://api.mangadex.org/manga/{MID}") == {"result": "ok"}
    assert calls == [dict(robots=False)]
    for url in (f"https://evil.org/manga/{MID}", "https://api.mangadex.org/auth/login", f"http://api.mangadex.org/manga/{MID}"):
        with pytest.raises(SecurityError):
            await client.api_json(url)


async def test_downloader_reuses_pages_when_at_home_server_rotates(setup_library, image_bytes):
    from app.services.download_manager import DownloadManager
    settings, db, library, mid, ids = setup_library
    db.execute("UPDATE chapters SET url=? WHERE id=?", (f"https://mangadex.org/chapter/{CID}", ids[0]))
    client = Client()
    downloads = []
    async def image(url, referer=""):
        downloads.append(url)
        return image_bytes
    client.image = image
    manager = DownloadManager(db, settings)
    manager.running = True
    async def run():
        task = db.tasks()[-1]
        db.execute("UPDATE tasks SET status='running' WHERE id=?", (task["id"],))
        await manager.download(task, client, Registry(client))
        assert db.tasks()[-1]["status"] == "complete"
    await run()
    assert len(downloads) == 2
    library.enqueue(ids)
    client.base = "https://uploads.mangadex.org/token-two"
    await run()
    assert len(downloads) == 2
    assert db.tasks()[-1]["skipped"] == 2
    assert db.chapters(mid)[0]["status"] == "verified"
