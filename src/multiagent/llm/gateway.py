from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Self

import httpx

from multiagent.log import get_logger

log = get_logger("llm")

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5-coder"


class LLMError(RuntimeError):
    """Raised when the LLM gateway cannot complete a chat request."""


@dataclass(frozen=True)
class CallMetric:
    """Metrics for a single :meth:`LLMGateway.chat` call."""

    model: str
    prompt_chars: int
    response_chars: int
    duration_seconds: float
    error: str | None = None


@dataclass
class CallMetrics:
    """Accumulator for :class:`CallMetric` across a run."""

    calls: list[CallMetric] = field(default_factory=list)

    @property
    def total_calls(self) -> int:
        return len(self.calls)

    @property
    def total_duration_seconds(self) -> float:
        return sum(c.duration_seconds for c in self.calls)

    @property
    def failed_calls(self) -> int:
        return sum(1 for c in self.calls if c.error is not None)


class LLMGateway:
    def __init__(
        self,
        model: str,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.metrics = CallMetrics()

    @classmethod
    def from_env(
        cls,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
    ) -> Self:
        env_model = os.getenv("MULTIAGENT_MODEL")
        env_base_url = os.getenv("MULTIAGENT_BASE_URL")
        env_api_key = os.getenv("MULTIAGENT_API_KEY")
        return cls(
            model=env_model or model,
            base_url=env_base_url or base_url,
            api_key=env_api_key,
        )

    def chat(
        self,
        messages: list[dict[str, object]],
        temperature: float = 0.2,
        max_retries: int = 3,
    ) -> str:
        prompt_chars = sum(len(str(m.get("content", ""))) for m in messages)
        start = time.monotonic()
        last_exc: LLMError | None = None

        for attempt in range(max_retries):
            error: str | None = None
            response = ""
            try:
                if self.api_key:
                    response = self._chat_openai(messages, temperature)
                else:
                    response = self._chat_ollama(messages, temperature)
                return response
            except LLMError as exc:
                last_exc = exc
                error = str(exc)
                if attempt < max_retries - 1:
                    wait = 2**attempt  # 1s, 2s, 4s
                    log.warning(
                        "LLM cagrisi basarisiz (deneme %d/%d), %ds sonra tekrar: %s",
                        attempt + 1,
                        max_retries,
                        wait,
                        exc,
                    )
                    time.sleep(wait)
                    continue
                raise
            finally:
                elapsed = time.monotonic() - start
                self.metrics.calls.append(
                    CallMetric(
                        model=self.model,
                        prompt_chars=prompt_chars,
                        response_chars=len(response),
                        duration_seconds=elapsed,
                        error=error,
                    )
                )

        # Should not reach here, but satisfy type checker
        if last_exc is not None:
            raise last_exc
        raise LLMError("LLM cagrisi bilinmeyen bir sebeple basarisiz oldu.")

    def _chat_openai(
        self,
        messages: list[dict[str, object]],
        temperature: float,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        full_content = ""
        try:
            with httpx.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=300.0,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            chunk = json.loads(line[6:])
                            delta = chunk["choices"][0].get("delta", {})
                            if "content" in delta and delta["content"]:
                                full_content += delta["content"]
                        except (json.JSONDecodeError, KeyError, IndexError):
                            log.debug("stream chunk yoksayildi: %s", line)
        except httpx.HTTPStatusError as exc:
            raise LLMError(
                f"OpenAI API error ({exc.response.status_code}): {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            raise LLMError(f"Could not reach API at {self.base_url}: {exc}") from exc

        if not full_content:
            raise LLMError("API returned an empty or invalid stream response.")

        return full_content

    def _chat_ollama(
        self,
        messages: list[dict[str, object]],
        temperature: float,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }

        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=300.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LLMError(
                f"Ollama chat request failed with status "
                f"{exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            raise LLMError(f"Could not reach Ollama at {self.base_url}: {exc}") from exc

        try:
            data: object = response.json()
        except ValueError as exc:
            raise LLMError("Ollama returned an invalid JSON response.") from exc

        return self._extract_content(data)

    @staticmethod
    def _extract_content(data: object) -> str:
        if not isinstance(data, dict):
            raise LLMError("Ollama returned an unexpected response shape.")

        message = data.get("message")
        if not isinstance(message, dict):
            raise LLMError("Ollama response is missing the message object.")

        content = message.get("content")
        if not isinstance(content, str):
            raise LLMError("Ollama response is missing message content.")

        return content
