import ipaddress
import re
import socket
from urllib.parse import urlsplit, urlunsplit

from aiohttp.abc import AbstractResolver
from app.core.exceptions import SecurityError


def validate_url(url: str) -> str:
    try:
        parts = urlsplit(url.strip())
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
            raise ValueError
        if parts.port not in (None, 80, 443):
            raise ValueError
        if any(c.isspace() or ord(c) < 32 for c in url) or "\\" in url:
            raise ValueError
        host = parts.hostname.rstrip(".").lower()
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError
        return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path or "/", parts.query, ""))
    except (ValueError, TypeError) as exc:
        raise SecurityError("URL inválida: use HTTP/HTTPS público, sem credenciais ou portas privadas.") from exc


def safe_url(url: str) -> str:
    """Logs omit query, fragment, and credentials, including signed image URLs."""
    try:
        p = urlsplit(url)
        return urlunsplit((p.scheme, p.hostname or "", p.path, "", ""))
    except ValueError:
        return "[URL inválida]"


def scrub(message: str) -> str:
    return re.sub(r"https?://[^\s\"'<>]+", lambda m: safe_url(m.group()), message)


class PublicResolver(AbstractResolver):
    """Check addresses actually handed to the connector to prevent DNS rebinding."""
    async def resolve(self, host: str, port: int = 0, family: int = socket.AF_INET):
        import asyncio
        records = await asyncio.get_running_loop().getaddrinfo(host, port, family=family, type=socket.SOCK_STREAM)
        result = []
        for af, _, proto, _, addr in records:
            if not ipaddress.ip_address(addr[0]).is_global:
                raise SecurityError("A fonte resolveu para um endereço local ou privado.")
            result.append(dict(hostname=host, host=addr[0], port=port, family=af, proto=proto, flags=0))
        return result

    async def close(self):
        pass
