import io
import os
import pytest
from PIL import Image
from app.core.config import Settings
from app.infrastructure.database import Database
from app.models import Chapter, Manga
from app.services.library import Library

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def image_bytes():
    stream = io.BytesIO()
    Image.new("RGB", (32, 64), "navy").save(stream, format="PNG")
    return stream.getvalue()


@pytest.fixture
def setup_library(tmp_path):
    settings = Settings(library=str(tmp_path / "library"), keep_images=True)
    db = Database(tmp_path / "data" / "library.sqlite3")
    library = Library(db, Path(settings.library))
    manga = Manga("Obra Á", "https://example.org/manga/a", chapters=[Chapter("Capítulo 1", "https://example.org/chapter-1")])
    mid, ids = library.add(manga)
    library.enqueue(ids)
    return settings, db, library, mid, ids


from pathlib import Path
