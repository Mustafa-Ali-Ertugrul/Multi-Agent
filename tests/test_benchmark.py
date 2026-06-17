from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from multiagent.agents.build import BuildAgent
from multiagent.agents.security import SecurityAgent
from multiagent.benchmark import BenchmarkRunner
from multiagent.config import BenchmarkModelConfig
from multiagent.context.store import ContextStore


def test_benchmark_runner_scores_model_without_mutating_repo(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def answer():\n    return 41\n", encoding="utf-8")
    (repo / "test_app.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )

    def fake_build_run(self: BuildAgent, context: ContextStore) -> ContextStore:
        context.decisions.append(
            "Onerilen degisiklik (unified diff):\n"
            "--- a/app.py\n"
            "+++ b/app.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def answer():\n"
            "-    return 41\n"
            "+    return 42\n"
        )
        return context

    monkeypatch.setattr(BuildAgent, "run", fake_build_run)
    monkeypatch.setattr(SecurityAgent, "run", lambda self, context: context)
    monkeypatch.setattr("multiagent.benchmark._run_pytest", lambda path: True)

    results = BenchmarkRunner(
        [BenchmarkModelConfig(name="fake", provider="ollama", model="fake")]
    ).run(repo, "fix answer")

    assert results[0].diff_generated is True
    assert results[0].tests_passed is True
    assert results[0].score > 0
    assert source.read_text(encoding="utf-8") == "def answer():\n    return 41\n"
