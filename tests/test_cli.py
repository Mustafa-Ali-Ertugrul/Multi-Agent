from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch, raises

from multiagent.agents.architect import ArchitectAgent
from multiagent.agents.build import BuildAgent
from multiagent.agents.coordinator import CoordinatorAgent
from multiagent.agents.memory import MemoryAgent
from multiagent.agents.reviewer import ReviewerAgent
from multiagent.agents.test_runner import TestRunnerAgent
from multiagent.cli import _analyze, _build_parser
from multiagent.context.store import ContextStore
from multiagent.llm.gateway import LLMGateway


class FakeLLM(LLMGateway):
    def __init__(self) -> None:
        pass

    def chat(
        self,
        messages: list[dict[str, object]],
        temperature: float = 0.2,
        max_retries: int = 3,
    ) -> str:
        return "fake response"


def test_build_parser_has_new_arguments() -> None:
    parser = _build_parser()
    args = parser.parse_args(["analyze", "src", "--agents", "reviewer,build"])
    assert args.command == "analyze"
    assert args.repo_path == Path("src")
    assert args.agents == "reviewer,build"
    assert args.apply is False

    args = parser.parse_args(["analyze", "src", "--apply"])
    assert args.apply is True
    assert args.agents is None

    args = parser.parse_args(
        [
            "analyze",
            "src",
            "--coordinator",
            "--memory",
            "--security",
            "--knowledge-graph",
            "--task",
            "auth fix",
        ]
    )
    assert args.coordinator is True
    assert args.memory is True
    assert args.security is True
    assert args.knowledge_graph is True
    assert args.task == "auth fix"

    args = parser.parse_args(
        ["benchmark", "src", "--task", "fix", "--models", "qwen,deepseek"]
    )
    assert args.command == "benchmark"
    assert args.models == "qwen,deepseek"


def test_analyze_runs_filtered_agents(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(LLMGateway, "from_env", lambda *args, **kwargs: FakeLLM())

    executed_agents: list[str] = []

    def fake_reviewer_run(self: ReviewerAgent, context: ContextStore) -> ContextStore:
        executed_agents.append("reviewer")
        return context

    monkeypatch.setattr(ReviewerAgent, "run", fake_reviewer_run)

    def fake_architect_run(self: ArchitectAgent, context: ContextStore) -> ContextStore:
        executed_agents.append("architect")
        return context

    monkeypatch.setattr(ArchitectAgent, "run", fake_architect_run)

    def fake_test_runner_run(
        self: TestRunnerAgent, context: ContextStore
    ) -> ContextStore:
        executed_agents.append("test-runner")
        return context

    monkeypatch.setattr(TestRunnerAgent, "run", fake_test_runner_run)

    def fake_build_run(self: BuildAgent, context: ContextStore) -> ContextStore:
        executed_agents.append("build")
        return context

    monkeypatch.setattr(BuildAgent, "run", fake_build_run)

    parser = _build_parser()

    args = parser.parse_args(["analyze", str(tmp_path)])
    _analyze(args)
    assert executed_agents == ["reviewer", "architect", "test-runner", "build"]

    executed_agents.clear()
    args = parser.parse_args(["analyze", str(tmp_path), "--agents", "build,reviewer"])
    _analyze(args)
    assert executed_agents == ["reviewer", "build"]

    args = parser.parse_args(["analyze", str(tmp_path), "--agents", "invalid-agent"])
    with raises(SystemExit):
        _analyze(args)


def test_analyze_runs_coordinator_and_persists_memory(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(LLMGateway, "from_env", lambda *args, **kwargs: FakeLLM())
    calls: list[str] = []

    def fake_coordinator_run(
        self: CoordinatorAgent, context: ContextStore
    ) -> ContextStore:
        calls.append("coordinator")
        context.decisions.append("coordinated")
        return context

    def fake_memory_persist(self: MemoryAgent, context: ContextStore) -> None:
        calls.append("memory-persist")

    monkeypatch.setattr(CoordinatorAgent, "run", fake_coordinator_run)
    monkeypatch.setattr(MemoryAgent, "persist", fake_memory_persist)

    parser = _build_parser()
    args = parser.parse_args(
        [
            "analyze",
            str(tmp_path),
            "--coordinator",
            "--memory",
            "--task",
            "auth",
        ]
    )
    _analyze(args)

    assert calls == ["coordinator", "memory-persist"]


def test_analyze_coordinator_respects_explicit_agent_filter(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(LLMGateway, "from_env", lambda *args, **kwargs: FakeLLM())
    captured_agents: list[list[str]] = []

    def fake_coordinator_run(
        self: CoordinatorAgent, context: ContextStore
    ) -> ContextStore:
        captured_agents.append(sorted(self.agents))
        return context

    monkeypatch.setattr(CoordinatorAgent, "run", fake_coordinator_run)

    parser = _build_parser()
    args = parser.parse_args(
        [
            "analyze",
            str(tmp_path),
            "--coordinator",
            "--agents",
            "memory,security",
            "--memory",
            "--security",
        ]
    )
    _analyze(args)

    assert captured_agents == [["knowledge-graph", "memory", "security"]]
