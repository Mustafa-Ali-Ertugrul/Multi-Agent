"""Tests for orchestrator error boundary (Faz 1.1, 1.2, 1.5)."""

from pathlib import Path

from multiagent.agents.base import Agent, AgentError
from multiagent.context.store import ContextStore
from multiagent.orchestrator.core import Orchestrator

# ---------------------------------------------------------------------------
# 1.1 — Orchestrator error boundary
# ---------------------------------------------------------------------------


class _FailingAgent(Agent):
    """Agent that always raises a plain Exception."""

    @property
    def name(self) -> str:
        return "failing"

    def run(self, context: ContextStore) -> ContextStore:
        raise RuntimeError("boom")


class _PassingAgent(Agent):
    """Agent that appends a decision and returns the context."""

    @property
    def name(self) -> str:
        return "passing"

    def run(self, context: ContextStore) -> ContextStore:
        context.decisions.append("passing-decision")
        return context


def test_fail_fast_raises_on_first_agent_error(tmp_path: Path) -> None:
    """fail_fast=True (default) — agent hatası pipeline'i durdurur."""
    agent_fail = _FailingAgent()

    context = ContextStore(repo_path=tmp_path)
    orch = Orchestrator(agents=[agent_fail], fail_fast=True)

    raised = False
    try:
        orch.run(context)
    except AgentError as exc:
        raised = True
        assert "failing" in exc.agent_name
        assert "boom" in str(exc)
    assert raised is True


def test_fail_fast_passes_first_then_fails(tmp_path: Path) -> None:
    """fail_fast=True — ilk agent başarılı, ikinci hata verirse pipeline durur."""
    agent1 = _PassingAgent()
    agent2 = _FailingAgent()

    context = ContextStore(repo_path=tmp_path)
    orch = Orchestrator(agents=[agent1, agent2], fail_fast=True)

    raised = False
    try:
        orch.run(context)
    except AgentError as exc:
        raised = True
        assert "failing" in exc.agent_name

    assert raised is True
    assert "passing-decision" in context.decisions


def test_continue_on_error_records_trace_and_continues(tmp_path: Path) -> None:
    """fail_fast=False — hatayı trace'e kaydeder, sonraki agent'lar çalışır."""
    agent1 = _PassingAgent()
    agent2 = _FailingAgent()
    agent3 = _PassingAgent()

    context = ContextStore(repo_path=tmp_path)
    orch = Orchestrator(
        agents=[agent1, agent2, agent3],
        fail_fast=False,
    )

    final = orch.run(context)

    # agent1 and agent3 decisions should be present
    assert final.decisions.count("passing-decision") == 2

    # agent2 error should be recorded in trace
    error_traces = [t for t in final.agent_trace if t.action == "error"]
    assert len(error_traces) == 1
    assert "boom" in error_traces[0].reason


def test_agent_error_propagates_directly(tmp_path: Path) -> None:
    """AgentError doğrudan propagate olur (çift sarmalanmaz)."""

    class AgentRaisingAgentError(Agent):
        @property
        def name(self) -> str:
            return "agent-error"

        def run(self, context: ContextStore) -> ContextStore:
            raise AgentError("agent-error", " intentional failure")

    orch = Orchestrator(
        agents=[AgentRaisingAgentError()],
        fail_fast=True,
    )
    raised = False
    try:
        orch.run(ContextStore(repo_path=tmp_path))
    except AgentError as exc:
        raised = True
        assert exc.agent_name == "agent-error"
    assert raised is True


# ---------------------------------------------------------------------------
# 1.2 — Snapshot / rollback (BuildAgent)
# ---------------------------------------------------------------------------


def test_build_rollback_on_failed_hunk(tmp_path: Path) -> None:
    """UnifiedDiffApplier hata verirse dosyalar eski haline döner."""
    from multiagent.agents.build import BuildError, UnifiedDiffApplier

    target = tmp_path / "test.py"
    target.write_text("line1\nline2\nline3\n")

    # Diff with invalid context lines — should cause BuildError
    bad_diff = """\
--- a/test.py
+++ b/test.py
@@ -10,3 +10,3 @@
 nonexistent line
-other line
+new line
"""
    raised = False
    try:
        UnifiedDiffApplier.apply(tmp_path, bad_diff)
    except BuildError:
        raised = True

    assert raised is True
    # File must be unchanged after rollback
    assert target.read_text() == "line1\nline2\nline3\n"


# ---------------------------------------------------------------------------
# 1.5 — Config llm_failure_mode
# ---------------------------------------------------------------------------


def test_config_default_failure_mode(tmp_path: Path) -> None:
    from multiagent.config import load_config

    config = load_config(tmp_path / "nonexistent.toml")
    assert config.llm_failure_mode == "fallback"


def test_config_reads_failure_mode(tmp_path: Path) -> None:
    from multiagent.config import load_config

    toml = tmp_path / "m.toml"
    toml.write_text('[multiagent]\nllm_failure_mode = "fallback"\n')
    config = load_config(toml)
    assert config.llm_failure_mode == "fallback"


def test_config_rejects_invalid_failure_mode(tmp_path: Path) -> None:
    from multiagent.config import load_config

    toml = tmp_path / "m.toml"
    toml.write_text('[multiagent]\nllm_failure_mode = "unknown"\n')
    config = load_config(toml)
    # Should fall back to default
    assert config.llm_failure_mode == "fallback"
