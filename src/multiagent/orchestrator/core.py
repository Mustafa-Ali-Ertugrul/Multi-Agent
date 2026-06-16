from __future__ import annotations

from multiagent.agents.base import Agent
from multiagent.context.store import ContextStore
from multiagent.llm.gateway import LLMGateway


class Orchestrator:
    def __init__(self, llm: LLMGateway, agents: list[Agent]) -> None:
        self.llm = llm
        self.agents = agents

    def run(self, context: ContextStore) -> ContextStore:
        current_context = context

        for agent in self.agents:
            print(f"[orchestrator] running agent: {agent.name}")
            current_context = agent.run(current_context)

        return current_context
