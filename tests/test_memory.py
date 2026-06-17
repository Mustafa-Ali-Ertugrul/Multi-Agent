from __future__ import annotations

from pathlib import Path

from multiagent.context.store import ContextStore, Finding
from multiagent.memory import SQLiteMemoryStore


def test_sqlite_memory_store_persists_and_recalls_records(tmp_path: Path) -> None:
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite")
    context = ContextStore(repo_path=tmp_path, task="authentication module")
    context.files = {"auth.py": "TOKEN = 'value'\n"}
    context.add_finding(
        Finding(
            severity="high",
            file="auth.py",
            line=1,
            message="Authentication secret leaked",
            source="security:secret",
        )
    )
    context.decisions.append("Authentication module uses JWT tokens.")
    context.add_trace("security", "run", "security enabled")

    store.save_run(context)

    memories = store.recall(
        repo_path=tmp_path,
        task="authentication follow-up",
        file_names=["auth.py"],
    )

    assert len(memories) >= 2
    assert any("Authentication secret leaked" in memory.content for memory in memories)
    assert any(memory.kind == "decision" for memory in memories)
