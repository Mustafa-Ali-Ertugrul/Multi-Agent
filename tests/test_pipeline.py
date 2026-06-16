import subprocess
from pathlib import Path
from unittest.mock import patch

from pytest import MonkeyPatch

from multiagent.agents.architect import ArchitectAgent
from multiagent.agents.build import BuildAgent
from multiagent.agents.github_pr import GitHubPRAgent
from multiagent.agents.reviewer import ReviewerAgent
from multiagent.agents.test_runner import TestRunnerAgent
from multiagent.context.store import ContextStore
from multiagent.llm.gateway import LLMGateway
from multiagent.orchestrator.core import Orchestrator


class FakeLLM(LLMGateway):
    def __init__(self) -> None:
        pass

    def chat(self, messages: list[dict[str, object]], temperature: float = 0.2) -> str:
        content = ""
        for msg in messages:
            content += str(msg.get("content", ""))

        if (
            "Asagidaki kararlara ve bulgulara dayanarak bir GitHub Pull Request"
            in content
        ):
            return '{"title": "E2E PR", "body": "End to end PR body"}'
        elif "unified diff formatinda" in content:
            return """Onerilen degisiklik (unified diff):
--- a/main.py
+++ b/main.py
@@ -1,2 +1,2 @@
-print("old")
+print("new")
"""
        return "Fake LLM decision"


def test_end_to_end_pipeline(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "fake_token_for_test")

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "main.py").write_text('print("old")\n')

    original_run = subprocess.run

    from typing import Any

    def mock_run(*args: Any, **kwargs: Any) -> Any:
        cmd = args[0] if args else kwargs.get("args", [])
        if "bandit" in cmd:
            bandit_out = (
                '{"results": [{"issue_severity": "HIGH", "filename": "main.py", '
                '"line_number": 1, "issue_text": "Bad code", "test_id": "B101"}]}'
            )
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=1,
                stdout=bandit_out,
            )
        elif "pytest" in cmd:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=1,
                stdout="1 failed\n== FAILURES ==",
            )
        return original_run(cmd, *args, **kwargs)

    with patch("subprocess.run", side_effect=mock_run):
        llm = FakeLLM()

        agents = [
            ReviewerAgent(llm=llm),
            ArchitectAgent(llm=llm),
            TestRunnerAgent(llm=llm),
            BuildAgent(llm=llm, apply=False),
        ]

        orchestrator = Orchestrator(llm=llm, agents=agents)

        context = ContextStore(repo_path=repo_dir)
        context.load_repo(repo_dir)

        final_context = orchestrator.run(context)

        assert len(final_context.findings) > 0
        finding_sources = {f.source for f in final_context.findings}
        assert "bandit:B101" in finding_sources
        assert "pytest" in finding_sources

        assert len(final_context.decisions) > 0

        diff_decision = any(
            "Onerilen degisiklik (unified diff):" in str(d)
            for d in final_context.decisions
        )
        assert diff_decision is True


def test_github_pr_agent_dry_run(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "fake_token")

    llm = FakeLLM()
    agent = GitHubPRAgent(llm=llm, dry_run=True)

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    context = ContextStore(repo_path=repo_dir)
    context.decisions.append(
        "Onerilen degisiklik (unified diff):\n"
        "--- a/file\n+++ b/file\n@@ -1 +1 @@\n-a\n+b"
    )

    final_context = agent.run(context)

    dry_run_decision = any("[DRY RUN]" in str(d) for d in final_context.decisions)
    assert dry_run_decision is True
