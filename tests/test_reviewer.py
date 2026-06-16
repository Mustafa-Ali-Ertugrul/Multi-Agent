from __future__ import annotations

import subprocess
from pathlib import Path

from pytest import MonkeyPatch

from multiagent.agents.reviewer import ReviewerAgent
from multiagent.context.store import ContextStore
from multiagent.llm.gateway import LLMGateway


class FakeLLM(LLMGateway):
    def __init__(self) -> None:
        pass

    def chat(
        self,
        messages: list[dict[str, object]],
        temperature: float = 0.2,
    ) -> str:
        return "Kısa güvenlik özeti."


def test_reviewer_converts_bandit_results_to_findings(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    source_path = tmp_path / "app.py"
    source_path.write_text("import subprocess\n", encoding="utf-8")

    store = ContextStore(repo_path=tmp_path, files={"app.py": source_path.read_text()})

    bandit_json = (
        '{"results": ['
        '{"filename": "'
        + source_path.as_posix()
        + '", "line_number": 1, "issue_text": "subprocess call", '
        '"issue_severity": "HIGH", "test_id": "B404"}'
        "]}"
    )

    def fake_run(
        args: list[str],
        capture_output: bool,
        check: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert args == ["bandit", "-f", "json", "-q", str(source_path)]
        assert capture_output is True
        assert check is False
        assert text is True
        return subprocess.CompletedProcess(args=args, returncode=1, stdout=bandit_json)

    monkeypatch.setattr(subprocess, "run", fake_run)

    agent = ReviewerAgent(llm=FakeLLM())
    result = agent.run(store)

    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.severity == "high"
    assert finding.file == "app.py"
    assert finding.line == 1
    assert finding.message == "subprocess call"
    assert finding.source == "bandit:B404"
    assert result.decisions == ["Kısa güvenlik özeti."]
