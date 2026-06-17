"""Tests for LLM call metrics (Faz 2.3)."""

from unittest.mock import patch

from multiagent.llm.gateway import LLMError, LLMGateway


class _StubGateway(LLMGateway):
    """Gateway whose ``chat`` delegates to ``_chat_openai``/``_chat_ollama``
    stubs so we can exercise the metrics wrapper without real HTTP."""

    def __init__(self, *, fail: bool = False) -> None:
        super().__init__(model="stub", base_url="http://stub")
        self.fail = fail

    def _chat_openai(self, messages, temperature):  # type: ignore[override]
        if self.fail:
            raise LLMError("stub failure")
        return "ok-response"

    def _chat_ollama(self, messages, temperature):  # type: ignore[override]
        if self.fail:
            raise LLMError("stub failure")
        return "ok-response"


def test_metrics_recorded_on_success() -> None:
    gw = _StubGateway()
    result = gw.chat([{"role": "user", "content": "hello world"}])

    assert result == "ok-response"
    assert gw.metrics.total_calls == 1
    assert gw.metrics.failed_calls == 0
    metric = gw.metrics.calls[0]
    assert metric.model == "stub"
    assert metric.error is None
    assert metric.response_chars == len("ok-response")
    assert metric.prompt_chars == len("hello world")
    assert metric.duration_seconds >= 0


def test_metrics_recorded_on_failure() -> None:
    gw = _StubGateway(fail=True)

    raised = False
    try:
        gw.chat([{"role": "user", "content": "x"}])
    except LLMError:
        raised = True

    assert raised is True
    # Even on failure, the metric must be recorded (finally block)
    assert gw.metrics.total_calls == 1
    assert gw.metrics.failed_calls == 1
    assert gw.metrics.calls[0].error is not None
    assert "stub failure" in gw.metrics.calls[0].error  # type: ignore[operator]
    assert gw.metrics.calls[0].response_chars == 0


def test_metrics_accumulate_across_calls() -> None:
    gw = _StubGateway()
    gw.chat([{"role": "user", "content": "a"}])
    gw.chat([{"role": "user", "content": "bb"}])

    assert gw.metrics.total_calls == 2
    assert gw.metrics.calls[0].prompt_chars == 1
    assert gw.metrics.calls[1].prompt_chars == 2
