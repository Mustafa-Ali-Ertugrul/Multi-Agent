from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from multiagent.agents.base import Agent
from multiagent.context.store import ContextStore, DiffProposal, Finding
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
    new: bool = False


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
        context.add_diff_proposal(
            DiffProposal(
                agent=self.name,
                path=None,
                diff=diff,
                created_at=time.time(),
            )
        )
        context.decisions.append(f"Onerilen degisiklik (unified diff):\n{diff}")

        if self.apply:
            try:
                UnifiedDiffApplier.apply(context.repo_path, diff)
            except BuildError as exc:
                context.decisions.append(
                    f"Onerilen degisiklik UYGULANAMADI, dosyalar geri alindi: {exc}"
                )
                raise
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
            f"Ilgili repo graph ozeti:\n{BuildAgent._graph_summary(context)}\n\n"
            f"Bulgular:\n{findings or '-'}\n\n"
            f"Kararlar:\n{decisions or '-'}"
        )

    @staticmethod
    def _format_finding(finding: Finding) -> str:
        return (
            f"- [{finding.severity}] {finding.file}:{finding.line} "
            f"{finding.message} ({finding.source})"
        )

    @staticmethod
    def _graph_summary(context: ContextStore) -> str:
        if context.knowledge_graph is None:
            return "-"

        finding_files = {finding.file for finding in context.findings}
        if not finding_files:
            return context.knowledge_graph.summary(limit=10)

        matching_nodes = [
            node for node in context.knowledge_graph.nodes if node.file in finding_files
        ][:10]
        if not matching_nodes:
            return context.knowledge_graph.summary(limit=10)
        return "\n".join(
            f"{node.kind}:{node.name} ({node.file}:{node.line})"
            for node in matching_nodes
        )


class UnifiedDiffApplier:
    @classmethod
    def apply(cls, repo_path: Path, diff: str) -> None:
        """Apply a unified diff to the working tree.

        Takes a snapshot of every target file before mutating it; if any
        hunk fails, all previously-modified files are rolled back so the
        repository is left untouched. The error is then re-raised.
        Supports new file creation via ``--- /dev/null`` markers.
        """
        snapshot: dict[Path, str] = {}
        modified: list[Path] = []
        try:
            for diff_file in cls.parse(diff):
                target = cls._safe_target(repo_path, diff_file.path, diff_file.new)
                if diff_file.new:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    original: list[str] = []
                else:
                    if target not in snapshot:
                        snapshot[target] = target.read_text(encoding="utf-8")
                    original = snapshot[target].splitlines(keepends=True)
                updated = cls._apply_hunks(
                    original, diff_file.hunks, diff_file.path, diff_file.new
                )
                target.write_text("".join(updated), encoding="utf-8")
                modified.append(target)
        except Exception:
            # Roll back every file we touched, in reverse order.
            for target in reversed(modified):
                try:
                    target.write_text(snapshot[target], encoding="utf-8")
                except OSError:
                    pass
            raise

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

            old_path = lines[index].strip()
            is_new = old_path == "--- /dev/null" or old_path.startswith(
                "--- /dev/null\t"
            )
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
            files.append(DiffFile(path=path, hunks=hunks, new=is_new))

        if not files:
            raise BuildError("Unified diff bulunamadi.")
        return files

    @staticmethod
    def _apply_hunks(
        original: list[str],
        hunks: list[list[str]],
        path: str,
        new: bool = False,
    ) -> list[str]:
        updated: list[str] = []
        pointer = 0

        for hunk in hunks:
            match = HUNK_HEADER_RE.match(hunk[0])
            if match is None:
                raise BuildError(f"Hunk basligi gecersiz: {path}")

            hunk_start = int(match.group("old_start")) - 1
            if not new and (hunk_start < pointer or hunk_start > len(original)):
                raise BuildError(f"Hunk konumu gecersiz: {path}")

            if not new:
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
                    if new:
                        continue
                    UnifiedDiffApplier._expect_line(original, pointer, content, path)
                    updated.append(original[pointer])
                    pointer += 1
                elif marker == "-":
                    if new:
                        raise BuildError(
                            f"Yeni dosya diff'inde '-' satiri olamaz: {path}"
                        )
                    UnifiedDiffApplier._expect_line(original, pointer, content, path)
                    pointer += 1
                elif marker == "+":
                    updated.append(content)
                else:
                    raise BuildError(f"Hunk satiri gecersiz: {path}")

        if not new:
            updated.extend(original[pointer:])
        return updated

    @staticmethod
    def _safe_target(repo_path: Path, relative_path: str, is_new: bool = False) -> Path:
        path = Path(relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise BuildError(f"Guvenli olmayan diff yolu: {relative_path}")

        repo_root = repo_path.resolve()
        target = (repo_root / path).resolve()
        if repo_root != target and repo_root not in target.parents:
            raise BuildError(f"Diff yolu repo disina cikiyor: {relative_path}")
        if not is_new and not target.exists():
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
