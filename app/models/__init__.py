from dataclasses import dataclass, field


@dataclass(frozen=True)
class Chapter:
    title: str
    url: str
    language: str = ""


@dataclass
class Manga:
    title: str
    url: str
    description: str = ""
    cover: str = ""
    chapters: list[Chapter] = field(default_factory=list)
    listing_complete: bool = False


@dataclass
class PageList:
    urls: list[str]
    # HTML image count alone does not establish source completeness.
    authoritative: bool = False
    cache_keys: list[str] | None = None
