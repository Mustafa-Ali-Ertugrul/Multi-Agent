from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from multiagent.mcp.client import MCPClient

from multiagent.context.store import ContextStore


class Agent(ABC):
    def __init__(
        self,
        tools: MCPClient | None = None,
        require_mcp: bool = False,
    ) -> None:
        self.tools = tools
        self.require_mcp = require_mcp

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def run(self, context: ContextStore) -> ContextStore:
        raise NotImplementedError
