from __future__ import annotations

from pathlib import Path

from multiagent.agents.base import Agent
from multiagent.context.store import ContextStore
from multiagent.memory import SQLiteMemoryStore


class MemoryAgent(Agent):
    def __init__(self, memory_path: Path) -> None:
        super().__init__()
        self.store = SQLiteMemoryStore(memory_path)

    @property
    def name(self) -> str:
        return "memory"

    def run(self, context: ContextStore) -> ContextStore:
        context.memories = self.store.recall(
            repo_path=context.repo_path,
            task=context.task,
            file_names=list(context.files),
        )
        context.add_trace(
            self.name,
            "run",
            f"loaded {len(context.memories)} relevant memories",
        )
        if context.memories:
            context.decisions.append(
                "Memory recall:\n"
                + "\n".join(f"- {memory.content}" for memory in context.memories)
            )
        return context

    def persist(self, context: ContextStore) -> None:
        self.store.save_run(context)
