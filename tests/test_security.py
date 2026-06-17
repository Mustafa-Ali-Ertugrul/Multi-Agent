from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from pytest import MonkeyPatch

from multiagent.agents.security import SecurityAgent
from multiagent.context.store import ContextStore


def test_security_agent_detects_secret_sqli_ssrf_and_xss(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    context = ContextStore(repo_path=tmp_path)
    context.files = {
        "app.py": "\n".join(
            [
                "import requests",
                "from markupsafe import Markup",
                "API_KEY = 'sk-abcdefghijklmnopqrstuvwxyz'",
                "def handler(user_url, name, cursor):",
                '    cursor.execute(f"SELECT * FROM users WHERE name = {name}")',
                "    requests.get(user_url)",
                "    return Markup(name)",
            ]
        )
    }
    monkeypatch.setattr(SecurityAgent, "_run_bandit", lambda self, context: None)
    monkeypatch.setattr(
        SecurityAgent, "_run_dependency_audit", lambda self, context: None
    )

    SecurityAgent().run(context)

    sources = {finding.source for finding in context.findings}
    assert "security:secret" in sources
    assert "security:sqli" in sources
    assert "security:ssrf" in sources
    assert "security:xss" in sources


def test_security_agent_reports_missing_dependency_audit(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    context = ContextStore(repo_path=tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n")
    monkeypatch.setattr(shutil, "which", lambda name: None)

    SecurityAgent()._run_dependency_audit(context)

    assert context.findings[0].source == "security:cve"
    assert "pip-audit is not installed" in context.findings[0].message


def test_security_agent_skips_dependency_audit_without_manifest(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    context = ContextStore(repo_path=tmp_path)
    monkeypatch.setattr(shutil, "which", lambda name: "pip-audit")

    SecurityAgent()._run_dependency_audit(context)

    assert context.findings == []


def test_security_agent_parses_pip_audit_vulnerabilities(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    context = ContextStore(repo_path=tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n")
    monkeypatch.setattr(shutil, "which", lambda name: "pip-audit")

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["pip-audit"],
            returncode=1,
            stdout='{"dependencies":[{"name":"pkg","vulns":[{"id":"CVE-1"}]}]}',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    SecurityAgent()._run_dependency_audit(context)

    assert context.findings[0].source == "security:cve"
    assert "CVE-1" in context.findings[0].message
