from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from multiagent.agents.base import Agent
from multiagent.agents.build import BuildError, UnifiedDiffApplier
from multiagent.context.store import ContextStore
from multiagent.llm.gateway import LLMGateway

if TYPE_CHECKING:
    from multiagent.mcp.client import MCPClient


class GitHubPRError(RuntimeError):
    """Raised when GitHub PR operations fail."""


class GitHubPRAgent(Agent):
    def __init__(
        self,
        llm: LLMGateway,
        dry_run: bool = True,
        tools: MCPClient | None = None,
        require_mcp: bool = False,
    ) -> None:
        super().__init__(tools=tools, require_mcp=require_mcp)
        self.llm = llm
        self.dry_run = dry_run

        self.github_token = os.environ.get("GITHUB_TOKEN")
        if not self.github_token:
            raise GitHubPRError("GITHUB_TOKEN ortam degiskeni bulunamadi.")

    @property
    def name(self) -> str:
        return "github_pr"

    def run(self, context: ContextStore) -> ContextStore:
        diff_text = self._extract_diff(context)
        if not diff_text:
            context.decisions.append(
                "Uretilmis bir unified diff bulunamadi. PR acilmayacak."
            )
            return context

        title, body = self._generate_pr_content(context)
        branch_name = f"auto-fix-{int(time.time())}"

        if self.dry_run:
            context.decisions.append(
                f"[DRY RUN] PR acilmayacak.\n"
                f"Branch: {branch_name}\nTitle: {title}\nBody: {body}"
            )
            return context

        try:
            self._apply_diff_if_needed(context, diff_text)
            self._commit_and_push(context.repo_path, branch_name, title)
            pr_url = self._create_pull_request(
                context.repo_path, branch_name, title, body
            )
            context.decisions.append(f"Pull Request basariyla acildi: {pr_url}")
        except Exception as exc:
            raise GitHubPRError(f"PR olusturma sirasinda hata: {exc}") from exc

        return context

    def _extract_diff(self, context: ContextStore) -> str | None:
        prefix = "Onerilen degisiklik (unified diff):\n"
        for decision in reversed(context.decisions):
            if decision.startswith(prefix):
                return decision[len(prefix) :]
        return None

    def _generate_pr_content(self, context: ContextStore) -> tuple[str, str]:
        prompt = (
            "Asagidaki kararlara ve bulgulara dayanarak bir GitHub Pull Request icin "
            "baslik (title) ve govde (body) uret. Yaniti SADECE gecerli bir JSON "
            'formatinda ver: {"title": "...", "body": "..."}\n\n'
            "Kararlar:\n" + "\n".join(context.decisions)
        )

        response = self.llm.chat(
            messages=[
                {
                    "role": "system",
                    "content": "Sadece belirtilen JSON formatinda yanit ver.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )

        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1 and end != 0:
                data = json.loads(response[start:end])
                return (
                    str(data.get("title", "Otomatik Duzeltme")),
                    str(data.get("body", "Bu PR otomatik olarak uretilmistir.")),
                )
        except Exception:
            pass

        return "Otomatik Duzeltme", f"Bu PR otomatik olarak uretilmistir.\n\n{response}"

    def _apply_diff_if_needed(self, context: ContextStore, diff: str) -> None:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=context.repo_path,
            capture_output=True,
            text=True,
        )
        if status.stdout.strip():
            return

        try:
            UnifiedDiffApplier.apply(context.repo_path, diff)
        except BuildError:
            pass

    def _commit_and_push(self, repo_path: Path, branch_name: str, message: str) -> None:
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "add", "-A"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        if not status.stdout.strip():
            raise GitHubPRError("Commit edilecek bir degisiklik bulunamadi.")

        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "push", "-u", "origin", branch_name],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

    def _get_repo_full_name(self, repo_path: Path) -> str:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        url = result.stdout.strip()

        if "github.com" not in url:
            raise GitHubPRError(f"Gecerli bir GitHub origin URL'si bulunamadi: {url}")

        if url.startswith("https://"):
            parts = url.split("github.com/")[-1]
        elif "git@github.com:" in url:
            parts = url.split("git@github.com:")[-1]
        else:
            parts = url

        if parts.endswith(".git"):
            parts = parts[:-4]
        return parts

    def _create_pull_request(
        self, repo_path: Path, branch_name: str, title: str, body: str
    ) -> str:
        repo_name = self._get_repo_full_name(repo_path)
        base_branch = self._get_default_branch(repo_name)

        url = f"https://api.github.com/repos/{repo_name}/pulls"
        data = {
            "title": title,
            "body": body,
            "head": branch_name,
            "base": base_branch,
        }
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        with httpx.Client() as client:
            response = client.post(url, json=data, headers=headers)

        if response.status_code != 201:
            raise GitHubPRError(
                f"PR olusturulamadi. HTTP {response.status_code}: {response.text}"
            )

        resp_data = response.json()
        if not isinstance(resp_data, dict):
            raise GitHubPRError("Gecersiz PR API yaniti.")

        html_url = resp_data.get("html_url")
        if not isinstance(html_url, str):
            raise GitHubPRError("PR URL'si API yanitinda bulunamadi.")

        return html_url

    def _get_default_branch(self, repo_name: str) -> str:
        url = f"https://api.github.com/repos/{repo_name}"
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        with httpx.Client() as client:
            response = client.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict):
                branch = data.get("default_branch")
                if isinstance(branch, str):
                    return branch
        return "main"
