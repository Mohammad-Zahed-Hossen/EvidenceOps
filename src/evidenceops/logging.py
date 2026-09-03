"""Framework-independent structured logging helpers."""

import logging

DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Configure standard-library logging without logging request content or secrets."""
    logging.basicConfig(level=level.upper(), format=DEFAULT_FORMAT)
    logging.getLogger().setLevel(level.upper())


def get_logger(name: str) -> logging.Logger:
    """Return a named logger for a framework-independent EvidenceOps component."""
    return logging.getLogger(name)
