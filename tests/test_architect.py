from __future__ import annotations

from pathlib import Path

from multiagent.agents.architect import ArchitectAgent
from multiagent.context.store import ContextStore
from multiagent.llm.gateway import LLMGateway


class FakeLLM(LLMGateway):
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    def chat(
        self,
        messages: list[dict[str, object]],
        temperature: float = 0.2,
        max_retries: int = 3,
    ) -> str:
        self.messages = messages
        return "Mimari ozet raporu."


def test_architect_adds_architecture_summary_to_decisions(tmp_path: Path) -> None:
    context = ContextStore(
        repo_path=tmp_path,
        files={
            "src/app.py": (
                "import os\n\n"
                "class Service:\n"
                "    pass\n\n"
                "def run() -> None:\n"
                "    pass\n"
            )
        },
    )
    llm = FakeLLM()

    result = ArchitectAgent(llm=llm).run(context)

    assert result.decisions == ["Mimari ozet raporu."]
    assert len(llm.messages) == 2
    user_message = llm.messages[1]
    assert "src/app.py" in str(user_message["content"])
    assert "Service" in str(user_message["content"])
    assert "run" in str(user_message["content"])
