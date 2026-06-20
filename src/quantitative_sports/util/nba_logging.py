from __future__ import annotations
import importlib
import logging
from typing import Any, cast


def _load_rich_handler() -> type[logging.Handler] | None:
    try:
        module = importlib.import_module("rich.logging")
        return getattr(module, "RichHandler")
    except (ImportError, AttributeError):
        return None


def configure_logging(level: str = "INFO") -> None:
    """
    Configure root logging with RichHandler.

    This should be called once from CLI entrypoints.
    """
    numeric = getattr(logging, level.upper(), logging.INFO)
    rich_handler = _load_rich_handler()
    handlers = (
        [cast(Any, rich_handler)(rich_tracebacks=True, markup=True)]
        if rich_handler
        else [logging.StreamHandler()]
    )
    logging.basicConfig(level=numeric, format="%(message)s", datefmt="[%X]", handlers=handlers)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name.

    Args:
        name: Name for the logger (typically __name__ from the calling module).

    Returns:
        A configured Logger instance.
    """
    return logging.getLogger(name)
