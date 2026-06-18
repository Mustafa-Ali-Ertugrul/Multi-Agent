from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import httpx

from multiagent.agents.base import Agent
from multiagent.agents.build import BuildError, UnifiedDiffApplier
from multiagent.context.store import ContextStore
from multiagent.llm.gateway import LLMGateway
from multiagent.log import get_logger

log = get_logger("github_pr")

if TYPE_CHECKING:
    from multiagent.mcp.client import MCPClient

GIT_TIMEOUT = 60
HTTPX_TIMEOUT = 60.0


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
        self.github_token: str | None = os.environ.get("GITHUB_TOKEN")

    @property
    def name(self) -> str:
        return "github_pr"

    def run(self, context: ContextStore) -> ContextStore:
        if not self.dry_run and not self.github_token:
            raise GitHubPRError(
                "GITHUB_TOKEN ortam degiskeni bulunamadi; dry_run=False icin zorunlu."
            )

        diff_text = self._extract_diff(context)
        if not diff_text:
            context.decisions.append(
                "Uretilmis bir unified diff bulunamadi. PR acilmayacak."
            )
            return context

        title, body = self._generate_pr_content(context)
        branch_name = f"auto-fix-{int(time.time())}-{uuid4().hex[:8]}"

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
        build_proposals = [
            proposal for proposal in context.proposed_diffs if proposal.agent == "build"
        ]
        if build_proposals:
            return build_proposals[-1].diff

        prefix = "Onerilen degisiklik (unified diff):\n"
        for decision in reversed(context.decisions):
            if decision.startswith(prefix):
                log.warning(
                    "build proposed_diffs bulunamadi; decisions geriye donuk "
                    "taramasina dusuldu. Yeni BuildAgent ciktisi bekleniyor."
                )
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
        except Exception as exc:
            log.warning(
                "JSON parse hatasi, varsayilan PR icerigi kullaniliyor: %s", exc
            )
            context.decisions.append(
                f"PR basligi/govdesi icin LLM JSON ayristirilamadi; "
                f"varsayilan icerik kullanildi ({exc.__class__.__name__})."
            )

        return "Otomatik Duzeltme", f"Bu PR otomatik olarak uretilmistir.\n\n{response}"

    def _apply_diff_if_needed(self, context: ContextStore, diff: str) -> None:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=context.repo_path,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
        )
        if status.stdout.strip():
            return

        try:
            UnifiedDiffApplier.apply(context.repo_path, diff)
        except BuildError as exc:
            raise GitHubPRError(f"Diff uygulanamadi, PR iptal edildi: {exc}") from exc

    def _commit_and_push(self, repo_path: Path, branch_name: str, message: str) -> None:
        try:
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=repo_path,
                check=True,
                capture_output=True,
                timeout=GIT_TIMEOUT,
            )
            subprocess.run(
                ["git", "add", "-A"],
                cwd=repo_path,
                check=True,
                capture_output=True,
                timeout=GIT_TIMEOUT,
            )

            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=GIT_TIMEOUT,
            )
            if not status.stdout.strip():
                raise GitHubPRError("Commit edilecek bir degisiklik bulunamadi.")

            subprocess.run(
                ["git", "commit", "-m", message],
                cwd=repo_path,
                check=True,
                capture_output=True,
                timeout=GIT_TIMEOUT,
            )
            subprocess.run(
                ["git", "push", "-u", "origin", branch_name],
                cwd=repo_path,
                check=True,
                capture_output=True,
                timeout=GIT_TIMEOUT,
            )
        except subprocess.TimeoutExpired as exc:
            raise GitHubPRError(
                f"Git islemi {GIT_TIMEOUT} saniye sure sinirini asti: {exc}"
            ) from exc

    def _get_repo_full_name(self, repo_path: Path) -> str:
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
                timeout=GIT_TIMEOUT,
            )
        except subprocess.TimeoutExpired as exc:
            raise GitHubPRError(
                f"git remote sorgusu {GIT_TIMEOUT} saniye sure sinirini asti."
            ) from exc
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

        with httpx.Client(timeout=HTTPX_TIMEOUT) as client:
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

        with httpx.Client(timeout=HTTPX_TIMEOUT) as client:
            response = client.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict):
                branch = data.get("default_branch")
                if isinstance(branch, str):
                    return branch
        return "main"
