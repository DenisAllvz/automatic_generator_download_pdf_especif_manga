import asyncio
import json
from pathlib import Path
from bs4 import BeautifulSoup
from app.extractors.generic import HtmlExtractor
from app.services.integrity import diagnose
from app.infrastructure.http_client import HttpClient
from app.core.config import Settings


async def test_structured_chapters_metadata_and_malformed_json():
    data = {"@type": "ComicSeries", "name": "Obra JSON", "description": "Teste", "hasPart": [
        {"@type": "Chapter", "name": "Chapter 2", "url": "/chapter-2"},
        {"@type": "Chapter", "name": "Chapter 1", "url": "/chapter-1"}]}
    html = '<script type="application/ld+json">broken</script><script type="application/ld+json">' + json.dumps(data) + '</script>'
    class Source:
        async def text(self, url):
            return html
    result = await HtmlExtractor(Source()).get_manga_info("https://example.org/")
    assert result.title == "Obra JSON" and result.description == "Teste"
    assert [c.title for c in result.chapters] == ["Chapter 1", "Chapter 2"]


def test_malicious_manifest_path_does_not_read_outside(tmp_path):
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"secret")
    folder = tmp_path / "chapter"
    folder.mkdir()
    (folder / "manifest.json").write_text(json.dumps({"expected":1, "pages":[{"file":"../secret.png"}]}))
    result = diagnose(folder)
    assert result["status"] == "incomplete" and result["valid_pages"] == 0
    assert outside.read_bytes() == b"secret"


async def test_domain_crawl_delay_staggers_requests():
    client = HttpClient(Settings())
    started = asyncio.get_running_loop().time()
    await asyncio.gather(client._pace("example.org", .05), client._pace("example.org", .05))
    assert asyncio.get_running_loop().time() - started >= .04
