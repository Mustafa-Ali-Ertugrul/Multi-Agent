from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from multiagent.agents.base import Agent
from multiagent.context.store import ContextStore
from multiagent.llm.gateway import LLMError, LLMGateway

if TYPE_CHECKING:
    from multiagent.mcp.client import MCPClient

MAX_FALLBACK_LINES = 40


class ArchitectAgent(Agent):
    def __init__(
        self,
        llm: LLMGateway,
        tools: MCPClient | None = None,
        require_mcp: bool = False,
    ) -> None:
        super().__init__(tools=tools, require_mcp=require_mcp)
        self.llm = llm

    @property
    def name(self) -> str:
        return "architect"

    def run(self, context: ContextStore) -> ContextStore:
        summaries = [
            self._summarize_file(path, content)
            for path, content in sorted(context.files.items())
            if path.endswith(".py")
        ]

        if not summaries:
            context.decisions.append(
                "Python dosyasi bulunamadigi icin mimari inceleme yapilmadi."
            )
            return context

        try:
            report = self.llm.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Kisa, net ve Turkce mimari inceleme raporlari yaz. "
                            "Katman ayrimi, bagimlilik yonu ve refactor firsatlarini "
                            "degerlendir."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Asagidaki Python repo yapisini incele ve kisa bir "
                            "mimari iyilestirme raporu uret:\n\n"
                            + ArchitectAgent._memory_context(context)
                            + ArchitectAgent._graph_context(context)
                            + "\n\n".join(summaries)
                        ),
                    },
                ],
                temperature=0.2,
            )
        except LLMError:
            report = "Mimari inceleme ozeti:\n" + "\n\n".join(summaries)
        context.decisions.append(report)
        return context

    @classmethod
    def _summarize_file(cls, path: str, content: str) -> str:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return cls._fallback_summary(path, content)

        imports: list[str] = []
        classes: list[str] = []
        functions: list[str] = []

        for node in tree.body:
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.extend(f"{module}.{alias.name}" for alias in node.names)
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)

        return (
            f"File: {path}\n"
            f"Imports: {cls._format_items(imports)}\n"
            f"Classes: {cls._format_items(classes)}\n"
            f"Functions: {cls._format_items(functions)}"
        )

    @staticmethod
    def _fallback_summary(path: str, content: str) -> str:
        first_lines = "\n".join(content.splitlines()[:MAX_FALLBACK_LINES])
        return f"File: {path}\nAST: parse failed\nFirst lines:\n{first_lines}"

    @staticmethod
    def _format_items(items: list[str]) -> str:
        if not items:
            return "-"
        return ", ".join(items)

    @staticmethod
    def _memory_context(context: ContextStore) -> str:
        if not context.memories:
            return ""
        lines = "\n".join(f"- {memory.content}" for memory in context.memories[:5])
        return f"Kalici hafiza:\n{lines}\n\n"

    @staticmethod
    def _graph_context(context: ContextStore) -> str:
        if context.knowledge_graph is None:
            return ""
        return f"Repo knowledge graph ozeti:\n{context.knowledge_graph.summary()}\n\n"
