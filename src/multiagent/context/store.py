from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Self


@dataclass(frozen=True)
class Finding:
    severity: str
    file: str
    line: int
    message: str
    source: str


@dataclass
class ContextStore:
    repo_path: Path
    files: dict[str, str] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    exclude_dirs: set[str] = field(
        default_factory=lambda: {".venv", "node_modules", ".git"}
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

    def to_json(self) -> str:
        data = {
            "repo_path": str(self.repo_path),
            "files": self.files,
            "findings": [asdict(finding) for finding in self.findings],
            "decisions": self.decisions,
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

        return cls(
            repo_path=repo_path,
            files=files,
            findings=findings,
            decisions=decisions,
        )

    def _iter_python_files(self, repo_path: Path) -> list[Path]:
        return [
            path
            for path in repo_path.rglob("*.py")
            if not self.exclude_dirs.intersection(path.relative_to(repo_path).parts)
        ]

    @staticmethod
    def _read_str(data: dict[str, Any], key: str) -> str:
        value = data.get(key)
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
    def _read_dict_list(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
        value = data.get(key)
        if not isinstance(value, list) or not all(
            isinstance(item, dict) for item in value
        ):
            raise ValueError(f"Expected '{key}' to be a list of objects.")
        return list(value)
