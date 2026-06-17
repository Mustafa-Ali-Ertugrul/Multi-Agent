from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from multiagent.context.store import ContextStore, MemoryRecord


class SQLiteMemoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def recall(
        self,
        repo_path: Path,
        task: str,
        file_names: list[str],
        limit: int = 10,
    ) -> list[MemoryRecord]:
        terms = self._terms(task, file_names)
        rows = self._fetch_repo_memories(repo_path)
        scored: list[tuple[int, MemoryRecord]] = []
        for row in rows:
            memory = self._record_from_row(row)
            haystack = " ".join(
                [memory.task, memory.kind, memory.content, *memory.tags]
            )
            score = sum(
                1 for term in terms if term and term.lower() in haystack.lower()
            )
            if score > 0 or not terms:
                scored.append((score, memory))

        scored.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
        return [memory for _, memory in scored[:limit]]

    def save_run(self, context: ContextStore) -> None:
        now = time.time()
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO runs(run_id, repo_path, task, created_at) "
                "VALUES (?, ?, ?, ?)",
                (context.run_id, str(context.repo_path), context.task, now),
            )
            for trace in context.agent_trace:
                conn.execute(
                    "INSERT INTO run_events(run_id, agent, action, reason, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (context.run_id, trace.agent, trace.action, trace.reason, now),
                )
            for memory in self._memories_from_context(context, now):
                conn.execute(
                    "INSERT INTO memories("
                    "repo_path, task, kind, content, tags, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        memory.repo_path,
                        memory.task,
                        memory.kind,
                        memory.content,
                        json.dumps(memory.tags),
                        memory.created_at,
                    ),
                )
            for decision in context.decisions:
                if "Pull Request" in decision or "[DRY RUN] PR" in decision:
                    conn.execute(
                        "INSERT INTO prs(run_id, repo_path, summary, created_at) "
                        "VALUES (?, ?, ?, ?)",
                        (context.run_id, str(context.repo_path), decision, now),
                    )

    def list_run_events(self, run_id: str) -> list[dict[str, object]]:
        """Return all recorded events for a given run, oldest first.

        Each event is a plain dict: ``{agent, action, reason, created_at}``.
        """
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT agent, action, reason, created_at "
                "FROM run_events WHERE run_id = ? ORDER BY id ASC",
                (run_id,),
            ).fetchall()
        return [
            {
                "agent": row["agent"],
                "action": row["action"],
                "reason": row["reason"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def _init_db(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS memories("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "repo_path TEXT NOT NULL, task TEXT NOT NULL, kind TEXT NOT NULL, "
                "content TEXT NOT NULL, tags TEXT NOT NULL, created_at REAL NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS runs("
                "run_id TEXT PRIMARY KEY, repo_path TEXT NOT NULL, "
                "task TEXT NOT NULL, created_at REAL NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS run_events("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, "
                "agent TEXT NOT NULL, action TEXT NOT NULL, reason TEXT NOT NULL, "
                "created_at REAL NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS prs("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, "
                "repo_path TEXT NOT NULL, summary TEXT NOT NULL, "
                "created_at REAL NOT NULL)"
            )

    def _fetch_repo_memories(self, repo_path: Path) -> list[sqlite3.Row]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, repo_path, task, kind, content, tags, created_at "
                "FROM memories WHERE repo_path = ? ORDER BY created_at DESC LIMIT 100",
                (str(repo_path),),
            ).fetchall()
        return list(rows)

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> MemoryRecord:
        raw_tags = row["tags"]
        try:
            parsed_tags = json.loads(raw_tags)
        except json.JSONDecodeError:
            parsed_tags = []
        tags = (
            [str(item) for item in parsed_tags] if isinstance(parsed_tags, list) else []
        )
        return MemoryRecord(
            id=int(row["id"]),
            repo_path=str(row["repo_path"]),
            task=str(row["task"]),
            kind=str(row["kind"]),
            content=str(row["content"]),
            tags=tags,
            created_at=float(row["created_at"]),
        )

    @staticmethod
    def _terms(task: str, file_names: list[str]) -> list[str]:
        task_terms = [part.strip(".,:;()[]{}").lower() for part in task.split()]
        file_terms = [Path(name).stem.lower() for name in file_names]
        return [term for term in [*task_terms, *file_terms] if len(term) >= 3]

    @staticmethod
    def _memories_from_context(
        context: ContextStore, created_at: float
    ) -> list[MemoryRecord]:
        records: list[MemoryRecord] = []
        for finding in context.findings:
            records.append(
                MemoryRecord(
                    id=0,
                    repo_path=str(context.repo_path),
                    task=context.task,
                    kind="finding",
                    content=(
                        f"{finding.severity} {finding.file}:{finding.line} "
                        f"{finding.message}"
                    ),
                    tags=[finding.source, finding.file],
                    created_at=created_at,
                )
            )
        for decision in context.decisions[-10:]:
            records.append(
                MemoryRecord(
                    id=0,
                    repo_path=str(context.repo_path),
                    task=context.task,
                    kind="decision",
                    content=decision[:2000],
                    tags=["decision"],
                    created_at=created_at,
                )
            )
        return records
