from __future__ import annotations

import os
from typing import Self

import httpx

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5-coder"


class LLMError(RuntimeError):
    """Raised when the LLM gateway cannot complete a chat request."""


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
    ) -> str:
        if self.api_key:
            return self._chat_openai(messages, temperature)
        return self._chat_ollama(messages, temperature)

    def _chat_openai(
        self,
        messages: list[dict[str, object]],
        temperature: float,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LLMError(
                f"OpenAI API error ({exc.response.status_code}): {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            raise LLMError(f"Could not reach API at {self.base_url}: {exc}") from exc

        try:
            data = response.json()
            return str(data["choices"][0]["message"]["content"])
        except (ValueError, KeyError, IndexError) as exc:
            raise LLMError("API returned an invalid JSON response.") from exc

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
                timeout=60.0,
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
