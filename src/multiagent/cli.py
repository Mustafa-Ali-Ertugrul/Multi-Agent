from __future__ import annotations

import argparse
from pathlib import Path
from typing import NoReturn

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from multiagent.agents.architect import ArchitectAgent
from multiagent.agents.base import Agent
from multiagent.agents.build import BuildAgent
from multiagent.agents.github_pr import GitHubPRAgent
from multiagent.agents.reviewer import ReviewerAgent
from multiagent.agents.test_runner import TestRunnerAgent
from multiagent.config import load_config
from multiagent.context.store import ContextStore, Finding
from multiagent.llm.gateway import LLMGateway
from multiagent.mcp.client import MCPClient, MCPServerConfig
from multiagent.orchestrator.core import Orchestrator

console = Console()


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "analyze":
        _analyze(args)
        return

    _fail("Bilinmeyen komut.")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="multiagent",
        description="Multi-agent kod analiz araci.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Bir repo uzerinde analiz calistirir.",
    )
    analyze_parser.add_argument("repo_path", type=Path)
    analyze_parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Ollama model adi. MULTIAGENT_MODEL ortam degiskeninden once gelir.",
    )
    analyze_parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Analiz context JSON ciktisinin yazilacagi dosya.",
    )
    analyze_parser.add_argument(
        "--agents",
        type=str,
        default=None,
        help="Calistirilacak agent adlari (virgulle ayrilmis).",
    )
    analyze_parser.add_argument(
        "--apply",
        action="store_true",
        help="BuildAgent'in diff uygulamasini acar.",
    )
    analyze_parser.add_argument(
        "--open-pr",
        action="store_true",
        help=(
            "GitHubPRAgent'i ekleyerek PR olusturma adimini calistirir "
            "(varsayilan olarak dry_run)."
        ),
    )
    analyze_parser.add_argument(
        "--execute-pr",
        action="store_true",
        help=(
            "dry_run modunu kapatarak GitHub uzerinde gercek bir PR acar "
            "(ortamda GITHUB_TOKEN gerektirir)."
        ),
    )
    analyze_parser.add_argument(
        "--require-mcp",
        action="store_true",
        help="MCP entegrasyonunu zorunlu kilar, mcp arizalanirsa sert hata firlatir.",
    )
    analyze_parser.add_argument(
        "--mcp-command",
        type=str,
        default=None,
        help="MCP stdio sunucusu icin komut.",
    )
    analyze_parser.add_argument(
        "--mcp-args",
        type=str,
        default=None,
        help="MCP stdio sunucusu icin argumanlar (boslukla ayrilmis).",
    )
    analyze_parser.add_argument(
        "--mcp-url",
        type=str,
        default=None,
        help="MCP sse sunucusu icin URL.",
    )

    return parser


def _analyze(args: argparse.Namespace) -> None:
    repo_path = args.repo_path
    if not isinstance(repo_path, Path):
        _fail("repo-path gecerli bir dosya yolu olmali.")
    if not repo_path.exists() or not repo_path.is_dir():
        _fail(f"Repo dizini bulunamadi: {repo_path}")

    config = load_config(
        repo_path / "multiagent.toml"
        if (repo_path / "multiagent.toml").exists()
        else repo_path / ".multiagent.toml"
    )

    context = ContextStore(repo_path=repo_path, exclude_dirs=set(config.exclude_dirs))
    context.load_repo(repo_path)

    model = args.model or config.model
    llm = (
        LLMGateway.from_env(model=model)
        if isinstance(model, str)
        else LLMGateway.from_env()
    )

    valid_agent_names = ["reviewer", "architect", "test-runner", "build"]
    if args.open_pr or args.execute_pr:
        valid_agent_names.append("github_pr")

    if isinstance(args.agents, str) and args.agents.strip():
        requested_names = [
            name.strip().lower() for name in args.agents.split(",") if name.strip()
        ]
        for name in requested_names:
            if name not in valid_agent_names and name != "github_pr":
                _fail(
                    f"Gecersiz agent: {name}. Gecerli agent'lar: "
                    "reviewer, architect, test-runner, build, github_pr"
                )
        if "github_pr" in requested_names and "github_pr" not in valid_agent_names:
            valid_agent_names.append("github_pr")

        active_names = [name for name in valid_agent_names if name in requested_names]
    else:
        # Check config agents
        active_names = [name for name in valid_agent_names if name in config.agents]
        if args.open_pr or args.execute_pr:
            if "github_pr" not in active_names:
                active_names.append("github_pr")

    require_mcp = bool(args.require_mcp) or config.require_mcp
    mcp_client = None

    cmd = args.mcp_command or config.mcp_command
    url = args.mcp_url or config.mcp_url

    if cmd or url:
        if args.mcp_args:
            mcp_args = args.mcp_args.split()
        elif config.mcp_args:
            mcp_args = config.mcp_args
        else:
            mcp_args = []

        server_config = MCPServerConfig(
            command=cmd,
            args=mcp_args,
            url=url,
        )
        mcp_client = MCPClient(server_config)

    agents_map: dict[str, Agent] = {
        "reviewer": ReviewerAgent(llm=llm, tools=mcp_client, require_mcp=require_mcp),
        "architect": ArchitectAgent(llm=llm, tools=mcp_client, require_mcp=require_mcp),
        "test-runner": TestRunnerAgent(
            llm=llm, tools=mcp_client, require_mcp=require_mcp
        ),
        "build": BuildAgent(
            llm=llm, apply=bool(args.apply), tools=mcp_client, require_mcp=require_mcp
        ),
    }

    if "github_pr" in active_names:
        agents_map["github_pr"] = GitHubPRAgent(
            llm=llm,
            dry_run=not bool(args.execute_pr),
            tools=mcp_client,
            require_mcp=require_mcp,
        )

    agent_results: list[tuple[str, list[Finding], list[str]]] = []

    for name in active_names:
        agent = agents_map[name]
        old_findings_len = len(context.findings)
        old_decisions_len = len(context.decisions)

        orchestrator = Orchestrator(llm=llm, agents=[agent])
        context = orchestrator.run(context)

        new_findings = context.findings[old_findings_len:]
        new_decisions = context.decisions[old_decisions_len:]
        agent_results.append((name, new_findings, new_decisions))

    json_out = args.json_out
    if isinstance(json_out, Path):
        context.save(json_out)

    _render_result(
        context,
        agent_results,
        json_out=json_out if isinstance(json_out, Path) else None,
    )


