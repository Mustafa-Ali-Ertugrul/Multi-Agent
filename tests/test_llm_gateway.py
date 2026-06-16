from __future__ import annotations

import httpx
import pytest

from multiagent.llm.gateway import LLMError, LLMGateway


def test_chat_raises_llm_error_when_ollama_cannot_be_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = httpx.Request("POST", "http://localhost:11434/api/chat")

    def fake_post(
        url: str,
        json: dict[str, object],
        timeout: float,
    ) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    monkeypatch.setattr(httpx, "post", fake_post)

    gateway = LLMGateway(model="qwen2.5-coder")

    with pytest.raises(LLMError, match="Could not reach Ollama"):
        gateway.chat(messages=[{"role": "user", "content": "Merhaba"}])


def test_chat_openai_reads_streaming_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeStreamResponse:
        def __enter__(self) -> FakeStreamResponse:
            return self

        def __exit__(
            self,
            exc_type: object,
            exc_value: object,
            traceback: object,
        ) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_lines(self) -> list[str]:
            return [
                'data: {"choices":[{"delta":{"content":"hello "}}]}',
                'data: {"choices":[{"delta":{"content":"world"}}]}',
                "data: [DONE]",
            ]

    def fake_stream(
        method: str,
        url: str,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> FakeStreamResponse:
        assert method == "POST"
        assert url == "https://api.example.test/chat/completions"
        assert headers["Authorization"] == "Bearer test-key"
        assert json["stream"] is True
        assert timeout == 300.0
        return FakeStreamResponse()

    monkeypatch.setattr(httpx, "stream", fake_stream)

    gateway = LLMGateway(
        model="kimi-k2.6",
        base_url="https://api.example.test",
        api_key="test-key",
    )

    assert gateway.chat(messages=[{"role": "user", "content": "Merhaba"}]) == (
        "hello world"
    )


def test_chat_openai_rejects_empty_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeStreamResponse:
        def __enter__(self) -> FakeStreamResponse:
            return self

        def __exit__(
            self,
            exc_type: object,
            exc_value: object,
            traceback: object,
        ) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_lines(self) -> list[str]:
            return ["data: [DONE]"]

    def fake_stream(
        method: str,
        url: str,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> FakeStreamResponse:
        return FakeStreamResponse()

    monkeypatch.setattr(httpx, "stream", fake_stream)

    gateway = LLMGateway(
        model="kimi-k2.6",
        base_url="https://api.example.test",
        api_key="test-key",
    )

    with pytest.raises(LLMError, match="empty or invalid stream"):
        gateway.chat(messages=[{"role": "user", "content": "Merhaba"}])
