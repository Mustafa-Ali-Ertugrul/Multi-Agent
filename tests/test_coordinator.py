from __future__ import annotations

from pathlib import Path

from multiagent.agents.base import Agent
from multiagent.agents.coordinator import CoordinatorAgent
from multiagent.context.store import ContextStore, Finding


class RecordingAgent(Agent):
    def __init__(self, name: str, finding: Finding | None = None) -> None:
        super().__init__()
        self._name = name
        self.finding = finding
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    def run(self, context: ContextStore) -> ContextStore:
        self.calls += 1
        if self.finding is not None:
            context.add_finding(self.finding)
        return context


def test_coordinator_runs_and_skips_agents_by_policy(tmp_path: Path) -> None:
    context = ContextStore(repo_path=tmp_path)
    context.files = {"app.py": "print('hi')\n", "test_app.py": "def test_ok(): pass\n"}
    security = RecordingAgent(
        "security",
        Finding(
            severity="high",
            file="app.py",
            line=1,
            message="problem",
            source="security:secret",
        ),
    )
    build = RecordingAgent("build")
    agents: dict[str, Agent] = {
        "security": security,
        "reviewer": RecordingAgent("reviewer"),
        "architect": RecordingAgent("architect"),
        "test-runner": RecordingAgent("test-runner"),
        "build": build,
    }

    CoordinatorAgent(
        agents=agents,
        knowledge_graph_enabled=False,
        security_enabled=True,
    ).run(context)

    assert security.calls == 1
    assert build.calls == 1
    assert any(
        trace.agent == "knowledge-graph" and trace.action == "skip"
        for trace in context.agent_trace
    )
