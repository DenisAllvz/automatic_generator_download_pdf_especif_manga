import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("manga")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(root / "technical.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(handler)
