"""Regression tests for the 5 bug fixes from the extreme test report.

Verifies the fixes for:
- Bug 1: CoordinatorAgent AgentError trace records str(exc), not agent repr
- Bug 2: \\r\\n line endings in unified diffs are normalized to \\n
- Bug 3: benchmark subprocess has timeout + TimeoutExpired handling
- Bug 4: run_id is unique across rapid same-millisecond creations
- Bug 5: max_retries=0/-N clamps to 1 (no misleading "unknown" error)
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch


def test_coordinator_agent_error_trace_records_str_exc(tmp_path: Path) -> None:
    """Bug 1: CoordinatorAgent + AgentError + fail_fast=False records str(exc)."""
    from multiagent.agents.base import Agent, AgentError
    from multiagent.agents.coordinator import CoordinatorAgent
    from multiagent.context.store import ContextStore

    class FailingMemoryAgent(Agent):
        @property
        def name(self) -> str:
            return "memory"

        def run(self, context):  # type: ignore[override]
            raise AgentError("memory", "specific AgentError message XYZ")

    agent_map = {"memory": FailingMemoryAgent()}
    coord = CoordinatorAgent(agents=agent_map, fail_fast=False)
    context = ContextStore(repo_path=tmp_path)
    coord.run(context)

    error_traces = [t for t in context.agent_trace if t.action == "error"]
    assert len(error_traces) == 1
    reason = error_traces[0].reason
    assert "specific AgentError message XYZ" in reason
    assert "FailingMemoryAgent" not in reason
    assert "0x" not in reason


def test_crlf_diff_applies_normally(tmp_path: Path) -> None:
    """Bug 2: \\r\\n line endings in diff are normalized before parsing."""
    from multiagent.agents.build import UnifiedDiffApplier

    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "app.py"
    target.write_text("x = 1\ny = 2\n", encoding="utf-8")

    diff_crlf = (
        "--- a/app.py\n+++ b/app.py\n@@ -1,2 +1,2 @@\n x = 1\n-y = 2\n+y = 3\n"
    ).replace("\n", "\r\n")
    UnifiedDiffApplier.apply(repo, diff_crlf)
    assert target.read_text(encoding="utf-8") == "x = 1\ny = 3\n"


def test_benchmark_timeout_returns_false(tmp_path: Path, monkeypatch) -> None:
    """Bug 3: subprocess.TimeoutExpired handled gracefully (no crash)."""
    from multiagent.benchmark import _run_pytest

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "test_x.py").write_text("def test_ok(): assert True\n", encoding="utf-8")

    def fake_run(*args, **kwargs):
        assert "timeout" in kwargs
        assert kwargs["timeout"] == 120
        raise subprocess.TimeoutExpired(cmd="pytest", timeout=120)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _run_pytest(repo)
    assert result is False


def test_run_id_unique_across_rapid_creations() -> None:
    """Bug 4: run_id is unique even when stores are created in same millisecond."""
    from multiagent.context.store import ContextStore

    ids: set[str] = set()
    for _ in range(100):
        store = ContextStore(repo_path=Path("."))
        ids.add(store.run_id)

    assert len(ids) == 100
    sample = next(iter(ids))
    parts = sample.split("-")
    assert len(parts) == 2
    assert len(parts[1]) == 8
    int(parts[0])  # ms part must parse
    int(parts[1], 16)  # suffix must be hex


def test_max_retries_zero_clamps_to_one_attempt() -> None:
    """Bug 5a: max_retries=0 clamps to 1 attempt, raises real error."""
    from multiagent.llm.gateway import LLMError, LLMGateway

    gateway = LLMGateway(model="test-model")
    call_count = 0

    def always_fail(messages, temperature):
        nonlocal call_count
        call_count += 1
        raise LLMError("real error")

    with patch.object(gateway, "_chat_ollama", side_effect=always_fail):
        with patch("multiagent.llm.gateway.time.sleep"):
            raised_msg: str | None = None
            try:
                gateway.chat(
                    messages=[{"role": "user", "content": "hi"}],
                    max_retries=0,
                )
            except LLMError as exc:
                raised_msg = str(exc)

    assert raised_msg == "real error"
    assert "bilinmeyen" not in (raised_msg or "").lower()
    assert call_count == 1


def test_max_retries_negative_clamps_to_one() -> None:
    """Bug 5b: max_retries=-N clamps to 1 attempt, no misleading unknown error."""
    from multiagent.llm.gateway import LLMError, LLMGateway

    gateway = LLMGateway(model="test-model")
    call_count = 0

    def always_fail(messages, temperature):
        nonlocal call_count
        call_count += 1
        raise LLMError("transient")

    with patch.object(gateway, "_chat_ollama", side_effect=always_fail):
        with patch("multiagent.llm.gateway.time.sleep"):
            raised = False
            try:
                gateway.chat(
                    messages=[{"role": "user", "content": "hi"}],
                    max_retries=-5,
                )
            except LLMError:
                raised = True

    assert raised is True
    assert call_count == 1
