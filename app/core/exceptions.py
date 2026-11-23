class MangaError(Exception):
    """Erro acionável, seguro para a interface."""


class SecurityError(MangaError):
    pass


class ExtractionError(MangaError):
    pass


class DownloadError(MangaError):
    def __init__(self, message: str, status: int | None = None, attempts: int = 1):
        super().__init__(message)
        self.status = status
        self.attempts = attempts


class TaskInterrupted(MangaError):
    pass
