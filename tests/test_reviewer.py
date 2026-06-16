from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

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


def test_reviewer_mcp_success(tmp_path: Path) -> None:
    from unittest.mock import AsyncMock

    from multiagent.mcp.client import ToolSpec

    tools = AsyncMock()
    tools.__aenter__.return_value = tools

    mock_tool = ToolSpec(name="security_scan", description="", input_schema={})
    tools.list_tools = AsyncMock(return_value=[mock_tool])
    tools.call_tool = AsyncMock(return_value="MCP security OK")

    agent = ReviewerAgent(llm=FakeLLM(), tools=tools)
    store = ContextStore(repo_path=tmp_path)

    result = agent.run(store)

    assert "MCP Guvenlik Analizi Sonuclari:\nMCP security OK" in result.decisions
    tools.call_tool.assert_awaited_once_with("security_scan", {"path": str(tmp_path)})


def test_reviewer_mcp_fallback(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    from unittest.mock import AsyncMock

    from multiagent.mcp.client import ToolSpec

    tools = AsyncMock()
    tools.__aenter__.return_value = tools

    mock_tool = ToolSpec(name="security_scan", description="", input_schema={})
    tools.list_tools = AsyncMock(return_value=[mock_tool])
    tools.call_tool = AsyncMock(side_effect=Exception("Timeout"))

    agent = ReviewerAgent(llm=FakeLLM(), tools=tools, require_mcp=False)
    source_path = tmp_path / "app.py"
    source_path.write_text("x=1", encoding="utf-8")
    store = ContextStore(repo_path=tmp_path, files={"app.py": "x=1"})

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout='{"results": []}'
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = agent.run(store)

    fallback_decision = next(
        d for d in result.decisions if "MCP araci kullanilamadi" in d
    )
    assert "Timeout" in fallback_decision
    # 2 decisions: 1 from fallback, 1 from local LLM summarize
    assert len(result.decisions) == 2


def test_reviewer_mcp_require_hard_fail(tmp_path: Path) -> None:
    from unittest.mock import AsyncMock

    from multiagent.agents.reviewer import ReviewerError

    tools = AsyncMock()
    tools.__aenter__.return_value = tools
    tools.list_tools = AsyncMock(return_value=[])  # No matching tool

    agent = ReviewerAgent(llm=FakeLLM(), tools=tools, require_mcp=True)
    store = ContextStore(repo_path=tmp_path)

    import pytest

    with pytest.raises(ReviewerError, match="Beklenen MCP araci bulunamadi"):
        agent.run(store)
