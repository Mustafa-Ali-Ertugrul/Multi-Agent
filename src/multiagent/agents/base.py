from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from multiagent.mcp.client import MCPClient

from multiagent.context.store import ContextStore


class AgentError(RuntimeError):
    """Raised when an agent fails during execution.

    Wraps the original exception so the orchestrator can log it
    and decide whether to continue or abort the pipeline.
    """

    def __init__(self, agent_name: str, message: str, *, cause: Exception | None = None) -> None:
        self.agent_name = agent_name
        super().__init__(f"[{agent_name}] {message}")
        if cause is not None:
            self.__cause__ = cause


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
