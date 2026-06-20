from __future__ import annotations

import ast
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Self
from uuid import uuid4


@dataclass(frozen=True)
class Finding:
    severity: str
    file: str
    line: int
    message: str
    source: str


@dataclass(frozen=True)
class MemoryRecord:
    id: int
    repo_path: str
    task: str
    kind: str
    content: str
    tags: list[str]
    created_at: float


@dataclass(frozen=True)
class AgentTrace:
    agent: str
    action: str
    reason: str


@dataclass(frozen=True)
class KnowledgeNode:
    id: str
    kind: str
    name: str
    file: str
    line: int


@dataclass(frozen=True)
class KnowledgeEdge:
    source: str
    target: str
    kind: str


@dataclass(frozen=True)
class RepoGraph:
    nodes: list[KnowledgeNode]
    edges: list[KnowledgeEdge]

    def summary(self, limit: int = 20) -> str:
        nodes = self.nodes[:limit]
        lines = [f"{node.kind}:{node.name} ({node.file}:{node.line})" for node in nodes]
        remaining = len(self.nodes) - len(nodes)
        if remaining > 0:
            lines.append(f"... {remaining} more nodes")
        return "\n".join(lines)


@dataclass(frozen=True)
class BenchmarkResult:
    name: str
    provider: str
    model: str
    score: float
    duration_seconds: float
    tests_passed: bool
    diff_generated: bool
    high_security_findings: int
    error: str | None = None


@dataclass(frozen=True)
class DiffProposal:
    agent: str
    path: str | None
    diff: str
    created_at: float


