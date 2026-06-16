from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from pytest import MonkeyPatch

from multiagent.agents.test_runner import TestRunnerAgent
from multiagent.context.store import ContextStore
from multiagent.llm.gateway import LLMGateway


class FakeLLM(LLMGateway):
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    def chat(
        self,
        messages: list[dict[str, object]],
        temperature: float = 0.2,
    ) -> str:
        self.messages = messages
        return "```python\ndef test_example() -> None:\n    assert True\n```"


def test_test_runner_parses_pytest_failure_and_requests_suggestions(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    context = ContextStore(
        repo_path=tmp_path,
        files={"app.py": "def add(a: int, b: int) -> int:\n    return a + b\n"},
    )
    pytest_output = "\n".join(
        [
            "test session starts",
            "collected 3 items",
            "",
            "tests/test_app.py .F",
            "",
            "FAILURES",
            "FAILED tests/test_app.py::test_add - AssertionError",
            "1 failed, 2 passed in 0.10s",
        ]
    )

    def fake_run(
        args: list[str],
        cwd: Path,
        capture_output: bool,
        check: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert args == ["pytest"]
        assert cwd == tmp_path
        assert capture_output is True
        assert check is False
        assert text is True
        return subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout=pytest_output,
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    llm = FakeLLM()

    result = TestRunnerAgent(llm=llm).run(context)

    assert len(result.findings) == 1
    assert result.findings[0].severity == "high"
    assert result.findings[0].message == "pytest basarisiz: 1 failed, 0 errors."
    assert result.decisions[0] == (
        "Test ozeti: basarisiz. 2 gecti, 1 kaldi, 0 hata, 0 atlandi."
    )
    assert result.decisions[1].startswith("```python")
    assert result.decisions[1].startswith("```python")
    assert len(llm.messages) == 2
    assert "app.py" in str(llm.messages[1]["content"])


def test_test_runner_mcp_success(tmp_path: Path) -> None:
    from unittest.mock import AsyncMock

    from multiagent.mcp.client import ToolSpec

    tools = AsyncMock()
    tools.__aenter__.return_value = tools

    mock_tool = ToolSpec(name="pytest", description="", input_schema={})
    tools.list_tools = AsyncMock(return_value=[mock_tool])
    tools.call_tool = AsyncMock(return_value="MCP pytest passed")

    agent = TestRunnerAgent(llm=FakeLLM(), tools=tools)
    context = ContextStore(repo_path=tmp_path)

    result = agent.run(context)

    assert "MCP Test Analizi Sonuclari:\nMCP pytest passed" in result.decisions
    tools.call_tool.assert_awaited_once_with("pytest", {"path": str(tmp_path)})


def test_test_runner_mcp_fallback(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    from unittest.mock import AsyncMock

    from multiagent.mcp.client import ToolSpec

    tools = AsyncMock()
    tools.__aenter__.return_value = tools

    mock_tool = ToolSpec(name="run_tests", description="", input_schema={})
    tools.list_tools = AsyncMock(return_value=[mock_tool])
    tools.call_tool = AsyncMock(side_effect=Exception("ConnectionRefused"))

    agent = TestRunnerAgent(llm=FakeLLM(), tools=tools, require_mcp=False)
    context = ContextStore(repo_path=tmp_path)

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout="collected 0 items\n"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = agent.run(context)

    fallback_decision = next(
        d for d in result.decisions if "MCP araci kullanilamadi" in d
    )
    assert "ConnectionRefused" in fallback_decision
    assert len(result.decisions) == 3


def test_test_runner_mcp_require_hard_fail(tmp_path: Path) -> None:
    from unittest.mock import AsyncMock

    from multiagent.agents.test_runner import TestRunnerError

    tools = AsyncMock()
    tools.__aenter__.return_value = tools
    tools.list_tools = AsyncMock(return_value=[])  # No matching tool

    agent = TestRunnerAgent(llm=FakeLLM(), tools=tools, require_mcp=True)
    context = ContextStore(repo_path=tmp_path)

    import pytest

    with pytest.raises(TestRunnerError, match="Beklenen MCP araci bulunamadi"):
        agent.run(context)
