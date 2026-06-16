from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

from multiagent.agents.base import Agent
from multiagent.context.store import ContextStore, Finding
from multiagent.llm.gateway import LLMGateway

MAX_CODE_CHARS = 12_000


@dataclass(frozen=True)
class TestRunSummary:
    passed: int
    failed: int
    errors: int
    skipped: int
    no_tests: bool
    output_excerpt: str

    @property
    def has_problems(self) -> bool:
        return self.no_tests or self.failed > 0 or self.errors > 0


class TestRunnerError(RuntimeError):
    """Raised when the test runner agent cannot execute pytest."""


class TestRunnerAgent(Agent):
    __test__ = False

    def __init__(self, llm: LLMGateway) -> None:
        self.llm = llm

    @property
    def name(self) -> str:
        return "test-runner"

    def run(self, context: ContextStore) -> ContextStore:
        output = self._run_pytest(context)
        summary = self._parse_pytest_output(output)

        findings = self._findings_from_summary(summary)
        for finding in findings:
            context.add_finding(finding)

        context.decisions.append(self._decision_summary(summary))

        if summary.has_problems:
            suggestions = self._suggest_tests(context, summary)
            context.decisions.append(suggestions)

        return context

    @staticmethod
    def _run_pytest(context: ContextStore) -> str:
        command = ["pytest"]

        try:
            result = subprocess.run(
                command,
                cwd=context.repo_path,
                capture_output=True,
                check=False,
                text=True,
            )
        except FileNotFoundError as exc:
            raise TestRunnerError(
                "pytest kurulu degil veya PATH icinde bulunamadi. "
                "Kurmak icin: pip install pytest"
            ) from exc

        return f"{result.stdout}\n{result.stderr}".strip()

    @staticmethod
    def _parse_pytest_output(output: str) -> TestRunSummary:
        counts = {
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
        }

        for amount, label in re.findall(
            r"(\d+)\s+(passed|failed|errors?|skipped)",
            output,
        ):
            normalized = "errors" if label in {"error", "errors"} else label
            counts[normalized] += int(amount)

        no_tests = (
            "collected 0 items" in output
            or "no tests ran" in output.lower()
            or "no tests collected" in output.lower()
        )

        return TestRunSummary(
            passed=counts["passed"],
            failed=counts["failed"],
            errors=counts["errors"],
            skipped=counts["skipped"],
            no_tests=no_tests,
            output_excerpt=TestRunnerAgent._output_excerpt(output),
        )

    @staticmethod
    def _findings_from_summary(summary: TestRunSummary) -> list[Finding]:
        findings: list[Finding] = []

        if summary.no_tests:
            findings.append(
                Finding(
                    severity="medium",
                    file="tests",
                    line=0,
                    message="pytest hic test bulamadi.",
                    source="pytest",
                )
            )

        if summary.failed > 0 or summary.errors > 0:
            findings.append(
                Finding(
                    severity="high",
                    file="tests",
                    line=0,
                    message=(
                        f"pytest basarisiz: {summary.failed} failed, "
                        f"{summary.errors} errors."
                    ),
                    source="pytest",
                )
            )

        return findings

    @staticmethod
    def _decision_summary(summary: TestRunSummary) -> str:
        if summary.no_tests:
            return "Test ozeti: pytest hic test bulamadi."

        status = "basarili"
        if summary.failed > 0 or summary.errors > 0:
            status = "basarisiz"

        return (
            f"Test ozeti: {status}. "
            f"{summary.passed} gecti, {summary.failed} kaldi, "
            f"{summary.errors} hata, {summary.skipped} atlandi."
        )

    def _suggest_tests(self, context: ContextStore, summary: TestRunSummary) -> str:
        code_context = self._code_context(context)
        return self.llm.chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Kisa ve uygulanabilir Turkce test iyilestirme onerileri yaz. "
                        "Eksik test fonksiyonlarini Python kod blogu olarak oner."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "pytest sonucu sorunlu. Mevcut kod ve test ciktisina gore "
                        "eksik test fonksiyonlari oner.\n\n"
                        f"pytest ozeti:\n{summary.output_excerpt}\n\n"
                        f"kod:\n{code_context}"
                    ),
                },
            ],
            temperature=0.2,
        )

    @staticmethod
    def _code_context(context: ContextStore) -> str:
        chunks: list[str] = []
        current_size = 0

        for path, content in sorted(context.files.items()):
            if not path.endswith(".py"):
                continue

            header = f"# {path}\n"
            remaining = MAX_CODE_CHARS - current_size - len(header)
            if remaining <= 0:
                break

            excerpt = content[:remaining]
            chunks.append(f"{header}{excerpt}")
            current_size += len(header) + len(excerpt)

        return "\n\n".join(chunks)

    @staticmethod
    def _output_excerpt(output: str) -> str:
        lines = output.splitlines()
        return "\n".join(lines[-40:])
