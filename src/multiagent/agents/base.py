from __future__ import annotations

from abc import ABC, abstractmethod

from multiagent.context.store import ContextStore


class Agent(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def run(self, context: ContextStore) -> ContextStore:
        raise NotImplementedError
