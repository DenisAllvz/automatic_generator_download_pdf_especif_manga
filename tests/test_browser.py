import pytest
from app.core.config import Settings
from app.core.exceptions import ExtractionError
from app.infrastructure.browser_renderer import BrowserRenderer
from app.extractors.generic import HtmlExtractor


class BrowserSource:
    settings = Settings()
    def __init__(self, unsafe=False):
        self.urls = []
        self.unsafe = unsafe

    async def _request(self, url, limit):
        self.urls.append(url)
        if self.unsafe:
            body = '<h1>A</h1><script>fetch("http://127.0.0.1/private").catch(()=>{});</script>'
        else:
            body = '''<h1>Obra JS</h1><script>
                document.body.insertAdjacentHTML('beforeend', '<div id="reader"><img data-src="https://example.org/page.png"></div>');
                </script>'''
        return body.encode(), "text/html"


async def test_optional_browser_js_without_external_network():
    pytest.importorskip("playwright.async_api")
    source = BrowserSource()
    html = await BrowserRenderer(source).text("https://example.org/chapter-1")
    from bs4 import BeautifulSoup
    pages = HtmlExtractor(source).parse_pages(BeautifulSoup(html, "html.parser"), "https://example.org/chapter-1")
    assert pages.urls == ["https://example.org/page.png"]
    assert source.urls == ["https://example.org/chapter-1"]


async def test_browser_private_fetch_blocked():
    pytest.importorskip("playwright.async_api")
    source = BrowserSource(unsafe=True)
    with pytest.raises(ExtractionError, match="recursos negados"):
        await BrowserRenderer(source).text("https://example.org/chapter-1")
    assert source.urls == ["https://example.org/chapter-1"]
