"""Tests for the logging helpers (Faz 2.1)."""

import logging

import pytest

from multiagent.log import configure_logging, get_logger


def test_get_logger_returns_namespaced_logger() -> None:
    logger = get_logger("test_module")
    assert logger.name == "multiagent.test_module"
    # Parent logger must have at least one handler attached by default
    assert len(logging.getLogger("multiagent").handlers) >= 1


def test_configure_logging_sets_level() -> None:
    configure_logging("DEBUG")
    assert logging.getLogger("multiagent").level == logging.DEBUG

    configure_logging("WARNING")
    assert logging.getLogger("multiagent").level == logging.WARNING


def test_configure_logging_rejects_invalid_level() -> None:
    raised = False
    try:
        configure_logging("NONSENSE")
    except ValueError:
        raised = True
    assert raised is True


def test_logger_emits_records(caplog: pytest.LogCaptureFixture) -> None:
    """get_logger ile üretilen kayitlar caplog ile yakalanabilmeli."""
    configure_logging("DEBUG")
    log = get_logger("captest")

    with caplog.at_level(logging.DEBUG, logger="multiagent.captest"):
        log.info("hello %s", "world")

    assert any("hello world" in r.getMessage() for r in caplog.records)
