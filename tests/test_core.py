import json
import socket
import pytest
from app.core.config import Settings
from app.core.exceptions import SecurityError, DownloadError
from app.core.security import PublicResolver, validate_url, safe_url, scrub
from app.infrastructure.filesystem import safe_name, contained, chapter_key
from app.services.integrity import inspect_image, diagnose


@pytest.mark.parametrize("url", ["file:///C:/a", "http://localhost/a", "http://127.0.0.1", "http://10.0.0.1", "http://[::1]", "http://169.254.169.254", "http://user:pass@example.org", "https://example.org:8080", "https://example.org\\a", "http://192.168.1.1", "http://example.local", "ftp://example.org"])
def test_block_unsafe_urls(url):
    with pytest.raises(SecurityError):
        validate_url(url)


def test_valid_url_and_redaction():
    assert validate_url("https://EXAMPLE.ORG/a#x") == "https://example.org/a"
    assert safe_url("https://u:p@example.org/image?token=secret#x") == "https://example.org/image"
    assert "secret" not in scrub("failure https://example.org/image?token=secret")


async def test_dns_rebinding_blocked(monkeypatch):
    import asyncio
    async def private(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", private)
    with pytest.raises(SecurityError):
        await PublicResolver().resolve("example.org", 443)


@pytest.mark.parametrize("name", ["CON", "nul.txt", "COM1", "../a", "a/b:c", "..", "x. "])
def test_windows_names(name):
    value = safe_name(name)
    assert not any(c in value for c in '/\\:<>|?*')
    assert value and not value.endswith((".", " "))


def test_path_traversal_and_symlink(tmp_path):
    with pytest.raises(SecurityError):
        contained(tmp_path, "../escape")


def test_chapter_decimal_and_special_order():
    titles = ["Extra", "Capítulo 10.1", "Capítulo 1.5", "Chapter 2", "Prólogo", "Capítulo 0", "Capítulo 100"]
    assert sorted(titles, key=chapter_key) == ["Prólogo", "Capítulo 0", "Capítulo 1.5", "Chapter 2", "Capítulo 10.1", "Capítulo 100", "Extra"]


def test_image_signature_and_small_valid_image(image_bytes):
    info = inspect_image(image_bytes)
    assert info["extension"] == ".png" and info["width"] == 32
    with pytest.raises(DownloadError):
        inspect_image(b"<html>login required</html>")


def test_settings_validation(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(library=str(tmp_path))
    settings.save(path)
    assert Settings.load(path) == settings
    settings.per_domain = 30
    with pytest.raises(ValueError):
        settings.save(path)


def test_missing_manifest_uncertainty(tmp_path):
    assert diagnose(tmp_path)["status"] == "unverifiable"
    (tmp_path / "manifest.json").write_text("garbage")
    assert diagnose(tmp_path)["status"] == "incomplete"
