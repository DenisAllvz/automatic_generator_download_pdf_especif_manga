import re
import json
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup
from app.core.exceptions import ExtractionError
from app.core.security import validate_url
from app.infrastructure.filesystem import chapter_key
from app.models import Chapter, Manga, PageList
from app.extractors.titles import work_title


class HtmlExtractor:
    name = "HTML público"
    chapter_selector = ".wp-manga-chapter a, .chapter-list a, .chapters a, [data-chapter] a"
    image_selector = "img.wp-manga-chapter-img, img.chapter-image, .reading-content img, #reader img, .reader img"
    max_pages = 100

    def __init__(self, client):
        self.client = client
        self.listing_complete = False

    def can_handle(self, url: str) -> bool:
        return True

    @staticmethod
    def structured(soup):
        objects = []
        for tag in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(tag.string or tag.get_text())
            except (ValueError, TypeError):
                continue
            queue = data if isinstance(data, list) else [data]
            for item in queue:
                if isinstance(item, dict):
                    objects.extend(item.get("@graph", [item]))
        return [item for item in objects if isinstance(item, dict)]

    @staticmethod
    def image_url(tag, url: str) -> str:
        source = next((tag.get(k) for k in ("data-src", "data-lazy-src", "data-original", "src")
                       if tag.get(k) and not tag.get(k).startswith("data:")), "")
        srcset = tag.get("data-srcset") or tag.get("srcset")
        if srcset and not any(tag.get(k) for k in ("data-src", "data-lazy-src", "data-original")):
            candidates = []
            for item in srcset.split(","):
                bits = item.strip().split()
                if bits:
                    weight = float(re.sub(r"[^\d.]", "", bits[-1]) or 1) if len(bits) > 1 else 1
                    candidates.append((weight, bits[0]))
            if candidates:
                source = max(candidates)[1]
        return validate_url(urljoin(url, source.strip())) if source.strip() else ""

    async def get_manga_info(self, url: str) -> Manga:
        url = validate_url(url)
        soup = BeautifulSoup(await self.client.text(url), "html.parser")
        structured = next((o for o in self.structured(soup) if o.get("@type") in ("Book", "ComicSeries", "CreativeWorkSeries", "ComicIssue")), {})
        title = work_title(soup, url, structured)
        if not title:
            raise ExtractionError("Título indisponível; fonte incompatível ou página vazia.")
        desc = soup.select_one('meta[property="og:description"], meta[name="description"]')
        cover = soup.select_one('meta[property="og:image"]')
        chapters = await self.get_chapters(url)
        if not chapters:
            # Direct chapter URL: only accept recognized reader images.
            pages = self.parse_pages(soup, url)
            if not pages.urls:
                raise ExtractionError("Nenhum capítulo ou leitor reconhecido. A fonte pode exigir JavaScript, login ou um adaptador próprio.")
            chapters = [Chapter(title, url)]
        description = desc.get("content", "") if desc else structured.get("description", "")
        cover_url = cover.get("content", "") if cover else structured.get("image", "")
        if isinstance(cover_url, list):
            cover_url = cover_url[0] if cover_url else ""
        if isinstance(cover_url, dict):
            cover_url = cover_url.get("url", "")
        return Manga(str(title), url, str(description),
                     validate_url(urljoin(url, cover_url)) if isinstance(cover_url, str) and cover_url else "",
                     chapters, self.listing_complete)

    async def get_chapters(self, url: str) -> list[Chapter]:
        seen, chapters, pending = set(), {}, [url]
        origin = urlsplit(url).netloc
        max_pages = getattr(getattr(self.client, "settings", None), "max_listing_pages", self.max_pages)
        self.listing_complete = False
        while pending:
            if len(seen) >= max_pages:
                raise ExtractionError(f"Listagem excede {max_pages} páginas. Aumente o limite; nenhum resultado parcial será confirmado.")
            listing = pending.pop(0)
            if listing in seen:
                continue
            seen.add(listing)
            soup = BeautifulSoup(await self.client.text(listing), "html.parser")
            tags = soup.select(self.chapter_selector)
            if not tags:
                tags = [a for a in soup.select("a[href]") if re.search(r"(?:/capitulo[-/]|/cap[-/]|/chapter[-/])", a["href"], re.I)]
            for tag in tags:
                if not tag.get("href"):
                    continue
                chapter_url = validate_url(urljoin(listing, tag["href"]))
                if urlsplit(chapter_url).netloc != origin:
                    continue
                title = tag.get_text(" ", strip=True) or urlsplit(chapter_url).path.rstrip("/").split("/")[-1]
                chapters.setdefault(chapter_url, Chapter(title, chapter_url))
            for obj in self.structured(soup):
                parts = obj.get("hasPart", [])
                if isinstance(parts, dict):
                    parts = [parts]
                if not isinstance(parts, list):
                    continue
                for part in parts:
                    if not isinstance(part, dict) or part.get("@type") not in ("Chapter", "ComicIssue"):
                        continue
                    if not isinstance(part.get("url"), str):
                        continue
                    chapter_url = validate_url(urljoin(listing, part["url"]))
                    if urlsplit(chapter_url).netloc == origin:
                        chapters.setdefault(chapter_url, Chapter(str(part.get("name") or "Capítulo"), chapter_url))
            for link in soup.select('a[rel~="next"], .pagination a[href], .nav-links a[href], a.next[href]'):
                next_url = validate_url(urljoin(listing, link.get("href", "")))
                if urlsplit(next_url).netloc == origin and next_url not in seen and next_url not in pending:
                    pending.append(next_url)
        # Traversed all advertised HTML listing links; hidden AJAX cannot be inferred.
        return sorted(chapters.values(), key=lambda c: chapter_key(c.title))

    def parse_pages(self, soup, url: str) -> PageList:
        found, seen = [], set()
        for image in soup.select(self.image_selector):
            context = " ".join(image.get("class", [])) + " " + (image.get("alt") or "")
            if re.search(r"\b(advert|advertisement|banner|avatar|logo|icon)\b", context, re.I):
                continue
            src = self.image_url(image, url)
            if src and src not in seen:
                found.append(src)
                seen.add(src)
        return PageList(found, False)

    async def get_chapter_pages(self, url: str) -> PageList:
        soup = BeautifulSoup(await self.client.text(validate_url(url)), "html.parser")
        result = self.parse_pages(soup, url)
        if not result.urls:
            raise ExtractionError("Lista de páginas indisponível; confira o acesso e o adaptador.")
        return result
