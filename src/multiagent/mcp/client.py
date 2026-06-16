from __future__ import annotations

from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, Self

try:
    from mcp.client.session import ClientSession  # type: ignore
    from mcp.client.sse import sse_client  # type: ignore
    from mcp.client.stdio import StdioServerParameters, stdio_client  # type: ignore
except ImportError as exc:
    raise RuntimeError(
        "MCP SDK (mcp) kurulu degil. Lutfen 'pip install mcp' ile kurun."
    ) from exc


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class MCPServerConfig:
    command: str | None = None
    args: list[str] | None = None
    url: str | None = None

    def validate(self) -> None:
        if self.url is not None:
            if self.command is not None:
                raise ValueError("MCPServerConfig hem command hem url iceremez.")
        elif self.command is None:
            raise ValueError("MCPServerConfig command veya url icermelidir.")


class MCPClient:
    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self.config.validate()
        self._exit_stack = AsyncExitStack()
        self._session: ClientSession | None = None

    async def __aenter__(self) -> Self:
        if self.config.url is not None:
            read_stream, write_stream = await self._exit_stack.enter_async_context(
                sse_client(self.config.url)
            )
        else:
            assert self.config.command is not None
            params = StdioServerParameters(
                command=self.config.command,
                args=self.config.args or [],
                env=None,
            )
            read_stream, write_stream = await self._exit_stack.enter_async_context(
                stdio_client(params)
            )

        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        assert self._session is not None
        await self._session.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any | None,
    ) -> None:
        await self._exit_stack.aclose()
        self._session = None

    async def list_tools(self) -> list[ToolSpec]:
        if self._session is None:
            raise RuntimeError("MCPClient baslatilmadi. 'async with' kullanin.")

        result = await self._session.list_tools()
        tools: list[ToolSpec] = []
        for tool in result.tools:
            tools.append(
                ToolSpec(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=tool.inputSchema,
                )
            )
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        if self._session is None:
            raise RuntimeError("MCPClient baslatilmadi. 'async with' kullanin.")

        result = await self._session.call_tool(name, arguments)

        texts: list[str] = []
        for content in result.content:
            if content.type == "text":
                texts.append(content.text)
        return "\n".join(texts)
