from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

from multiagent.agents.build import BuildAgent, BuildError, UnifiedDiffApplier
from multiagent.agents.security import SecurityAgent
from multiagent.config import BenchmarkModelConfig
from multiagent.context.store import BenchmarkResult, ContextStore
from multiagent.llm.gateway import LLMGateway


class BenchmarkRunner:
    def __init__(self, models: list[BenchmarkModelConfig]) -> None:
        self.models = models

    def run(self, repo_path: Path, task: str) -> list[BenchmarkResult]:
        results: list[BenchmarkResult] = []
        for model_config in self.models:
            results.append(self._run_model(repo_path, task, model_config))
        return results

    def _run_model(
        self,
        repo_path: Path,
        task: str,
        model_config: BenchmarkModelConfig,
    ) -> BenchmarkResult:
        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="multiagent-bench-") as tmp:
            temp_repo = Path(tmp) / repo_path.name
            shutil.copytree(
                repo_path,
                temp_repo,
                ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"),
            )
            context = ContextStore(repo_path=temp_repo, task=task)
            context.load_repo(temp_repo)
            error: str | None = None
            tests_passed = False
            diff_generated = False
            high_security_findings = 0

            try:
                llm = self._gateway_for(model_config)
                build = BuildAgent(llm=llm, apply=False)
                context = build.run(context)
                diff = _extract_diff(context)
                diff_generated = bool(diff)
                if diff:
                    try:
                        UnifiedDiffApplier.apply(temp_repo, diff)
                    except BuildError:
                        pass

                context = SecurityAgent().run(context)
                high_security_findings = sum(
                    1 for finding in context.findings if finding.severity == "high"
                )
                tests_passed = _run_pytest(temp_repo)
            except Exception as exc:
                error = str(exc)

            duration = time.perf_counter() - started
            score = self._score(
                diff_generated=diff_generated,
                tests_passed=tests_passed,
                high_security_findings=high_security_findings,
                duration=duration,
                cost_per_1k_tokens=model_config.cost_per_1k_tokens,
            )
            return BenchmarkResult(
                name=model_config.name,
                provider=model_config.provider,
                model=model_config.model,
                score=score,
                duration_seconds=duration,
                tests_passed=tests_passed,
                diff_generated=diff_generated,
                high_security_findings=high_security_findings,
                error=error,
            )

    @staticmethod
    def _gateway_for(model_config: BenchmarkModelConfig) -> LLMGateway:
        api_key = (
            os.environ.get(model_config.api_key_env)
            if model_config.api_key_env
            else None
        )
        base_url = model_config.base_url or _default_base_url(model_config.provider)
        return LLMGateway(
            model=model_config.model,
            base_url=base_url,
            api_key=api_key,
        )

    @staticmethod
    def _score(
        diff_generated: bool,
        tests_passed: bool,
        high_security_findings: int,
        duration: float,
        cost_per_1k_tokens: float | None,
    ) -> float:
        score = 0.0
        if diff_generated:
            score += 25
            score += 10
        if tests_passed:
            score += 25
        if high_security_findings == 0:
            score += 20
        score += max(0.0, 10.0 - min(duration, 10.0))
        if cost_per_1k_tokens is not None:
            score += max(0.0, 10.0 - min(cost_per_1k_tokens, 10.0))
        return round(score, 2)


def write_benchmark_json(path: Path, results: list[BenchmarkResult]) -> None:
    path.write_text(
        json.dumps([asdict(result) for result in results], indent=2),
        encoding="utf-8",
    )


def _extract_diff(context: ContextStore) -> str | None:
    prefix = "Onerilen degisiklik (unified diff):\n"
    for decision in reversed(context.decisions):
        if decision.startswith(prefix):
            return decision[len(prefix) :]
    return None


def _run_pytest(repo_path: Path) -> bool:
    if not any(path.name.startswith("test_") for path in repo_path.rglob("*.py")):
        return False
    result = subprocess.run(
        ["pytest"],
        cwd=repo_path,
        capture_output=True,
        check=False,
        text=True,
    )
    return bool(result.returncode == 0)


def _default_base_url(provider: str) -> str:
    if provider == "openai-compatible":
        return "https://api.openai.com/v1"
    if provider == "gemini":
        return "https://generativelanguage.googleapis.com/v1beta/openai"
    return "http://localhost:11434"
