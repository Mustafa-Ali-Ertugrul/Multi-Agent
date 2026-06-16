from __future__ import annotations

import ast

from multiagent.agents.base import Agent
from multiagent.context.store import ContextStore
from multiagent.llm.gateway import LLMGateway

MAX_FALLBACK_LINES = 40


class ArchitectAgent(Agent):
    def __init__(self, llm: LLMGateway) -> None:
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
                        "mimari iyilestirme raporu uret:\n\n" + "\n\n".join(summaries)
                    ),
                },
            ],
            temperature=0.2,
        )
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
