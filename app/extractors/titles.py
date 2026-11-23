"""Prefer work metadata over a site's branding and navigation headings."""
import re
import unicodedata
from urllib.parse import urlsplit, unquote


def normalized(value):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower())


def clean_chapter_title(value):
    value = re.sub(r'\s+', ' ', value).strip()
    pieces = re.split(r'\s*:\s*|\s+-\s+', value, maxsplit=1)
    if len(pieces) == 2:
        if normalized(pieces[0]) == normalized(pieces[1]):
            return pieces[0]
        if all(re.fullmatch(r'Cap[ií]tulo\s+\d+(?:[.,]\d+)?', part, re.I) for part in pieces):
            return pieces[1]
    return value


def is_site_title(title, url, site_name=""):
    host = (urlsplit(url).hostname or "").removeprefix("www.")
    brands = [site_name, host, host.split(".")[0]]
    return bool(normalized(title)) and normalized(title) in {normalized(b) for b in brands if b}


def title_from_work_url(url):
    match = re.match(r"^/(?:manga|manhwa|manhua|series|comic)/([^/]+)/?$", urlsplit(url).path, re.I)
    if not match:
        return ""
    slug = unquote(match.group(1))
    if re.fullmatch(r"[a-f0-9-]{32,36}|\d+", slug, re.I):
        return ""
    return re.sub(r"[-_]+", " ", slug).strip().title()


def work_title(soup, url, structured):
    site = soup.select_one('meta[property="og:site_name"]')
    site_name = site.get("content", "") if site else ""
    def clean(value):
        if not isinstance(value, str):
            return ""
        value = re.sub(r"\s+", " ", value).strip()
        brands = [site_name, (urlsplit(url).hostname or "").split(".")[0]]
        for brand in brands:
            if brand:
                value = re.sub(r"\s+(?:\||-|–|—|::)\s*" + re.escape(brand) + r"\s*$", "", value, flags=re.I).strip()
        return "" if is_site_title(value, url, site_name) else value
    candidates = []
    for selector in ("h1.manga-title", ".post-title h1", "h1.entry-title", "h1[itemprop='name']", ".manga-title", ".series-title"):
        candidates.extend(t.get_text(" ", strip=True) for t in soup.select(selector)
                          if not t.find_parent(["header", "nav", "footer"]))
    candidates.append(structured.get("name", ""))
    candidates.extend(t.get_text(" ", strip=True) for t in soup.select("h1")
                      if not t.find_parent(["header", "nav", "footer"]) and "site-title" not in t.get("class", []))
    og = soup.select_one('meta[property="og:title"]')
    candidates.append(og.get("content", "") if og else "")
    candidates.append(soup.title.get_text(strip=True) if soup.title else "")
    return next((title for value in candidates if (title := clean(value))), "") or title_from_work_url(url)
