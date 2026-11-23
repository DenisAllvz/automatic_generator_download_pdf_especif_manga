import pytest
from app.extractors.flormanga import FlorMangaExtractor
from app.extractors.registry import Registry
from app.core.exceptions import ExtractionError, SecurityError

WORK = "https://kk.flormanga.com/manga/obra/"
CHAPTER = WORK + "capitulo-1/"


class Client:
    def __init__(self, html):
        self.html, self.calls = html, []
    async def text(self, url):
        self.calls.append(url)
        return self.html


async def test_direct_chapter_has_work_name_and_never_follows_next():
    html = f'''<meta property="og:title" content="Nome da obra - Capítulo 1 - KK Flor">
        <ol class="breadcrumb"><a href="{WORK}">Nome da obra</a></ol>
        <h1 id="chapter-heading">Capítulo 1</h1>
        <div class="nav-links"><a rel="next" href="{WORK}capitulo-2/">Next</a></div>
        <select class="single-chapter-select"><option data-redirect="{WORK}capitulo-2/">Capítulo 2</option></select>
        <div class="reading-content"><img class="wp-manga-chapter-img" data-src="https://cdn.example.org/1.jpg"></div>
        <img class="wp-manga-chapter-img" src="https://cdn.example.org/banner.jpg">'''
    client = Client(html)
    extractor = FlorMangaExtractor(client)
    manga = await extractor.get_manga_info(CHAPTER)
    assert manga.title == "Nome da obra" and manga.url == WORK
    assert len(manga.chapters) == 1 and manga.chapters[0].url == CHAPTER
    assert client.calls == [CHAPTER]
    pages = await extractor.get_chapter_pages(CHAPTER)
    assert pages.urls == ["https://cdn.example.org/1.jpg"] and not pages.authoritative


async def test_chapter_title_fallback_without_breadcrumb():
    client = Client('''<meta property="og:title" content="Nome da obra - Capítulo 1 - KK Flor">
        <h1 id="chapter-heading">Capítulo 1</h1>
        <div class="reading-content"><img class="wp-manga-chapter-img" src="https://cdn.example.org/1.jpg"></div>''')
    assert (await FlorMangaExtractor(client).get_manga_info(CHAPTER)).title == "Nome da obra"


async def test_work_lists_select_options_and_links_without_navigation_requests():
    client = Client(f'''<h1 class="entry-title">Nome da obra</h1>
        <div class="wp-manga-chapter"><a href="{CHAPTER}">Capítulo 1</a></div>
        <select class="single-chapter-select">
          <option data-redirect="{WORK}capitulo-2/">Capítulo 2</option>
          <option data-redirect="{CHAPTER}">Capítulo 1</option>
          <option data-redirect="https://evil.org/manga/obra/capitulo-3/">Outro site</option>
        </select><a rel="next" href="{WORK}capitulo-99/">Next</a>''')
    manga = await FlorMangaExtractor(client).get_manga_info(WORK)
    assert [c.title for c in manga.chapters] == ["Capítulo 1", "Capítulo 2"]
    assert client.calls == [WORK]


async def test_empty_chapter_rejected():
    with pytest.raises(ExtractionError):
        await FlorMangaExtractor(Client('<h1 id="chapter-heading">Capítulo 1</h1>')).get_manga_info(CHAPTER)


def test_domain_registry_and_unsupported_paths():
    assert isinstance(Registry(None).select(CHAPTER), FlorMangaExtractor)
    assert not FlorMangaExtractor(None).can_handle("https://flormanga.com.evil.org/manga/obra/")
    with pytest.raises(ExtractionError):
        FlorMangaExtractor(None).location("https://kk.flormanga.com/login/")
