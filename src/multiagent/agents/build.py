from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from multiagent.agents.base import Agent
from multiagent.context.store import ContextStore, Finding
from multiagent.llm.gateway import LLMGateway

if TYPE_CHECKING:
    from multiagent.mcp.client import MCPClient

HUNK_HEADER_RE = re.compile(r"@@ -(?P<old_start>\d+)(?:,\d+)? \+\d+(?:,\d+)? @@")


class BuildError(RuntimeError):
    """Raised when a proposed build diff cannot be handled safely."""


@dataclass(frozen=True)
class DiffFile:
    path: str
    hunks: list[list[str]]


class BuildAgent(Agent):
    def __init__(
        self,
        llm: LLMGateway,
        apply: bool = False,
        tools: MCPClient | None = None,
        require_mcp: bool = False,
    ) -> None:
        super().__init__(tools=tools, require_mcp=require_mcp)
        self.llm = llm
        self.apply = apply

    @property
    def name(self) -> str:
        return "build"

    def run(self, context: ContextStore) -> ContextStore:
        diff = self._generate_diff(context)
        context.decisions.append(f"Onerilen degisiklik (unified diff):\n{diff}")

        if self.apply:
            UnifiedDiffApplier.apply(context.repo_path, diff)
            context.decisions.append("Onerilen degisiklik dosyalara uygulandi.")

        return context

    def _generate_diff(self, context: ContextStore) -> str:
        return self.llm.chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Sadece unified diff formatinda yanit ver. "
                        "Otomatik uygulanabilir, kucuk ve guvenli duzeltmeler oner."
                    ),
                },
                {
                    "role": "user",
                    "content": self._build_prompt(context),
                },
            ],
            temperature=0.2,
        )

    @staticmethod
    def _build_prompt(context: ContextStore) -> str:
        findings = "\n".join(
            BuildAgent._format_finding(item) for item in context.findings
        )
        decisions = "\n".join(f"- {item}" for item in context.decisions)

        return (
            "Asagidaki bulgular ve kararlar icin onerilen duzeltmeleri "
            "unified diff formatinda uret.\n\n"
            f"Bulgular:\n{findings or '-'}\n\n"
            f"Kararlar:\n{decisions or '-'}"
        )

    @staticmethod
    def _format_finding(finding: Finding) -> str:
        return (
            f"- [{finding.severity}] {finding.file}:{finding.line} "
            f"{finding.message} ({finding.source})"
        )


class UnifiedDiffApplier:
    @classmethod
    def apply(cls, repo_path: Path, diff: str) -> None:
        for diff_file in cls.parse(diff):
            target = cls._safe_target(repo_path, diff_file.path)
            original = target.read_text(encoding="utf-8").splitlines(keepends=True)
            updated = cls._apply_hunks(original, diff_file.hunks, diff_file.path)
            target.write_text("".join(updated), encoding="utf-8")

    @classmethod
    def parse(cls, diff: str) -> list[DiffFile]:
        normalized = cls._strip_code_fence(diff)
        lines = normalized.splitlines(keepends=True)
        files: list[DiffFile] = []
        index = 0

        while index < len(lines):
            line = lines[index]
            if not line.startswith("--- "):
                index += 1
                continue

            if index + 1 >= len(lines) or not lines[index + 1].startswith("+++ "):
                raise BuildError("Unified diff dosya basligi hatali.")

            path = cls._extract_new_path(lines[index + 1])
            index += 2
            hunks: list[list[str]] = []

            while index < len(lines) and not lines[index].startswith("--- "):
                if not lines[index].startswith("@@ "):
                    raise BuildError("Unified diff hunk basligi bekleniyordu.")

                hunk: list[str] = [lines[index]]
                index += 1
                while (
                    index < len(lines)
                    and not lines[index].startswith("@@ ")
                    and not lines[index].startswith("--- ")
                ):
                    hunk.append(lines[index])
                    index += 1
                hunks.append(hunk)

            if not hunks:
                raise BuildError("Unified diff en az bir hunk icermeli.")
            files.append(DiffFile(path=path, hunks=hunks))

        if not files:
            raise BuildError("Unified diff bulunamadi.")
        return files

    @staticmethod
    def _apply_hunks(
        original: list[str],
        hunks: list[list[str]],
        path: str,
    ) -> list[str]:
        updated: list[str] = []
        pointer = 0

        for hunk in hunks:
            match = HUNK_HEADER_RE.match(hunk[0])
            if match is None:
                raise BuildError(f"Hunk basligi gecersiz: {path}")

            hunk_start = int(match.group("old_start")) - 1
            if hunk_start < pointer or hunk_start > len(original):
                raise BuildError(f"Hunk konumu gecersiz: {path}")

            updated.extend(original[pointer:hunk_start])
            pointer = hunk_start

            for line in hunk[1:]:
                if line.startswith("\\"):
                    continue

                if not line:
                    raise BuildError(f"Hunk satiri gecersiz: {path}")

                marker = line[0]
                content = line[1:]

                if marker == " ":
                    UnifiedDiffApplier._expect_line(original, pointer, content, path)
                    updated.append(original[pointer])
                    pointer += 1
                elif marker == "-":
                    UnifiedDiffApplier._expect_line(original, pointer, content, path)
                    pointer += 1
                elif marker == "+":
                    updated.append(content)
                else:
                    raise BuildError(f"Hunk satiri gecersiz: {path}")

        updated.extend(original[pointer:])
        return updated

    @staticmethod
    def _safe_target(repo_path: Path, relative_path: str) -> Path:
        path = Path(relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise BuildError(f"Guvenli olmayan diff yolu: {relative_path}")

        repo_root = repo_path.resolve()
        target = (repo_root / path).resolve()
        if repo_root != target and repo_root not in target.parents:
            raise BuildError(f"Diff yolu repo disina cikiyor: {relative_path}")
        if not target.exists():
            raise BuildError(f"Diff hedef dosyasi bulunamadi: {relative_path}")
        return target

    @staticmethod
    def _expect_line(
        original: list[str],
        pointer: int,
        expected: str,
        path: str,
    ) -> None:
        if pointer >= len(original) or original[pointer] != expected:
            raise BuildError(f"Diff mevcut dosya icerigiyle eslesmedi: {path}")

    @staticmethod
    def _extract_new_path(line: str) -> str:
        raw_path = line[4:].strip().split("\t", maxsplit=1)[0]
        if raw_path == "/dev/null":
            raise BuildError("Yeni dosya olusturan diff henuz desteklenmiyor.")
        if raw_path.startswith("b/"):
            return raw_path[2:]
        return raw_path

    @staticmethod
    def _strip_code_fence(diff: str) -> str:
        stripped = diff.strip()
        if not stripped.startswith("```"):
            return diff

        lines = stripped.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]) + "\n"
        return diff
