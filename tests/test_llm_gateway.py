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
