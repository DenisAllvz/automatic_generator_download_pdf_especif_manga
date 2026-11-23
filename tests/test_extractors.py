import pytest
from app.extractors.generic import HtmlExtractor
from app.extractors.registry import Registry, BorutoExtractor, MangaLivreExtractor
from app.core.exceptions import ExtractionError


class FakeClient:
    def __init__(self, pages):
        self.pages = pages
        self.visited = []

    async def text(self, url):
        self.visited.append(url)
        return self.pages[url]


async def test_250_chapters_five_pages_unique_and_ordered():
    pages = {}
    for number in range(1, 6):
        chapters = "".join(f'<li class="wp-manga-chapter"><a href="/chapter-{i}">Capítulo {i}</a></li>' for i in range((number-1)*50+1, number*50+1))
        duplicate = '<li class="wp-manga-chapter"><a href="/chapter-1">Capítulo 1</a></li>'
        next_page = f'<a rel="next" href="/manga?p={number+1}">Próxima</a>' if number < 5 else ""
        pages[f"https://example.org/manga?p={number}"] = f"<h1>Obra</h1>{chapters}{duplicate}{next_page}"
    client = FakeClient(pages)
    result = await HtmlExtractor(client).get_chapters("https://example.org/manga?p=1")
    assert len(result) == 250
    assert result[0].title == "Capítulo 1" and result[-1].title == "Capítulo 250"
    assert len(client.visited) == 5


async def test_lazy_srcset_filtered_and_deduplicated():
    html = '''<h1>Chapter 1</h1><img src="/logo.png"><div id="reader">
        <img data-src=" /page.png " src="placeholder.gif"><img srcset="/small.png 100w, /large.png 900w">
        <img src="/page.png"><img class="banner" src="/ad.png"></div>'''
    client = FakeClient({"https://example.org/chapter-1": html})
    result = await HtmlExtractor(client).get_chapter_pages("https://example.org/chapter-1")
    assert result.urls == ["https://example.org/page.png", "https://example.org/large.png"]
    assert not result.authoritative
    manga = await HtmlExtractor(client).get_manga_info("https://example.org/chapter-1")
    assert len(manga.chapters) == 1


@pytest.mark.parametrize("html", ["", "<html><h1>Site</h1><img src='/banner.png'></html>", "<broken"])
async def test_incompatible_empty_malformed(html):
    with pytest.raises(ExtractionError):
        await HtmlExtractor(FakeClient({"https://example.org/": html})).get_manga_info("https://example.org/")


def test_registry_exact_domains():
    registry = Registry(None)
    assert isinstance(registry.select("https://leitor.borutoexplorer.com.br/manga/a"), BorutoExtractor)
    assert isinstance(registry.select("https://mangalivre.net/a"), MangaLivreExtractor)
    assert type(registry.select("https://borutoexplorer.com.br.evil.org/a")) is HtmlExtractor


async def test_variants_and_decimals_not_collapsed():
    html = '<h1>A</h1><div class="chapters">' + "".join(f'<a href="/chapter-{i}">{title}</a>' for i, title in enumerate(["Capítulo 1.5", "Capítulo 1 revisado", "Capítulo 1", "Extra", "Prólogo"])) + "</div>"
    result = await HtmlExtractor(FakeClient({"https://example.org/": html})).get_chapters("https://example.org/")
    assert len(result) == 5 and result[0].title == "Prólogo"


@pytest.mark.parametrize("title_markup", [
    '<h1 class="site-title">Manga Livre</h1><h1 class="manga-title">Vagabond</h1>',
    '<header><h1>Manga Livre</h1></header><h1>Vagabond</h1>',
    '<h1 class="site-title">Manga Livre</h1><meta property="og:title" content="Vagabond - Manga Livre">',
    '<h1>Manga Livre</h1><script type="application/ld+json">{"@type":"ComicSeries","name":"Vagabond"}</script>',
])
async def test_work_title_instead_of_site_brand(title_markup):
    html = '<meta property="og:site_name" content="Manga Livre">' + title_markup + '<div class="chapters"><a href="/chapter-1">Capítulo 1</a></div>'
    url = "https://mangalivre.blog/manga/vagabond/"
    manga = await HtmlExtractor(FakeClient({url: html})).get_manga_info(url)
    assert manga.title == "Vagabond"
