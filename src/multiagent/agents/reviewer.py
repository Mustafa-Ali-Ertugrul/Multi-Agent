from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from multiagent.agents.base import Agent
from multiagent.context.store import ContextStore, Finding
from multiagent.llm.gateway import LLMGateway


class ReviewerError(RuntimeError):
    """Raised when the reviewer agent cannot complete analysis."""


class ReviewerAgent(Agent):
    def __init__(self, llm: LLMGateway) -> None:
        self.llm = llm

    @property
    def name(self) -> str:
        return "reviewer"

    def run(self, context: ContextStore) -> ContextStore:
        python_files = self._python_file_paths(context)
        if not python_files:
            context.decisions.append(
                "Python dosyasi bulunamadigi icin guvenlik incelemesi yapilmadi."
            )
            return context

        bandit_output = self._run_bandit(python_files)
        findings = self._parse_bandit_findings(context.repo_path, bandit_output)

        for finding in findings:
            context.add_finding(finding)

        context.decisions.append(self._summarize_findings(findings))
        return context

    @staticmethod
    def _python_file_paths(context: ContextStore) -> list[Path]:
        return [
            context.repo_path / file_path
            for file_path in context.files
            if file_path.endswith(".py")
        ]

    @staticmethod
    def _run_bandit(paths: list[Path]) -> dict[str, Any]:
        command = ["bandit", "-f", "json", "-q", *[str(path) for path in paths]]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                check=False,
                text=True,
            )
        except FileNotFoundError as exc:
            raise ReviewerError(
                "Bandit kurulu degil veya PATH icinde bulunamadi. "
                "Kurmak icin: pip install bandit"
            ) from exc

        if result.returncode not in (0, 1):
            raise ReviewerError(f"Bandit calistirilamadi: {result.stderr.strip()}")

        try:
            data: Any = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ReviewerError("Bandit gecerli JSON ciktisi uretmedi.") from exc

        if not isinstance(data, dict):
            raise ReviewerError("Bandit JSON ciktisi beklenen nesne biciminde degil.")
        return data

    @classmethod
    def _parse_bandit_findings(
        cls,
        repo_path: Path,
        bandit_output: dict[str, Any],
    ) -> list[Finding]:
        raw_results = bandit_output.get("results", [])
        if not isinstance(raw_results, list):
            raise ReviewerError("Bandit JSON ciktisinda 'results' listesi bulunamadi.")

        findings: list[Finding] = []
        for item in raw_results:
            if not isinstance(item, dict):
                raise ReviewerError("Bandit bulgusu beklenen nesne biciminde degil.")
            findings.append(cls._finding_from_bandit_item(repo_path, item))
        return findings

    @staticmethod
    def _finding_from_bandit_item(repo_path: Path, item: dict[str, Any]) -> Finding:
        filename = ReviewerAgent._read_str(item, "filename")
        line_number = ReviewerAgent._read_int(item, "line_number")
        issue_text = ReviewerAgent._read_str(item, "issue_text")
        severity = ReviewerAgent._read_str(item, "issue_severity")
        test_id = ReviewerAgent._read_str(item, "test_id")

        return Finding(
            severity=severity.lower(),
            file=ReviewerAgent._relative_filename(repo_path, filename),
            line=line_number,
            message=issue_text,
            source=f"bandit:{test_id}",
        )

    @staticmethod
    def _relative_filename(repo_path: Path, filename: str) -> str:
        path = Path(filename)
        try:
            return path.relative_to(repo_path).as_posix()
        except ValueError:
            return path.as_posix()

    def _summarize_findings(self, findings: list[Finding]) -> str:
        if not findings:
            prompt = (
                "Bandit hicbir guvenlik bulgusu uretmedi. Kisa bir Turkce ozet yaz."
            )
        else:
            lines = [
                f"- [{finding.severity}] {finding.file}:{finding.line} "
                f"{finding.message} ({finding.source})"
                for finding in findings
            ]
            prompt = (
                "Asagidaki Bandit guvenlik bulgularini kisa bir Turkce "
                "rapor olarak ozetle:\n" + "\n".join(lines)
            )

        return self.llm.chat(
            messages=[
                {
                    "role": "system",
                    "content": "Kisa, net ve Turkce guvenlik inceleme raporlari yaz.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )

    @staticmethod
    def _read_str(data: dict[str, Any], key: str) -> str:
        value = data.get(key)
        if not isinstance(value, str):
            raise ReviewerError(f"Bandit bulgusunda '{key}' metin olmali.")
        return value

    @staticmethod
    def _read_int(data: dict[str, Any], key: str) -> int:
        value = data.get(key)
        if not isinstance(value, int):
            raise ReviewerError(f"Bandit bulgusunda '{key}' sayi olmali.")
        return value
