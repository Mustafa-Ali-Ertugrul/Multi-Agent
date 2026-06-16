from __future__ import annotations

from pathlib import Path

from multiagent.agents.build import BuildAgent
from multiagent.context.store import ContextStore, Finding
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
        return (
            "--- a/app.py\n"
            "+++ b/app.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def answer() -> int:\n"
            "-    return 41\n"
            "+    return 42\n"
        )


def test_build_agent_adds_suggested_diff_without_applying_it(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text("def answer() -> int:\n    return 41\n", encoding="utf-8")

    context = ContextStore(
        repo_path=tmp_path,
        files={"app.py": source.read_text(encoding="utf-8")},
        findings=[
            Finding(
                severity="medium",
                file="app.py",
                line=2,
                message="Return value should be updated.",
                source="test",
            )
        ],
        decisions=["Test ozeti: basarisiz."],
    )
    llm = FakeLLM()

    result = BuildAgent(llm=llm).run(context)

    assert source.read_text(encoding="utf-8") == "def answer() -> int:\n    return 41\n"
    assert len(result.decisions) == 2
    assert result.decisions[-1].startswith("Onerilen degisiklik")
    assert "--- a/app.py" in result.decisions[-1]
    assert len(llm.messages) == 2
    assert "Return value should be updated." in str(llm.messages[1]["content"])
