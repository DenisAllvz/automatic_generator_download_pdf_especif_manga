"""Sequential URL batches; one failed source does not discard the remaining links."""
from app.infrastructure.filesystem import identity
from app.core.security import scrub


async def add_links(text, library, fetch, cancel=None):
    import asyncio
    urls = list(dict.fromkeys(text.split()))
    if not urls:
        raise ValueError('Cole pelo menos um link.')
    results = []
    for url in urls:
        if cancel is not None and cancel.is_set():
            break
        try:
            pending = asyncio.create_task(fetch(url))
            try:
                while not pending.done():
                    if cancel is not None and cancel.is_set():
                        return results + [dict(url=url, error='Lista interrompida pelo usuário.')]
                    await asyncio.wait({pending}, timeout=.1)
                manga, cover, adapter = pending.result()
            finally:
                if not pending.done():
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
            mid, _ = library.add(manga)
            if cover:
                from app.services.covers import save_cover
                save_cover(library.db, mid, cover, library.db.path.parent)
            languages = {c.language for c in manga.chapters if c.language}
            language = next((lang for lang in ('pt-br', 'pt', 'en') if lang in languages), '')
            ids = [identity(c.url) for c in manga.chapters if not language or c.language == language]
            queued = library.enqueue(ids, skip_complete=True)
            results.append(dict(url=url, title=manga.title, **queued))
        except Exception as exc:
            # Batch boundary: preserve every error in the returned report and continue.
            results.append(dict(url=url, error=scrub(f'{type(exc).__name__}: {exc}')))
    return results
