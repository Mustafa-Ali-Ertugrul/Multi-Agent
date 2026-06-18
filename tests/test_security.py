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


def test_security_agent_detects_xss_via_fstring_html(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    context = ContextStore(repo_path=tmp_path)
    context.files = {
        "template.py": "\n".join(
            [
                "def render(name):",
                '    return f"<div>{name}</div>"',
            ]
        )
    }
    monkeypatch.setattr(SecurityAgent, "_run_bandit", lambda self, context: None)
    monkeypatch.setattr(
        SecurityAgent, "_run_dependency_audit", lambda self, context: None
    )

    SecurityAgent().run(context)

    sources = {finding.source for finding in context.findings}
    assert "security:xss" in sources


def test_security_agent_does_not_flag_non_html_fstring(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    context = ContextStore(repo_path=tmp_path)
    context.files = {
        "logic.py": ("def cmp(a, b):\n    return f'{a} < {b} and {a} > {b}'\n"),
    }
    monkeypatch.setattr(SecurityAgent, "_run_bandit", lambda self, context: None)
    monkeypatch.setattr(
        SecurityAgent, "_run_dependency_audit", lambda self, context: None
    )

    SecurityAgent().run(context)

    xss_findings = [f for f in context.findings if f.source == "security:xss"]
    assert xss_findings == []


def test_security_agent_detects_sqli_via_assigned_fstring(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    context = ContextStore(repo_path=tmp_path)
    context.files = {
        "db.py": "\n".join(
            [
                "def handler(cursor, name):",
                '    query = f"SELECT * FROM users WHERE name = {name}"',
                "    cursor.execute(query)",
            ]
        )
    }
    monkeypatch.setattr(SecurityAgent, "_run_bandit", lambda self, context: None)
    monkeypatch.setattr(
        SecurityAgent, "_run_dependency_audit", lambda self, context: None
    )

    SecurityAgent().run(context)

    sources = {finding.source for finding in context.findings}
    assert "security:sqli" in sources


def test_security_agent_does_not_flag_safe_variable_execute(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    context = ContextStore(repo_path=tmp_path)
    context.files = {
        "db.py": "\n".join(
            [
                "def handler(cursor, user_id):",
                '    query = "SELECT * FROM users WHERE id = ?"',
                "    cursor.execute(query, (user_id,))",
            ]
        )
    }
    monkeypatch.setattr(SecurityAgent, "_run_bandit", lambda self, context: None)
    monkeypatch.setattr(
        SecurityAgent, "_run_dependency_audit", lambda self, context: None
    )

    SecurityAgent().run(context)

    sqli_findings = [f for f in context.findings if f.source == "security:sqli"]
    assert sqli_findings == []
