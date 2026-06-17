from __future__ import annotations

import time

from multiagent.agents.base import Agent, AgentError
from multiagent.context.store import ContextStore
from multiagent.log import get_logger

log = get_logger("coordinator")


class CoordinatorAgent(Agent):
    """Policy-driven orchestrator that conditionally runs agents.

    Evaluates repository heuristics (file counts, graph size, findings)
    to decide which agents should run and in what order.
    """

    def __init__(
        self,
        agents: dict[str, Agent],
        knowledge_graph_enabled: bool = True,
        security_enabled: bool = True,
        open_pr: bool = False,
        apply_changes: bool = False,
        rerun_tests_after_apply: bool = False,
        fail_fast: bool = True,
    ) -> None:
        super().__init__()
        self.agents = agents
        self.knowledge_graph_enabled = knowledge_graph_enabled
        self.security_enabled = security_enabled
        self.open_pr = open_pr
        self.apply_changes = apply_changes
        self.rerun_tests_after_apply = rerun_tests_after_apply
        self.fail_fast = fail_fast

    @property
    def name(self) -> str:
        return "coordinator"

    def run(self, context: ContextStore) -> ContextStore:
        current = context
        current = self._maybe_run(
            current,
            "memory",
            "memory" in self.agents,
            "memory enabled",
        )
        current = self._maybe_run(
            current,
            "knowledge-graph",
            self.knowledge_graph_enabled,
            "knowledge graph enabled",
        )
        current = self._maybe_run(
            current,
            "security",
            self.security_enabled,
            "security enabled by coordinator policy",
        )
        current = self._maybe_run(
            current,
            "reviewer",
            self._has_python_files(current),
            "python files detected",
        )
        current = self._maybe_run(
            current,
            "architect",
            self._should_run_architect(current),
            "multi-module or graph-rich repo detected",
        )
        current = self._maybe_run(
            current,
            "test-runner",
            self._has_tests(current),
            "test files detected",
        )
        current = self._maybe_run(
            current,
            "build",
            self._should_run_build(current),
            "findings or actionable decisions detected",
        )

        if self.apply_changes and self.rerun_tests_after_apply:
            current = self._run_agent(
                current,
                "test-runner",
                "rerun after apply",
                action="rerun",
            )

        current = self._maybe_run(
            current,
            "github_pr",
            self.open_pr,
            "PR requested",
        )
        return current

    def _maybe_run(
        self, context: ContextStore, name: str, condition: bool, reason: str
    ) -> ContextStore:
        if name not in self.agents:
            context.add_trace(name, "skip", "agent unavailable")
            return context
        if not condition:
            context.add_trace(name, "skip", reason)
            return context
        return self._run_agent(context, name, reason)

    def _run_agent(
        self,
        context: ContextStore,
        name: str,
        reason: str,
        action: str = "run",
    ) -> ContextStore:
        log.info("coordinator %s agent: %s (%s)", action, name, reason)
        context.add_trace(name, action, reason)
        start = time.monotonic()
        try:
            return self.agents[name].run(context)
        except AgentError:
            elapsed = time.monotonic() - start
            log.warning(
                "agent %s raised AgentError after %.2fs", name, elapsed
            )
            if self.fail_fast:
                raise
            context.add_trace(name, "error", str(self.agents[name]))
            return context
        except Exception as exc:
            elapsed = time.monotonic() - start
            log.warning("agent %s failed after %.2fs: %s", name, elapsed, exc)
            context.add_trace(name, "error", str(exc))
            if self.fail_fast:
                raise AgentError(name, str(exc), cause=exc) from exc
            return context

    @staticmethod
    def _has_python_files(context: ContextStore) -> bool:
        return any(path.endswith(".py") for path in context.files)

    @staticmethod
    def _has_tests(context: ContextStore) -> bool:
        return any(
            path.endswith(".py")
            and (
                path.startswith("test_")
                or "/test_" in path
                or path.startswith("tests/")
            )
            for path in context.files
        )

    @staticmethod
    def _should_run_architect(context: ContextStore) -> bool:
        python_files = [path for path in context.files if path.endswith(".py")]
        graph_nodes = (
            len(context.knowledge_graph.nodes) if context.knowledge_graph else 0
        )
        return len(python_files) > 1 or graph_nodes > 5

    @staticmethod
    def _should_run_build(context: ContextStore) -> bool:
        if any(finding.severity in {"high", "medium"} for finding in context.findings):
            return True
        actionable_terms = ("fix", "duzelt", "refactor", "unified diff", "apply")
        return any(
            any(term in decision.lower() for term in actionable_terms)
            for decision in context.decisions
        )
