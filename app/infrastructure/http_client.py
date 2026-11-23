import asyncio
import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import aiohttp
from app.core.config import Settings
from app.core.exceptions import DownloadError, SecurityError
from app.core.security import PublicResolver, validate_url


class HttpClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.session: aiohttp.ClientSession | None = None
        self.robots: dict[str, RobotFileParser | None] = {}
        self.gates: dict[str, asyncio.Semaphore] = {}
        self.cooldowns: dict[str, float] = {}
        self.pace_locks: dict[str, asyncio.Lock] = {}
        self.last_access: dict[str, float] = {}
        self.api_images: set[str] = set()

    async def _pace(self, host: str, delay: float):
        if not delay:
            return
        lock = self.pace_locks.setdefault(host, asyncio.Lock())
        async with lock:
            now = asyncio.get_running_loop().time()
            wait = self.last_access.get(host, now-delay) + delay - now
            if wait > 0:
                await asyncio.sleep(wait)
            self.last_access[host] = asyncio.get_running_loop().time()

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=8, limit_per_host=self.settings.per_domain,
                                           resolver=PublicResolver(), use_dns_cache=False),
            timeout=aiohttp.ClientTimeout(total=self.settings.timeout), trust_env=False,
            headers={"User-Agent": "MangaManager/2.0 (authorized personal library)"})
        return self

    async def __aexit__(self, *args):
        await self.session.close()

    @staticmethod
    def retry_after(value: str) -> float:
        try:
            return max(0, float(value))
        except ValueError:
            try:
                return max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
            except (ValueError, TypeError):
                return 1

    async def _robots_allowed(self, url: str):
        p = urlsplit(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin not in self.robots:
            try:
                data, _ = await self._request(origin + "/robots.txt", self.settings.max_html_mb * 1024**2, robots=False)
            except DownloadError as exc:
                # RFC 9309 §2.3.1.3: 4xx means robots.txt is unavailable,
                # not a Disallow rule. Keep rate limits and server/network
                # failures blocking; HTTP denials on actual resources still fail.
                if exc.status is None or not 400 <= exc.status < 500 or exc.status == 429:
                    raise DownloadError("Não foi possível consultar as permissões em robots.txt.", exc.status, exc.attempts) from exc
                self.robots[origin] = None
            else:
                robot = RobotFileParser()
                robot.parse(data.decode("utf-8", errors="replace").splitlines())
                self.robots[origin] = robot
        robot = self.robots[origin]
        if robot:
            if not robot.can_fetch("MangaManager", url):
                raise SecurityError("A fonte não permite este acesso em robots.txt.")
            delay = robot.crawl_delay("MangaManager") or robot.crawl_delay("*") or 0
            return delay
        return 0

    async def _request(self, url: str, limit: int, referer: str = "", robots: bool = True):
        current = validate_url(url)
        assert self.session is not None
        for redirect in range(6):
            delay = await self._robots_allowed(current) if robots else 0
            host = urlsplit(current).netloc
            if host == "api.mangadex.org":
                delay = max(delay, .25)  # Official global allowance: approximately 5/s.
            gate = self.gates.setdefault(host, asyncio.Semaphore(self.settings.per_domain))
            last_status = None
            for attempt in range(1, self.settings.retries + 1):
                wait = max(0, self.cooldowns.get(host, 0) - asyncio.get_running_loop().time())
                if wait:
                    await asyncio.sleep(wait)
                try:
                    async with gate:
                        if host == "api.mangadex.org" and urlsplit(current).path.startswith("/at-home/server/"):
                            await self._pace("mangadex-at-home", 1.6)  # Below 40 requests/minute.
                        await self._pace(host, delay)
                        headers = {"Referer": referer} if referer else {}
                        async with self.session.get(current, allow_redirects=False, headers=headers) as response:
                            last_status = response.status
                            if response.status in (301, 302, 303, 307, 308):
                                current = validate_url(urljoin(current, response.headers.get("Location", "")))
                                break
                            if response.status in (429, 500, 502, 503, 504):
                                retry = self.retry_after(response.headers.get("Retry-After", "1"))
                                try:
                                    reset = float(response.headers.get("X-RateLimit-Retry-After", "0"))
                                    retry = max(retry, reset - datetime.now(timezone.utc).timestamp())
                                except ValueError:
                                    pass
                                self.cooldowns[host] = asyncio.get_running_loop().time() + max(retry, 2**(attempt - 1))
                                raise DownloadError("Limite de acesso ou falha temporária da fonte.", response.status, attempt)
                            if response.status != 200:
                                raise DownloadError("Acesso negado ou recurso indisponível; confira a URL e a autorização.", response.status, attempt)
                            size = response.content_length
                            if size is not None and size > limit:
                                raise DownloadError("Recurso excede o limite de tamanho configurado.")
                            chunks = bytearray()
                            async for chunk in response.content.iter_chunked(65536):
                                chunks.extend(chunk)
                                if len(chunks) > limit:
                                    raise DownloadError("Recurso excede o limite de tamanho configurado.")
                            return bytes(chunks), response.headers.get("Content-Type", "").split(";")[0].lower()
                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    if attempt == self.settings.retries:
                        raise DownloadError("Conexão interrompida ou tempo limite; tente novamente.", last_status, attempt) from exc
                except DownloadError as exc:
                    if exc.status not in (429, 500, 502, 503, 504) or attempt == self.settings.retries:
                        raise
                await asyncio.sleep(2**(attempt - 1))
            else:
                raise DownloadError("Tentativas esgotadas.", last_status, self.settings.retries)
        raise DownloadError("Excesso de redirecionamentos.")

    async def text(self, url: str) -> str:
        data, mime = await self._request(url, self.settings.max_html_mb * 1024**2)
        if mime not in ("text/html", "application/xhtml+xml", "text/plain", ""):
            raise DownloadError("A URL não retornou uma página HTML.")
        return data.decode("utf-8", errors="replace")

    async def image(self, url: str, referer: str = "") -> bytes:
        data, mime = await self._request(url, self.settings.max_image_mb * 1024**2, referer,
                                       robots=validate_url(url) not in self.api_images)
        if not mime.startswith("image/"):
            raise DownloadError("A fonte retornou conteúdo que não é imagem.")
        return data

    async def api_json(self, url: str) -> dict:
        url = validate_url(url)
        parsed = urlsplit(url)
        uuid = r"[a-fA-F0-9-]{36}"
        if parsed.scheme != "https" or parsed.netloc != "api.mangadex.org" or not re.fullmatch(
                rf"/(?:manga/{uuid}(?:/feed)?|chapter/{uuid}|at-home/server/{uuid})", parsed.path):
            raise SecurityError("Endpoint de API não autorizado.")
        # robots.txt governs crawlers; these documented public API operations are
        # intended for clients, including the explicitly documented AtHome route.
        data, mime = await self._request(url, self.settings.max_html_mb * 1024**2, robots=False)
        if mime != "application/json" and not mime.endswith("+json"):
            raise DownloadError("A API não retornou JSON.")
        try:
            result = json.loads(data)
        except (ValueError, UnicodeError) as exc:
            raise DownloadError("A API retornou JSON inválido.") from exc
        if not isinstance(result, dict):
            raise DownloadError("Resposta de API inválida.")
        return result

    def register_api_images(self, urls):
        # Exact image URLs returned by the API, still subject to DNS, MIME,
        # redirect and size checks. This never affects arbitrary HTML requests.
        self.api_images.update(validate_url(url) for url in urls)