@dataclass
class ContextStore:
    repo_path: Path
    task: str = ""
    run_id: str = field(
        default_factory=lambda: f"{int(time.time() * 1000)}-{uuid4().hex[:8]}"
    )
    files: dict[str, str] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    memories: list[MemoryRecord] = field(default_factory=list)
    agent_trace: list[AgentTrace] = field(default_factory=list)
    knowledge_graph: RepoGraph | None = None
    benchmark_results: list[BenchmarkResult] = field(default_factory=list)
    proposed_diffs: list[DiffProposal] = field(default_factory=list)
    exclude_dirs: set[str] = field(
        default_factory=lambda: {".venv", "node_modules", ".git"}
    )
    ast_trees: dict[str, ast.Module | None] = field(
        default_factory=dict,
        compare=False,
        repr=False,
    )

    def load_repo(self, path: Path | str) -> None:
        repo_path = Path(path)
        self.repo_path = repo_path
        self.files.clear()

        for file_path in self._iter_python_files(repo_path):
            relative_path = file_path.relative_to(repo_path).as_posix()
            self.files[relative_path] = file_path.read_text(
                encoding="utf-8",
                errors="replace",
            )

    def add_finding(self, finding: Finding) -> None:
        self.findings.append(finding)

    def add_diff_proposal(self, proposal: DiffProposal) -> None:
        self.proposed_diffs.append(proposal)

    def add_trace(self, agent: str, action: str, reason: str) -> None:
        self.agent_trace.append(AgentTrace(agent=agent, action=action, reason=reason))

    def to_json(self) -> str:
        data = {
            "repo_path": str(self.repo_path),
            "task": self.task,
            "run_id": self.run_id,
            "files": self.files,
            "findings": [asdict(finding) for finding in self.findings],
            "decisions": self.decisions,
            "memories": [asdict(memory) for memory in self.memories],
            "agent_trace": [asdict(trace) for trace in self.agent_trace],
            "knowledge_graph": (
                asdict(self.knowledge_graph) if self.knowledge_graph else None
            ),
            "benchmark_results": [asdict(result) for result in self.benchmark_results],
            "proposed_diffs": [asdict(proposal) for proposal in self.proposed_diffs],
        }
        return json.dumps(data, indent=2, sort_keys=True)

    def save(self, path: Path | str) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path | str) -> Self:
        raw_data: Any = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw_data, dict):
            raise ValueError("Context store JSON must contain an object.")

        repo_path = Path(cls._read_str(raw_data, "repo_path"))
        task = cls._read_optional_str(raw_data, "task")
        run_id = cls._read_optional_str(raw_data, "run_id")
        files = cls._read_str_dict(raw_data, "files")
        decisions = cls._read_str_list(raw_data, "decisions")
        findings = [
            Finding(
                severity=cls._read_str(item, "severity"),
                file=cls._read_str(item, "file"),
                line=cls._read_int(item, "line"),
                message=cls._read_str(item, "message"),
                source=cls._read_str(item, "source"),
            )
            for item in cls._read_dict_list(raw_data, "findings")
        ]
        memories = [
            MemoryRecord(
                id=cls._read_int(item, "id"),
                repo_path=cls._read_str(item, "repo_path"),
                task=cls._read_str(item, "task"),
                kind=cls._read_str(item, "kind"),
                content=cls._read_str(item, "content"),
                tags=cls._read_string_list_from_dict(item, "tags"),
                created_at=cls._read_float(item, "created_at"),
            )
            for item in cls._read_dict_list_optional(raw_data, "memories")
        ]
        agent_trace = [
            AgentTrace(
                agent=cls._read_str(item, "agent"),
                action=cls._read_str(item, "action"),
                reason=cls._read_str(item, "reason"),
            )
            for item in cls._read_dict_list_optional(raw_data, "agent_trace")
        ]
        proposed_diffs = [
            DiffProposal(
                agent=cls._read_str(item, "agent"),
                path=cls._read_optional_str(item, "path") or None,
                diff=cls._read_str(item, "diff"),
                created_at=cls._read_float(item, "created_at"),
            )
            for item in cls._read_dict_list_optional(raw_data, "proposed_diffs")
        ]

        return cls(
            repo_path=repo_path,
            task=task,
            run_id=run_id,
            files=files,
            findings=findings,
            decisions=decisions,
            memories=memories,
            agent_trace=agent_trace,
            knowledge_graph=cls._read_graph(raw_data.get("knowledge_graph")),
            benchmark_results=cls._read_benchmark_results(raw_data),
            proposed_diffs=proposed_diffs,
        )

    def _iter_python_files(self, repo_path: Path) -> list[Path]:
        return [
            path
            for path in repo_path.rglob("*.py")
            if not self.exclude_dirs.intersection(path.relative_to(repo_path).parts)
        ]

    def get_ast(self, relative_path: str) -> ast.Module | None:
        if relative_path in self.ast_trees:
            return self.ast_trees[relative_path]
        content = self.files.get(relative_path, "")
        try:
            tree = ast.parse(content)
        except SyntaxError:
            tree = None
        self.ast_trees[relative_path] = tree
        return tree

    @staticmethod
    def _read_str(data: dict[str, Any], key: str) -> str:
        value = data.get(key)
        if not isinstance(value, str):
            raise ValueError(f"Expected '{key}' to be a string.")
        return value

    @staticmethod
    def _read_optional_str(data: dict[str, Any], key: str) -> str:
        value = data.get(key, "")
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError(f"Expected '{key}' to be a string.")
        return value

    @staticmethod
    def _read_int(data: dict[str, Any], key: str) -> int:
        value = data.get(key)
        if not isinstance(value, int):
            raise ValueError(f"Expected '{key}' to be an integer.")
        return value

    @staticmethod
    def _read_float(data: dict[str, Any], key: str) -> float:
        value = data.get(key)
        if not isinstance(value, (int, float)):
            raise ValueError(f"Expected '{key}' to be a number.")
        return float(value)

    @staticmethod
    def _read_str_dict(data: dict[str, Any], key: str) -> dict[str, str]:
        value = data.get(key)
        if not isinstance(value, dict):
            raise ValueError(f"Expected '{key}' to be an object.")
        if not all(isinstance(item_key, str) for item_key in value):
            raise ValueError(f"Expected all '{key}' keys to be strings.")
        if not all(isinstance(item_value, str) for item_value in value.values()):
            raise ValueError(f"Expected all '{key}' values to be strings.")
        return dict(value)

    @staticmethod
    def _read_str_list(data: dict[str, Any], key: str) -> list[str]:
        value = data.get(key)
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise ValueError(f"Expected '{key}' to be a list of strings.")
        return list(value)

    @staticmethod
    def _read_string_list_from_dict(data: dict[str, Any], key: str) -> list[str]:
        value = data.get(key, [])
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise ValueError(f"Expected '{key}' to be a list of strings.")
        return list(value)

    @staticmethod
    def _read_dict_list(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
        value = data.get(key)
        if not isinstance(value, list) or not all(
            isinstance(item, dict) for item in value
        ):
            raise ValueError(f"Expected '{key}' to be a list of objects.")
        return list(value)

    @staticmethod
    def _read_dict_list_optional(
        data: dict[str, Any], key: str
    ) -> list[dict[str, Any]]:
        value = data.get(key, [])
        if not isinstance(value, list) or not all(
            isinstance(item, dict) for item in value
        ):
            raise ValueError(f"Expected '{key}' to be a list of objects.")
        return list(value)

    @classmethod
    def _read_graph(cls, value: object) -> RepoGraph | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("Expected 'knowledge_graph' to be an object.")
        nodes = [
            KnowledgeNode(
                id=cls._read_str(item, "id"),
                kind=cls._read_str(item, "kind"),
                name=cls._read_str(item, "name"),
                file=cls._read_str(item, "file"),
                line=cls._read_int(item, "line"),
            )
            for item in cls._read_dict_list(value, "nodes")
        ]
        edges = [
            KnowledgeEdge(
                source=cls._read_str(item, "source"),
                target=cls._read_str(item, "target"),
                kind=cls._read_str(item, "kind"),
            )
            for item in cls._read_dict_list(value, "edges")
        ]
        return RepoGraph(nodes=nodes, edges=edges)

    @classmethod
    def _read_benchmark_results(cls, data: dict[str, Any]) -> list[BenchmarkResult]:
        return [
            BenchmarkResult(
                name=cls._read_str(item, "name"),
                provider=cls._read_str(item, "provider"),
                model=cls._read_str(item, "model"),
                score=cls._read_float(item, "score"),
                duration_seconds=cls._read_float(item, "duration_seconds"),
                tests_passed=cls._read_bool(item, "tests_passed"),
                diff_generated=cls._read_bool(item, "diff_generated"),
                high_security_findings=cls._read_int(item, "high_security_findings"),
                error=(
                    cls._read_str(item, "error")
                    if isinstance(item.get("error"), str)
                    else None
                ),
            )
            for item in cls._read_dict_list_optional(data, "benchmark_results")
        ]

    @staticmethod
    def _read_bool(data: dict[str, Any], key: str) -> bool:
        value = data.get(key)
        if not isinstance(value, bool):
            raise ValueError(f"Expected '{key}' to be a boolean.")
        return value
