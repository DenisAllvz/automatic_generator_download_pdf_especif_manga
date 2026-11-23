"""Read public metadata/HTML for the sources requested by the user; no images."""
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "tmp" / "source-review"
root.mkdir(parents=True, exist_ok=True)
sources = {
    "vagabond.html": "https://mangalivre.blog/manga/vagabond/",
    "mangadex-title.json": "https://api.mangadex.org/manga/39e55355-dfb4-44e9-bd0b-df1fc3a0e33e?includes[]=cover_art",
    "mangadex-docs.html": "https://api.mangadex.org/docs/",
    "mangadex-openapi.yaml": "https://api.mangadex.org/docs/static/api.yaml",
    "mangadex-limitations.html": "https://api.mangadex.org/docs/2-limitations/",
    "mangadex-reading.html": "https://api.mangadex.org/docs/4-reading-chapter/",
    "mangadex-robots.txt": "https://api.mangadex.org/robots.txt",
    "mangadex-feed.json": "https://api.mangadex.org/manga/39e55355-dfb4-44e9-bd0b-df1fc3a0e33e/feed?limit=5&order[chapter]=asc&includes[]=scanlation_group",
}
for filename, url in sources.items():
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "MangaManager/2.0.1"})
        with urllib.request.urlopen(request, timeout=25) as response:
            data = response.read(8 * 1024 * 1024 + 1)
            if len(data) > 8 * 1024 * 1024:
                raise ValueError("Response too large")
            (root / filename).write_bytes(data)
            print(filename, response.status, len(data), flush=True)
    except Exception as exc:
        print(filename, type(exc).__name__, str(exc), flush=True)
