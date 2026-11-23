"""FlorManga/Madara: chapter navigation is never listing pagination."""
import re
from urllib.parse import urlsplit, urljoin
from bs4 import BeautifulSoup
from app.core.exceptions import ExtractionError
from app.core.security import validate_url
from app.extractors.generic import HtmlExtractor
from app.extractors.titles import work_title
from app.infrastructure.filesystem import chapter_key
from app.models import Manga, Chapter


class FlorMangaExtractor(HtmlExtractor):
    name = "FlorManga — HTML Madara"
    image_selector = ".reading-content img.wp-manga-chapter-img"

    def can_handle(self, url):
        host = urlsplit(url).hostname or ""
        return host == "flormanga.com" or host.endswith(".flormanga.com")

    def location(self, url):
        url = validate_url(url)
        parsed = urlsplit(url)
        match = re.fullmatch(r"/manga/([^/]+)(?:/((?:capitulo|chapter)[^/]*))?/?", parsed.path, re.I)
        if not self.can_handle(url) or not match:
            raise ExtractionError("Use a URL de uma obra ou capítulo do FlorManga.")
        return url, f"{parsed.scheme}://{parsed.netloc}/manga/{match[1]}/", bool(match[2])

    async def get_manga_info(self, url):
        url, work_url, direct = self.location(url)
        soup = BeautifulSoup(await self.client.text(url), "html.parser")
        structured = next((o for o in self.structured(soup) if o.get("@type") in ("Book", "ComicSeries", "CreativeWorkSeries")), {})
        if direct:
            breadcrumb = next((a for a in soup.select(".breadcrumb a[href]")
                               if urljoin(url, a["href"]).rstrip("/") == work_url.rstrip("/")), None)
            if breadcrumb:
                title = breadcrumb.get_text(" ", strip=True)
            else:
                og = soup.select_one('meta[property="og:title"]')
                heading = soup.select_one("#chapter-heading")
                raw = og.get("content", "") if og else ""
                chapter_name = heading.get_text(" ", strip=True) if heading else ""
                title = re.split(r"\s+-\s+" + re.escape(chapter_name), re.sub(r"\s+", " ", raw), maxsplit=1)[0] if chapter_name else ""
            if not title:
                raise ExtractionError("Nome da obra indisponível no capítulo FlorManga.")
            chapters = self.direct_chapter(soup, url)
        else:
            title = work_title(soup, url, structured)
            chapters = self.listed_chapters(soup, work_url)
        if not title or not chapters:
            raise ExtractionError("Título ou lista de capítulos FlorManga indisponível. Confira a URL e o acesso à obra.")
        desc = soup.select_one('meta[property="og:description"], meta[name="description"]')
        cover = soup.select_one('meta[property="og:image"]')
        return Manga(title, work_url, desc.get("content", "") if desc else "",
                     validate_url(urljoin(url, cover["content"])) if cover and cover.get("content") else "",
                     chapters, False)

    def direct_chapter(self, soup, url):
        if not self.parse_pages(soup, url).urls:
            raise ExtractionError("As páginas deste capítulo FlorManga não estão disponíveis.")
        heading = soup.select_one("#chapter-heading, h1")
        title = heading.get_text(" ", strip=True) if heading else urlsplit(url).path.rstrip("/").split("/")[-1]
        return [Chapter(title, url)]

    def listed_chapters(self, soup, work_url):
        found = {}
        origin, prefix = urlsplit(work_url).netloc, urlsplit(work_url).path
        for tag in soup.select(".wp-manga-chapter a[href], .chapter-list a[href], .single-chapter-select option[data-redirect]"):
            href = tag.get("data-redirect") or tag.get("href")
            link = validate_url(urljoin(work_url, href))
            parsed = urlsplit(link)
            suffix = parsed.path.removeprefix(prefix).strip("/")
            if parsed.netloc == origin and parsed.path.startswith(prefix) and re.fullmatch(r"(?:capitulo|chapter)[^/]+", suffix, re.I):
                found.setdefault(link, Chapter(tag.get_text(" ", strip=True) or suffix, link))
        return sorted(found.values(), key=lambda c: chapter_key(c.title))

    async def get_chapters(self, url):
        url, work_url, direct = self.location(url)
        soup = BeautifulSoup(await self.client.text(url), "html.parser")
        return self.direct_chapter(soup, url) if direct else self.listed_chapters(soup, work_url)
