"""Centralised logging helpers for the multiagent package.

Usage::

    from multiagent.log import get_logger

    log = get_logger(__name__)
    log.info("agent started")
    log.debug("chunk dropped: %r", data)
"""

from __future__ import annotations

import logging
import sys


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the ``multiagent`` namespace.

    If the root ``multiagent`` logger has no handlers yet, a default
    :class:`logging.StreamHandler` writing to *stderr* is attached so
    that library code always produces output (even when the consumer
    application hasn't configured logging).
    """
    logger = logging.getLogger(f"multiagent.{name}")

    if not logging.getLogger("multiagent").handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        handler.setLevel(logging.DEBUG)
        root = logging.getLogger("multiagent")
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)

    return logger


def configure_logging(level: str = "WARNING") -> None:
    """Set the minimum level for all ``multiagent.*`` loggers.

    Accepts standard level names: ``DEBUG``, ``INFO``, ``WARNING``,
    ``ERROR``, ``CRITICAL``.
    """
    numeric = getattr(logging, level.upper(), None)
    if numeric is None:
        raise ValueError(f"Invalid log level: {level!r}")
    logging.getLogger("multiagent").setLevel(numeric)
