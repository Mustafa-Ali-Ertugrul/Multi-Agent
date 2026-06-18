from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pytest import MonkeyPatch

from multiagent.agents.github_pr import GitHubPRAgent, GitHubPRError
from multiagent.context.store import ContextStore
from multiagent.llm.gateway import LLMGateway


class FakeLLM(LLMGateway):
    def __init__(self) -> None:
        pass

    def chat(
        self,
        messages: list[dict[str, object]],
        temperature: float = 0.2,
        max_retries: int = 3,
    ) -> str:
        return '{"title": "Test PR", "body": "Test Body"}'


def test_github_pr_constructor_allows_missing_token(monkeypatch: MonkeyPatch) -> None:
    """Constructor artik token yokliginde hata firlatmaz; kontrol run()'a tasindi."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    agent = GitHubPRAgent(llm=FakeLLM())
    assert agent.github_token is None


def test_github_pr_run_without_token_in_dry_run_works(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """dry_run=True modunda token olmadan hata firlatilmamali."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    agent = GitHubPRAgent(llm=FakeLLM(), dry_run=True)
    context = ContextStore(repo_path=tmp_path)
    context.decisions.append("Onerilen degisiklik (unified diff):\n--- a\n+++ b\n")

    result = agent.run(context)

    assert "[DRY RUN] PR acilmayacak." in result.decisions[-1]


def test_github_pr_run_without_token_in_real_mode_raises(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """dry_run=False modunda token yoksa run() GitHubPRError firlatir."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    agent = GitHubPRAgent(llm=FakeLLM(), dry_run=False)
    context = ContextStore(repo_path=tmp_path)
    context.decisions.append("Onerilen degisiklik (unified diff):\n--- a\n+++ b\n")

    with pytest.raises(GitHubPRError, match="GITHUB_TOKEN"):
        agent.run(context)


def test_github_pr_no_diff(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "fake_token")
    agent = GitHubPRAgent(llm=FakeLLM())
    context = ContextStore(repo_path=tmp_path)
    result = agent.run(context)
    assert "Uretilmis bir unified diff bulunamadi." in result.decisions[0]


def test_github_pr_dry_run(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "fake_token")
    agent = GitHubPRAgent(llm=FakeLLM(), dry_run=True)
    context = ContextStore(repo_path=tmp_path)
    context.decisions.append("Onerilen degisiklik (unified diff):\n--- a\n+++ b\n")

    result = agent.run(context)

    assert "[DRY RUN] PR acilmayacak." in result.decisions[-1]
    assert "Title: Test PR" in result.decisions[-1]


@patch("subprocess.run")
@patch("multiagent.agents.github_pr.httpx.Client")
def test_github_pr_success(
    mock_httpx_client_class: MagicMock,
    mock_run: MagicMock,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "fake_token")
    agent = GitHubPRAgent(llm=FakeLLM(), dry_run=False)
    context = ContextStore(repo_path=tmp_path)
    context.decisions.append("Onerilen degisiklik (unified diff):\n--- a\n+++ b\n")

    def fake_subprocess_run(args: list[str], **kwargs: object) -> MagicMock:
        mock_result = MagicMock()
        mock_result.stdout = ""
        if "remote" in args:
            mock_result.stdout = "https://github.com/owner/repo.git\n"
        elif "status" in args:
            mock_result.stdout = " M file.py\n"
        return mock_result

    mock_run.side_effect = fake_subprocess_run

    # Setup mock httpx client
    mock_client_instance = MagicMock()
    mock_httpx_client_class.return_value.__enter__.return_value = mock_client_instance

    mock_get_response = MagicMock()
    mock_get_response.status_code = 200
    mock_get_response.json.return_value = {"default_branch": "main"}
    mock_client_instance.get.return_value = mock_get_response

    mock_post_response = MagicMock()
    mock_post_response.status_code = 201
    mock_post_response.json.return_value = {
        "html_url": "https://github.com/owner/repo/pull/1"
    }
    mock_client_instance.post.return_value = mock_post_response

    result = agent.run(context)

    assert (
        "Pull Request basariyla acildi: https://github.com/owner/repo/pull/1"
        in result.decisions[-1]
    )

    # Assert subprocess calls
    assert any("remote" in call[0][0] for call in mock_run.call_args_list)
    assert any("commit" in call[0][0] for call in mock_run.call_args_list)
    assert any("push" in call[0][0] for call in mock_run.call_args_list)

    # Assert POST PR payload
    post_kwargs = mock_client_instance.post.call_args[1]
    assert post_kwargs["json"]["title"] == "Test PR"
    assert post_kwargs["json"]["head"].startswith("auto-fix-")
    assert post_kwargs["json"]["base"] == "main"
