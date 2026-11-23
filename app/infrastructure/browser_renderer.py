"""Optional renderer: no direct browser network; all requests use guarded HTTP."""
import asyncio
import sys
from app.core.exceptions import ExtractionError, MangaError
from app.core.security import validate_url


class BrowserRenderer:
    def __init__(self, client):
        self.client = client
        self.settings = client.settings

    async def text(self, url: str) -> str:
        if getattr(sys, "frozen", False):
            raise ExtractionError("Este pacote não inclui Chromium. Use a instalação Python com o extra browser ou um adaptador HTML/API autorizado.")
        try:
            from playwright.async_api import async_playwright, Error as BrowserError
        except ImportError as exc:
            raise ExtractionError("Instale o extra browser e execute python -m playwright install chromium.") from exc
        url = validate_url(url)
        blocked = []
        async with async_playwright() as automation:
            try:
                browser = await automation.chromium.launch(headless=True, chromium_sandbox=True,
                    proxy={"server": "http://127.0.0.1:9"},
                    args=["--proxy-bypass-list=<-loopback>", "--force-webrtc-ip-handling-policy=disable_non_proxied_udp", "--disable-quic"])
            except BrowserError as exc:
                raise ExtractionError("Chromium indisponível. Instale-o com python -m playwright install chromium.") from exc
            try:
                context = await browser.new_context(permissions=[], accept_downloads=False,
                    service_workers="block", java_script_enabled=True)
                page = await context.new_page()
                semaphore = asyncio.Semaphore(self.settings.per_domain)
                count = 0
                async def route(request_route):
                    nonlocal count
                    request = request_route.request
                    try:
                        validate_url(request.url)
                        count += 1
                        if count > 100 or request.method != "GET" or request.resource_type not in (
                                "document", "script", "stylesheet", "image", "xhr", "fetch", "font"):
                            blocked.append("ResourceLimitOrUnsupportedMethod")
                            await request_route.abort()
                            return
                        async with semaphore:
                            limit = self.settings.max_image_mb if request.resource_type == "image" else self.settings.max_html_mb
                            body, mime = await self.client._request(request.url, limit * 1024**2)
                        await request_route.fulfill(status=200, body=body, content_type=mime or "application/octet-stream")
                    except (MangaError, OSError) as exc:
                        blocked.append(type(exc).__name__)
                        await request_route.abort()
                async def websocket(socket):
                    await socket.close()
                await context.route("**/*", route)
                await context.route_web_socket("**/*", websocket)
                try:
                    async with asyncio.timeout(self.settings.timeout):
                        await page.goto(url, wait_until="domcontentloaded", timeout=self.settings.timeout * 1000)
                        # Bounded scroll preserves the original lazy-load capability.
                        for _ in range(3):
                            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            await asyncio.sleep(.3)
                        html = await page.content()
                except (BrowserError, TimeoutError) as exc:
                    raise ExtractionError("Renderização interrompida ou negada; nenhum bloqueio será contornado.") from exc
                if len(html.encode("utf-8")) > self.settings.max_html_mb * 1024**2:
                    raise ExtractionError("HTML renderizado excede o limite seguro.")
                if blocked:
                    # Denied subresources can mean an incomplete chapter/listing.
                    raise ExtractionError("A renderização teve recursos negados ou inacessíveis. Verifique autorização e o adaptador.")
                return html
            finally:
                await browser.close()

    async def image(self, url: str, referer: str = ""):
        return await self.client.image(url, referer)
