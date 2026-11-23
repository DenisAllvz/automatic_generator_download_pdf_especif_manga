"""MangaDex public API v5: metadata, paginated feeds and original AtHome pages."""
import re
from uuid import UUID
from urllib.parse import urlsplit, urlencode, quote
from app.core.security import validate_url
from app.core.exceptions import ExtractionError
from app.infrastructure.filesystem import chapter_key
from app.models import Manga, Chapter, PageList

API = "https://api.mangadex.org"
SITE = "https://mangadex.org"


class MangaDexExtractor:
    name = "MangaDex — API oficial"

    def __init__(self, client):
        self.client = client
        self.listing_complete = False

    def can_handle(self, url):
        return urlsplit(url).hostname in ("mangadex.org", "www.mangadex.org")

    def resource(self, url):
        parsed = urlsplit(validate_url(url))
        if not self.can_handle(url):
            raise ExtractionError("Use uma URL do MangaDex.")
        match = re.match(r"^/(title|chapter)/([^/]+)(?:/.*)?$", parsed.path)
        if not match:
            raise ExtractionError("Use a URL /title/ID ou /chapter/ID do MangaDex.")
        try:
            identifier = str(UUID(match[2]))
        except ValueError as exc:
            raise ExtractionError("Identificador MangaDex inválido.") from exc
        return match[1], identifier

    async def request(self, route, params=()):
        result = await self.client.api_json(API + route + ("?" + urlencode(params) if params else ""))
        if result.get("result") != "ok":
            raise ExtractionError("O MangaDex não disponibilizou este recurso.")
        return result

    @staticmethod
    def localized(attributes, field):
        values = attributes.get(field, {})
        if not isinstance(values, dict):
            return ""
        if field == "title":
            # Prefer a Portuguese alternate title when the primary is romanized.
            for lang in ("pt-br", "pt", "en"):
                if values.get(lang):
                    return values[lang]
                for alt in attributes.get("altTitles", []):
                    if isinstance(alt, dict) and alt.get(lang):
                        return alt[lang]
        return next((values[lang] for lang in ("pt-br", "pt", "en", "ja-ro", "ko-ro", "zh-ro")
                     if isinstance(values.get(lang), str) and values[lang]),
                    next((v for v in values.values() if isinstance(v, str) and v), ""))

    @staticmethod
    def chapter(entity):
        if not isinstance(entity, dict) or not isinstance(entity.get("attributes"), dict):
            raise ExtractionError("Metadados de capítulo MangaDex inválidos.")
        attrs = entity.get("attributes", {})
        try:
            cid = str(UUID(entity["id"]))
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            raise ExtractionError("Identificador de capítulo MangaDex inválido.") from exc
        language = attrs.get("translatedLanguage", "?")
        number = attrs.get("chapter")
        label = f"Capítulo {number}" if number is not None else "Extra"
        if attrs.get("title"):
            label += " - " + attrs["title"]
        groups = [r.get("attributes", {}).get("name", "") for r in entity.get("relationships", [])
                  if r.get("type") == "scanlation_group"]
        label += f" [{language.upper()}" + (" · " + ", ".join(g for g in groups if g) if any(groups) else "") + "]"
        return Chapter(label, f"{SITE}/chapter/{cid}", language)

    async def get_manga_info(self, url):
        kind, identifier = self.resource(url)
        direct = None
        if kind == "chapter":
            entity = (await self.request(f"/chapter/{identifier}", [("includes[]", "scanlation_group")])).get("data", {})
            direct = self.chapter(entity)
            relationship = next((r for r in entity.get("relationships", []) if r.get("type") == "manga"), None)
            if not relationship:
                raise ExtractionError("O capítulo não identifica sua obra no MangaDex.")
            identifier = str(UUID(relationship["id"]))
        result = await self.request(f"/manga/{identifier}", [("includes[]", "cover_art")])
        entity = result.get("data", {})
        if not isinstance(entity, dict) or not isinstance(entity.get("attributes"), dict):
            raise ExtractionError("Metadados da obra MangaDex inválidos.")
        attrs = entity.get("attributes", {})
        title = self.localized(attrs, "title")
        if not title:
            raise ExtractionError("Título da obra indisponível no MangaDex.")
        cover = ""
        art = next((r for r in entity.get("relationships", []) if r.get("type") == "cover_art"), {})
        filename = art.get("attributes", {}).get("fileName")
        if isinstance(filename, str) and filename:
            cover = f"https://uploads.mangadex.org/covers/{identifier}/{quote(filename, safe='')}.256.jpg"
            self.client.register_api_images([cover])
        chapters = [direct] if direct else await self.get_chapters(f"{SITE}/title/{identifier}")
        description = "Fonte: MangaDex (mangadex.org).\n" + self.localized(attrs, "description")
        return Manga(title, f"{SITE}/title/{identifier}", description, cover, chapters, self.listing_complete)

    async def get_chapters(self, url):
        kind, identifier = self.resource(url)
        if kind != "title":
            raise ExtractionError("Use a URL da obra para listar seus capítulos.")
        chapters, offset = {}, 0
        max_pages = getattr(getattr(self.client, "settings", None), "max_listing_pages", 100)
        self.listing_complete = False
        for _ in range(max_pages):
            if offset >= 10000:
                raise ExtractionError("A listagem MangaDex excede 10.000 registros; nenhuma lista parcial foi confirmada.")
            params = [("limit", min(500, 10000-offset)), ("offset", offset), ("order[chapter]", "asc"),
                      ("includes[]", "scanlation_group"), ("includeExternalUrl", "0"),
                      ("includeEmptyPages", "0"), ("includeFuturePublishAt", "0"), ("includeUnavailable", "0")]
            response = await self.request(f"/manga/{identifier}/feed", params)
            entities, total = response.get("data"), response.get("total")
            if not isinstance(entities, list) or type(total) is not int or total < 0:
                raise ExtractionError("Listagem MangaDex inválida.")
            if not entities and offset < total:
                raise ExtractionError("Listagem MangaDex interrompida; tente novamente.")
            for entity in entities:
                if not isinstance(entity, dict) or not isinstance(entity.get("attributes"), dict):
                    raise ExtractionError("Listagem MangaDex contém capítulo inválido.")
                attrs = entity.get("attributes", {})
                if attrs.get("externalUrl") or attrs.get("isUnavailable") or not attrs.get("pages"):
                    continue
                chapter = self.chapter(entity)
                chapters.setdefault(chapter.url, chapter)
            offset += len(entities)
            if offset >= total:
                self.listing_complete = True
                return sorted(chapters.values(), key=lambda c: chapter_key(c.title))
        raise ExtractionError("Listagem MangaDex excede o limite de páginas configurado.")

    async def get_chapter_pages(self, url):
        kind, identifier = self.resource(url)
        if kind != "chapter":
            raise ExtractionError("Use a URL de um capítulo MangaDex.")
        response = await self.request(f"/at-home/server/{identifier}", [("forcePort443", "true")])
        chapter = response.get("chapter", {})
        if not isinstance(chapter, dict):
            raise ExtractionError("Manifesto MangaDex inválido.")
        base = response.get("baseUrl", "")
        files, digest = chapter.get("data"), chapter.get("hash")
        if not isinstance(base, str) or not base.startswith("https://") or not isinstance(digest, str) or not digest:
            raise ExtractionError("Servidor de páginas MangaDex inválido.")
        if not isinstance(files, list) or not files or not all(isinstance(f, str) and f for f in files):
            raise ExtractionError("O MangaDex não disponibilizou páginas para este capítulo.")
        urls = [validate_url(f"{base.rstrip('/')}/data/{quote(digest, safe='')}/{quote(f, safe='')}") for f in files]
        if len(urls) != len(set(urls)):
            raise ExtractionError("Manifesto MangaDex contém páginas duplicadas.")
        self.client.register_api_images(urls)
        return PageList(urls, True, [f"mangadex:{identifier}:{digest}:{f}" for f in files])
