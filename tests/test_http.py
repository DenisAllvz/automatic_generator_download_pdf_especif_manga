import asyncio
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
import aiohttp
from aiohttp import web
import pytest
from app.core.config import Settings
from app.core.exceptions import DownloadError, SecurityError
from app.infrastructure.http_client import HttpClient


@pytest.fixture
async def server(monkeypatch):
    state = {"calls": 0, "mode": "ok", "robots": "User-agent: *\nAllow: /"}
    async def handler(request):
        if request.path == "/robots.txt":
            return web.Response(text=state["robots"], status=state.get("robots_status", 200))
        state["calls"] += 1
        if state["mode"] == "429" and state["calls"] == 1:
            return web.Response(status=429, headers={"Retry-After": "0"})
        if state["mode"] in ("403", "404", "500"):
            return web.Response(status=int(state["mode"]))
        if state["mode"] == "timeout":
            await asyncio.sleep(.2)
        if state["mode"] == "redirect":
            raise web.HTTPFound("http://127.0.0.1/private")
        if state["mode"] == "too_large":
            return web.Response(body=b"x" * 200)
        return web.Response(text="<h1>Public</h1>", content_type="text/html")
    app = web.Application()
    app.router.add_get("/{tail:.*}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    root = f"http://127.0.0.1:{port}"
    from app.infrastructure import http_client
    from app.core.security import validate_url
    # Only this fixture can access the simulated loopback server. Production has no flag.
    monkeypatch.setattr(http_client, "validate_url", lambda url: url if url.startswith(root + "/") else validate_url(url))
    class TestHttpClient(HttpClient):
        async def __aenter__(self):
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=.08))
            return self
    settings = Settings(retries=2)
    try:
        async with TestHttpClient(settings) as client:
            yield root, client, state
    finally:
        await runner.cleanup()


async def test_http_success_and_robots(server):
    root, client, state = server
    assert "Public" in await client.text(root + "/chapter")
    assert state["calls"] == 1


async def test_429_retry_after(server):
    root, client, state = server
    state["mode"] = "429"
    assert "Public" in await client.text(root + "/chapter")
    assert state["calls"] == 2


@pytest.mark.parametrize("mode,count", [("404", 1), ("500", 2), ("timeout", 2)])
async def test_http_failure_limits(server, mode, count):
    root, client, state = server
    state["mode"] = mode
    with pytest.raises(DownloadError) as exc:
        await client.text(root + "/chapter")
    assert state["calls"] == count
    assert exc.value.attempts == count


async def test_redirect_private_rejected(server):
    root, client, state = server
    state["mode"] = "redirect"
    with pytest.raises(SecurityError):
        await client.text(root + "/chapter")


async def test_robots_denied(server):
    root, client, state = server
    state["robots"] = "User-agent: *\nDisallow: /chapter"
    with pytest.raises(SecurityError):
        await client.text(root + "/chapter")
    assert state["calls"] == 0


@pytest.mark.parametrize("status", [401, 403, 404, 410])
async def test_unavailable_robots_does_not_block_public_resources(server, status):
    root, client, state = server
    state["robots_status"] = status
    assert "Public" in await client.text(root + "/chapter")
    assert state["calls"] == 1


async def test_image_denial_still_fails_when_robots_unavailable(server):
    root, client, state = server
    state.update(robots_status=403, mode="403")
    with pytest.raises(DownloadError) as exc:
        await client.image(root + "/page.jpg")
    assert exc.value.status == 403 and state["calls"] == 1


@pytest.mark.parametrize("status", [429, 503, None])
async def test_robots_rate_limit_or_unreachable_keeps_access_blocked(status):
    client = HttpClient(Settings())
    async def unavailable(*args, **kwargs):
        raise DownloadError("Indisponível", status, 1)
    client._request = unavailable
    with pytest.raises(DownloadError, match="robots.txt"):
        await client._robots_allowed("https://example.org/page.jpg")
    assert not client.robots


async def test_wrong_mime_and_size(server):
    root, client, state = server
    with pytest.raises(DownloadError, match="não é imagem"):
        await client.image(root + "/chapter")
    state["mode"] = "too_large"
    with pytest.raises(DownloadError, match="tamanho"):
        await client._request(root + "/chapter", 50)


def test_retry_after_date():
    date = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=5))
    assert 3 <= HttpClient.retry_after(date) <= 5
