from __future__ import annotations

import sys
import time

from multiagent.agents.base import Agent, AgentError
from multiagent.context.store import ContextStore
from multiagent.log import get_logger

log = get_logger("orchestrator")


class Orchestrator:
    """Runs a sequence of agents with configurable error handling.

    Parameters
    ----------
    agents:
        Ordered list of agents to execute.
    fail_fast:
        If *True* (default), the first agent error aborts the pipeline.
        If *False*, errors are recorded in ``context.agent_trace`` and
        the remaining agents continue.
    """

    def __init__(
        self,
        agents: list[Agent],
        *,
        fail_fast: bool = True,
    ) -> None:
        self.agents = agents
        self.fail_fast = fail_fast

    def run(self, context: ContextStore) -> ContextStore:
        current_context = context

        for agent in self.agents:
            agent_name = agent.name
            log.info("running agent: %s", agent_name)
            current_context.add_trace(agent_name, "start", "running")
            start_time = time.monotonic()

            try:
                current_context = agent.run(current_context)
                elapsed = time.monotonic() - start_time
                log.info("agent %s completed in %.2fs", agent_name, elapsed)
                current_context.add_trace(
                    agent_name, "success", f"completed in {elapsed:.2f}s"
                )
            except AgentError:
                # Already wrapped — re-raise or record depending on policy.
                elapsed = time.monotonic() - start_time
                exc = sys.exc_info()[1]
                log.warning(
                    "agent %s raised AgentError after %.2fs: %s",
                    agent_name,
                    elapsed,
                    exc,
                )
                if self.fail_fast:
                    raise
                current_context.add_trace(
                    agent_name,
                    "error",
                    str(exc),
                )
            except Exception as exc:
                elapsed = time.monotonic() - start_time
                log.warning(
                    "agent %s failed after %.2fs: %s",
                    agent_name,
                    elapsed,
                    exc,
                )
                current_context.add_trace(
                    agent_name,
                    "error",
                    str(exc),
                )
                if self.fail_fast:
                    raise AgentError(agent_name, str(exc), cause=exc) from exc

        return current_context
