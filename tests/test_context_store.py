from pathlib import Path

from multiagent.context.store import (
    BenchmarkResult,
    ContextStore,
    Finding,
    KnowledgeEdge,
    KnowledgeNode,
    MemoryRecord,
    RepoGraph,
)


def test_load_repo_reads_python_files_and_skips_excluded_dirs(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# ignored\n", encoding="utf-8")

    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "ignored.py").write_text("ignored\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ignored.py").write_text(
        "ignored\n",
        encoding="utf-8",
    )
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "ignored.py").write_text("ignored\n", encoding="utf-8")

    store = ContextStore(repo_path=tmp_path)
    store.load_repo(tmp_path)

    assert store.files == {"src/app.py": "print('hello')\n"}


def test_load_repo_skips_excluded_dirs_at_any_depth(tmp_path: Path) -> None:
    package_path = tmp_path / "package"
    package_path.mkdir()
    (package_path / "visible.py").write_text("visible = True\n", encoding="utf-8")

    nested_venv = package_path / ".venv"
    nested_venv.mkdir()
    (nested_venv / "hidden.py").write_text("hidden = True\n", encoding="utf-8")

    nested_node_modules = package_path / "node_modules"
    nested_node_modules.mkdir()
    (nested_node_modules / "hidden.py").write_text("hidden = True\n", encoding="utf-8")

    store = ContextStore(repo_path=tmp_path)
    store.load_repo(tmp_path)

    assert store.files == {"package/visible.py": "visible = True\n"}


def test_json_round_trip(tmp_path: Path) -> None:
    store = ContextStore(repo_path=tmp_path, task="auth task", run_id="run-1")
    store.files["src/app.py"] = "print('hello')\n"
    store.add_finding(
        Finding(
            severity="high",
            file="src/app.py",
            line=1,
            message="Example finding",
            source="test",
        )
    )
    store.decisions.append("Keep the first implementation small.")
    store.memories.append(
        MemoryRecord(
            id=1,
            repo_path=str(tmp_path),
            task="auth task",
            kind="decision",
            content="Use JWT.",
            tags=["auth"],
            created_at=1.0,
        )
    )
    store.add_trace("security", "run", "enabled")
    store.knowledge_graph = RepoGraph(
        nodes=[
            KnowledgeNode(
                id="file:src/app.py",
                kind="file",
                name="src/app.py",
                file="src/app.py",
                line=1,
            )
        ],
        edges=[
            KnowledgeEdge(
                source="file:src/app.py",
                target="call:print",
                kind="calls",
            )
        ],
    )
    store.benchmark_results.append(
        BenchmarkResult(
            name="qwen",
            provider="ollama",
            model="qwen",
            score=80.0,
            duration_seconds=1.0,
            tests_passed=True,
            diff_generated=True,
            high_security_findings=0,
        )
    )

    output_path = tmp_path / "context.json"
    store.save(output_path)

    loaded = ContextStore.load(output_path)

    assert loaded.repo_path == tmp_path
    assert loaded.files == store.files
    assert loaded.findings == store.findings
    assert loaded.decisions == store.decisions
    assert loaded.memories == store.memories
    assert loaded.agent_trace == store.agent_trace
    assert loaded.knowledge_graph == store.knowledge_graph
    assert loaded.benchmark_results == store.benchmark_results