def _render_result(
    context: ContextStore,
    agent_results: list[tuple[str, list[Finding], list[str]]],
    json_out: Path | None,
) -> None:
    console.print(
        Panel.fit(
            f"[bold]Repo:[/bold] {context.repo_path}\n"
            f"[bold]Python dosyasi:[/bold] {len(context.files)}\n"
            f"[bold]Toplam Bulgu:[/bold] {len(context.findings)}",
            title="Multiagent Analiz",
            border_style="cyan",
        )
    )

    title_map = {
        "reviewer": "Reviewer Agent (Guvenlik Incelemesi)",
        "architect": "Architect Agent (Mimari Incelemesi)",
        "test-runner": "Test-Runner Agent (Test Incelemesi)",
        "build": "Build Agent (Onerilen Unified Diff)",
        "github_pr": "GitHub PR Agent",
    }

    for agent_name, findings, decisions in agent_results:
        display_title = title_map.get(agent_name, f"{agent_name.capitalize()} Agent")
        console.print()
        console.print(
            Panel(
                f"[bold magenta]{display_title}[/bold magenta]",
                border_style="magenta",
            )
        )

        if findings:
            table = Table(
                title=f"{display_title} Bulgulari",
                header_style="bold magenta",
            )
            table.add_column("Seviye", style="bold")
            table.add_column("Dosya")
            table.add_column("Satir", justify="right")
            table.add_column("Kaynak")
            table.add_column("Mesaj")

            for finding in findings:
                table.add_row(
                    _severity_label(finding.severity),
                    finding.file,
                    str(finding.line),
                    finding.source,
                    finding.message,
                )
            console.print(table)
        else:
            if agent_name in ("reviewer", "test-runner"):
                console.print("[green]Herhangi bir bulgu saptanmadi.[/green]")

        if decisions:
            for decision in decisions:
                if "unified diff" in decision.lower() or "--- a/" in decision:
                    if "unified diff" in decision:
                        desc, _, diff_content = decision.partition(":\n")
                        console.print(f"[yellow]{desc}:[/yellow]")
                        if diff_content.strip():
                            syntax = Syntax(
                                diff_content,
                                "diff",
                                theme="monokai",
                                line_numbers=True,
                            )
                            console.print(syntax)
                    else:
                        syntax = Syntax(
                            decision,
                            "diff",
                            theme="monokai",
                            line_numbers=True,
                        )
                        console.print(syntax)
                else:
                    console.print(
                        Panel(
                            decision,
                            title="Rapor / Oneriler",
                            border_style="green",
                        )
                    )

    if json_out is not None:
        console.print()
        console.print(f"[cyan]JSON cikti yazildi:[/cyan] {json_out}")


def _severity_label(severity: str) -> str:
    normalized = severity.lower()
    if normalized == "high":
        return "[red]high[/red]"
    if normalized == "medium":
        return "[yellow]medium[/yellow]"
    if normalized == "low":
        return "[green]low[/green]"
    return severity


def _fail(message: str) -> NoReturn:
    console.print(f"[red]Hata:[/red] {message}")
    raise SystemExit(1)
