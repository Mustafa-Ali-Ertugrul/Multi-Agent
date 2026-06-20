from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from multiagent.agents.base import Agent
from multiagent.agents.reviewer import ReviewerAgent
from multiagent.context.store import ContextStore, Finding

PIP_AUDIT_TIMEOUT = 60

SECRET_PATTERNS = [
    re.compile(r"ghp_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)(api[_-]?key|secret|token)\s*=\s*['\"][^'\"]{12,}['\"]"),
]


class SecurityAgent(Agent):
    @property
    def name(self) -> str:
        return "security"

    def run(self, context: ContextStore) -> ContextStore:
        initial_count = len(context.findings)
        self._run_bandit(context)
        self._scan_files(context)
        self._run_dependency_audit(context)
        added = len(context.findings) - initial_count
        context.decisions.append(f"Security ozeti: {added} bulgu uretildi.")
        return context

    def _run_bandit(self, context: ContextStore) -> None:
        python_files = [
            context.repo_path / file_path
            for file_path in context.files
            if file_path.endswith(".py")
        ]
        if not python_files:
            return

        try:
            bandit_output = ReviewerAgent._run_bandit(python_files)
            findings = ReviewerAgent._parse_bandit_findings(
                context.repo_path, bandit_output
            )
        except Exception as exc:
            context.add_finding(
                Finding(
                    severity="low",
                    file="security",
                    line=0,
                    message=f"Bandit unavailable: {exc}",
                    source="security:cve",
                )
            )
            return

        for finding in findings:
            context.add_finding(finding)

    def _scan_files(self, context: ContextStore) -> None:
        for relative_path, content in context.files.items():
            self._scan_secrets(context, relative_path, content)
            self._scan_python_ast(context, relative_path, content)

    @staticmethod
    def _scan_secrets(context: ContextStore, relative_path: str, content: str) -> None:
        for line_number, line in enumerate(content.splitlines(), start=1):
            for pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    context.add_finding(
                        Finding(
                            severity="high",
                            file=relative_path,
                            line=line_number,
                            message="Potential secret leak detected.",
                            source="security:secret",
                        )
                    )
                    break

    def _scan_python_ast(
        self, context: ContextStore, relative_path: str, content: str
    ) -> None:
        tree = context.get_ast(relative_path)
        if tree is None:
            return

        risky_names = _risky_assigned_names(tree)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                self._check_sqli(context, relative_path, node, risky_names)
                self._check_ssrf(context, relative_path, node)
                self._check_xss(context, relative_path, node)
            elif isinstance(node, ast.JoinedStr):
                self._check_xss_fstring(context, relative_path, node)

    @staticmethod
    def _check_sqli(
        context: ContextStore,
        relative_path: str,
        node: ast.Call,
        risky_names: set[str],
    ) -> None:
        call_name = _call_name(node.func)
        if not call_name.endswith(".execute") and call_name != "execute":
            return
        if not node.args:
            return
        query = node.args[0]
        if isinstance(query, (ast.JoinedStr, ast.BinOp)):
            context.add_finding(
                Finding(
                    severity="high",
                    file=relative_path,
                    line=node.lineno,
                    message="Potential SQL injection via dynamic execute() query.",
                    source="security:sqli",
                )
            )
        elif isinstance(query, ast.Call) and _call_name(query.func).endswith(".format"):
            context.add_finding(
                Finding(
                    severity="high",
                    file=relative_path,
                    line=node.lineno,
                    message="Potential SQL injection via formatted execute() query.",
                    source="security:sqli",
                )
            )
        elif isinstance(query, ast.Name) and query.id in risky_names:
            context.add_finding(
                Finding(
                    severity="high",
                    file=relative_path,
                    line=node.lineno,
                    message=(
                        "Potential SQL injection via assigned dynamic execute() query."
                    ),
                    source="security:sqli",
                )
            )

    @staticmethod
    def _check_ssrf(context: ContextStore, relative_path: str, node: ast.Call) -> None:
        call_name = _call_name(node.func)
        if call_name not in {
            "requests.get",
            "requests.post",
            "httpx.get",
            "httpx.post",
            "client.get",
            "client.post",
        }:
            return
        if node.args and not isinstance(node.args[0], ast.Constant):
            context.add_finding(
                Finding(
                    severity="medium",
                    file=relative_path,
                    line=node.lineno,
                    message="Potential SSRF via dynamic outbound URL.",
                    source="security:ssrf",
                )
            )

    @staticmethod
    def _check_xss(context: ContextStore, relative_path: str, node: ast.Call) -> None:
        call_name = _call_name(node.func)
        risky_names = {"Markup", "mark_safe", "render_template_string"}
        if call_name.split(".")[-1] in risky_names:
            context.add_finding(
                Finding(
                    severity="medium",
                    file=relative_path,
                    line=node.lineno,
                    message="Potential XSS unsafe HTML rendering path.",
                    source="security:xss",
                )
            )

    @staticmethod
    def _check_xss_fstring(
        context: ContextStore, relative_path: str, node: ast.JoinedStr
    ) -> None:
        combined = "".join(
            v.value
            for v in node.values
            if isinstance(v, ast.Constant) and isinstance(v.value, str)
        )
        if re.search(r"</?[a-zA-Z][a-zA-Z0-9]*", combined):
            context.add_finding(
                Finding(
                    severity="medium",
                    file=relative_path,
                    line=node.lineno,
                    message="Potential XSS via f-string HTML rendering.",
                    source="security:xss",
                )
            )

    def _run_dependency_audit(self, context: ContextStore) -> None:
        if not self._has_dependency_manifest(context.repo_path):
            return
        if shutil.which("pip-audit") is None:
            context.add_finding(
                Finding(
                    severity="low",
                    file="dependencies",
                    line=0,
                    message="Dependency audit unavailable: pip-audit is not installed.",
                    source="security:cve",
                )
            )
            return

        try:
            result = subprocess.run(
                ["pip-audit", "-f", "json"],
                cwd=context.repo_path,
                capture_output=True,
                check=False,
                text=True,
                timeout=PIP_AUDIT_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            context.add_finding(
                Finding(
                    severity="low",
                    file="dependencies",
                    line=0,
                    message=(f"Dependency audit timed out after {PIP_AUDIT_TIMEOUT}s."),
                    source="security:cve",
                )
            )
            return
        if result.returncode not in (0, 1):
            context.add_finding(
                Finding(
                    severity="low",
                    file="dependencies",
                    line=0,
                    message=f"Dependency audit failed: {result.stderr.strip()}",
                    source="security:cve",
                )
            )
            return
        self._parse_pip_audit(context, result.stdout)

    @staticmethod
    def _parse_pip_audit(context: ContextStore, output: str) -> None:
        try:
            data: Any = json.loads(output)
        except json.JSONDecodeError:
            return
        dependencies = data.get("dependencies", []) if isinstance(data, dict) else []
        if not isinstance(dependencies, list):
            return
        for dependency in dependencies:
            if not isinstance(dependency, dict):
                continue
            name = str(dependency.get("name", "dependency"))
            vulnerabilities = dependency.get("vulns", [])
            if not isinstance(vulnerabilities, list):
                continue
            for vulnerability in vulnerabilities:
                if isinstance(vulnerability, dict):
                    vuln_id = str(vulnerability.get("id", "unknown"))
                    context.add_finding(
                        Finding(
                            severity="high",
                            file="dependencies",
                            line=0,
                            message=f"{name} has known vulnerability {vuln_id}.",
                            source="security:cve",
                        )
                    )

    @staticmethod
    def _has_dependency_manifest(repo_path: Path) -> bool:
        if (repo_path / "pyproject.toml").exists():
            return True
        return any(repo_path.glob("requirements*.txt"))


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _risky_assigned_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        risky = isinstance(value, (ast.JoinedStr, ast.BinOp)) or (
            isinstance(value, ast.Call) and _call_name(value.func).endswith(".format")
        )
        if risky:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names
