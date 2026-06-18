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
        max_retries: int = 3,
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


def test_unified_diff_applier_creates_new_file(tmp_path: Path) -> None:
    """--- /dev/null diff'i yeni dosya olusturur."""
    from multiagent.agents.build import UnifiedDiffApplier

    new_diff = (
        "--- /dev/null\n"
        "+++ b/new_module.py\n"
        "@@ -0,0 +1,3 @@\n"
        "+def greet() -> str:\n"
        '+    return "hi"\n'
        "+\n"
    )

    UnifiedDiffApplier.apply(tmp_path, new_diff)

    created = tmp_path / "new_module.py"
    assert created.exists()
    expected = 'def greet() -> str:\n    return "hi"\n\n'
    assert created.read_text(encoding="utf-8") == expected


def test_unified_diff_applier_creates_new_file_in_nested_dir(tmp_path: Path) -> None:
    """Yeni dosya icin ara dizinler otomatik olusturulur."""
    from multiagent.agents.build import UnifiedDiffApplier

    new_diff = "--- /dev/null\n+++ b/utils/helpers.py\n@@ -0,0 +1,1 @@\n+x = 1\n"

    UnifiedDiffApplier.apply(tmp_path, new_diff)

    created = tmp_path / "utils" / "helpers.py"
    assert created.exists()
    assert created.read_text(encoding="utf-8") == "x = 1\n"


def test_unified_diff_applier_rejects_path_traversal_in_new_file(
    tmp_path: Path,
) -> None:
    """Yeni dosya yolu da repo disina cikamaz."""
    from multiagent.agents.build import BuildError, UnifiedDiffApplier

    bad_diff = "--- /dev/null\n+++ b/../escape.py\n@@ -0,0 +1,1 @@\n+x = 1\n"

    import pytest

    with pytest.raises(BuildError):
        UnifiedDiffApplier.apply(tmp_path, bad_diff)


def test_unified_diff_applier_deletes_existing_file(tmp_path: Path) -> None:
    """+++ /dev/null diff'i mevcut dosyayi siler."""
    from multiagent.agents.build import UnifiedDiffApplier

    target = tmp_path / "old_module.py"
    target.write_text("def old():\n    return 1\n", encoding="utf-8")

    delete_diff = (
        "--- a/old_module.py\n"
        "+++ /dev/null\n"
        "@@ -1,2 +0,0 @@\n"
        "-def old():\n"
        "-    return 1\n"
    )

    UnifiedDiffApplier.apply(tmp_path, delete_diff)
    assert not target.exists()


def test_unified_diff_applier_rolls_back_deletion_on_failure(
    tmp_path: Path,
) -> None:
    """Silme basarili ama sonraki dosyada hata varsa, silinen dosya geri gelmeli."""
    from multiagent.agents.build import BuildError, UnifiedDiffApplier

    deleted = tmp_path / "doomed.py"
    deleted.write_text("to be deleted\n", encoding="utf-8")

    bad_diff = (
        "--- a/doomed.py\n"
        "+++ /dev/null\n"
        "@@ -1,1 +0,0 @@\n"
        "-to be deleted\n"
        "--- a/../escape.py\n"
        "+++ b/../escape.py\n"
        "@@ -0,0 +1,1 @@\n"
        "+x = 1\n"
    )

    import pytest

    with pytest.raises(BuildError):
        UnifiedDiffApplier.apply(tmp_path, bad_diff)

    assert deleted.exists()
    assert deleted.read_text(encoding="utf-8") == "to be deleted\n"
