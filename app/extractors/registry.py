from urllib.parse import urlsplit
from app.core.security import validate_url
from app.extractors.generic import HtmlExtractor
from app.extractors.mangadex import MangaDexExtractor
from app.extractors.flormanga import FlorMangaExtractor
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from app.models import Manga, Chapter
from app.core.exceptions import ExtractionError
from app.extractors.titles import work_title, clean_chapter_title


class BorutoExtractor(HtmlExtractor):
    name = "Boruto Explorer — seletores legados"
    chapter_selector = "li.wp-manga-chapter a"
    image_selector = "img.wp-manga-chapter-img"

    def can_handle(self, url: str) -> bool:
        host = urlsplit(url).hostname or ""
        return host == "borutoexplorer.com.br" or host.endswith(".borutoexplorer.com.br")


class MangaLivreExtractor(HtmlExtractor):
    name = "MangaLivre"
    chapter_selector = '.chapter-item a.chapter-link, .wp-manga-chapter a, .chapter-list a:not(.read-button)'
    image_selector = HtmlExtractor.image_selector

    def can_handle(self, url: str) -> bool:
        host = urlsplit(url).hostname or ""
        return host in ("mangalivre.net", "mangalivre.com", "mangalivre.blog") or host.endswith((".mangalivre.net", ".mangalivre.com", ".mangalivre.blog"))

    async def get_chapters(self, url):
        chapters = await super().get_chapters(url)
        return [Chapter(clean_chapter_title(c.title), c.url, c.language) for c in chapters]

    async def get_manga_info(self, url):
        if not urlsplit(url).path.startswith('/capitulo/'):
            return await super().get_manga_info(url)
        soup = BeautifulSoup(await self.client.text(url), 'html.parser')
        if not self.parse_pages(soup, url).urls:
            raise ExtractionError('As páginas do capítulo MangaLivre não estão disponíveis.')
        work_url = next((urljoin(url, a['href']) for a in soup.select('a[href]')
                         if urlsplit(urljoin(url, a['href'])).netloc == urlsplit(url).netloc
                         and re.fullmatch(r'/manga/[^/]+/?', urlsplit(urljoin(url, a['href'])).path)
                         and a.find_parent(class_=re.compile('breadcrumb|chapter|reader', re.I))), '')
        if not work_url:
            raise ExtractionError('Não foi possível identificar a obra. Use o link da página da obra no MangaLivre.')
        work_soup = BeautifulSoup(await self.client.text(work_url), 'html.parser')
        title = work_title(work_soup, work_url, {})
        heading = soup.select_one('.chapter-title, #chapter-heading, h1:not(.site-title)')
        raw = heading.get_text(' ', strip=True) if heading else urlsplit(url).path.split('/')[-2]
        raw = re.sub(r'^' + re.escape(title) + r'\s*[/|:–—-]\s*', '', raw, flags=re.I)
        chapter_title = clean_chapter_title(raw)
        return Manga(title, work_url, chapters=[Chapter(chapter_title, url)])


class Registry:
    def __init__(self, client, adapters=None):
        self.adapters = [factory(client) for factory in (adapters or [MangaDexExtractor, FlorMangaExtractor, BorutoExtractor, MangaLivreExtractor, HtmlExtractor])]

    def select(self, url: str):
        url = validate_url(url)
        return next(adapter for adapter in self.adapters if adapter.can_handle(url))
