"""Tests for LLMGateway retry/backoff behavior."""

from unittest.mock import patch

import pytest

from multiagent.llm.gateway import LLMError, LLMGateway


def test_chat_retries_on_transient_error() -> None:
    """Gateway should retry on LLMError and succeed on second attempt."""
    gateway = LLMGateway(model="test-model")

    call_count = 0

    def flaky_chat(messages, temperature):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise LLMError("transient error")
        return "success response"

    with patch.object(gateway, "_chat_ollama", side_effect=flaky_chat):
        with patch("multiagent.llm.gateway.time.sleep"):  # skip real waits
            result = gateway.chat(messages=[{"role": "user", "content": "hi"}])

    assert result == "success response"
    assert call_count == 2
    assert len(gateway.metrics.calls) == 2
    assert gateway.metrics.calls[0].error is not None
    assert gateway.metrics.calls[1].error is None


def test_chat_exhausts_retries_and_raises() -> None:
    """Gateway should raise after max_retries attempts."""
    gateway = LLMGateway(model="test-model")

    with patch.object(gateway, "_chat_ollama", side_effect=LLMError("permanent error")):
        with patch("multiagent.llm.gateway.time.sleep"):
            with pytest.raises(LLMError, match="permanent error"):
                gateway.chat(messages=[{"role": "user", "content": "hi"}])

    assert len(gateway.metrics.calls) == 3
    assert all(c.error is not None for c in gateway.metrics.calls)


def test_chat_no_retry_on_success() -> None:
    """Gateway should not retry if first call succeeds."""
    gateway = LLMGateway(model="test-model")

    with patch.object(gateway, "_chat_ollama", return_value="ok"):
        result = gateway.chat(messages=[{"role": "user", "content": "hi"}])

    assert result == "ok"
    assert len(gateway.metrics.calls) == 1
    assert gateway.metrics.calls[0].error is None
