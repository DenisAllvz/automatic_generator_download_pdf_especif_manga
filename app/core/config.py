import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


def data_directory() -> Path:
    if getattr(sys, "frozen", False) and (Path(sys.executable).parent / "portable.flag").exists():
        return Path(sys.executable).parent / "data"
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / "MangaManager"


@dataclass
class Settings:
    library: str = str(Path.home() / "Downloads" / "Minha Biblioteca")
    theme: str = "dark"
    concurrent_tasks: int = 1
    download_workers: int = 2
    per_domain: int = 2
    timeout: int = 30
    retries: int = 3
    max_image_mb: int = 50
    max_html_mb: int = 8
    max_listing_pages: int = 100
    chapter_pattern: str = "{title}"
    export_format: str = "pdf"
    render_javascript: bool = False
    keep_images: bool = False
    drive_folder_id: str = ''
    drive_folder_name: str = ''
    drive_manga_id: str = ''
    drive_grouped: bool = True
    drive_auto: bool = False

    def validate(self) -> None:
        for name, low, high in (("download_workers", 1, 3), ("concurrent_tasks", 1, 4), ("per_domain", 1, 4),
                                ("timeout", 5, 120), ("retries", 1, 5),
                                ("max_image_mb", 1, 200), ("max_html_mb", 1, 20),
                                ("max_listing_pages", 1, 1000)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"Configuração inválida: {name}")
        if self.theme not in ("dark", "light") or self.export_format not in ("cbz", "pdf"):
            raise ValueError("Tema ou formato inválido")
        if type(self.render_javascript) is not bool:
            raise ValueError("Configuração de navegador inválida")
        if type(self.keep_images) is not bool:
            raise ValueError('Configuração de imagens inválida')
        if type(self.drive_grouped) is not bool or type(self.drive_auto) is not bool:
            raise ValueError('Configuração do Drive inválida')
        if not all(isinstance(getattr(self, key), str) for key in ('drive_folder_id','drive_folder_name','drive_manga_id')):
            raise ValueError('Pasta do Drive inválida')
        if self.chapter_pattern not in ("{title}", "Capítulo {number} - {title}"):
            raise ValueError("Padrão de nome inválido")
        if not self.library or not Path(self.library).is_absolute():
            raise ValueError("Escolha uma pasta absoluta para a biblioteca")

    @classmethod
    def load(cls, path: Path) -> "Settings":
        if not path.exists():
            return cls()
        result = cls(**json.loads(path.read_text(encoding="utf-8")))
        result.validate()
        return result

    def save(self, path: Path) -> None:
        from app.infrastructure.filesystem import atomic_json
        self.validate()
        atomic_json(path, asdict(self))
