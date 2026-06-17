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
from multiagent.agents.coordinator import CoordinatorAgent
from multiagent.agents.github_pr import GitHubPRAgent
from multiagent.agents.knowledge_graph import KnowledgeGraphAgent
from multiagent.agents.memory import MemoryAgent
from multiagent.agents.reviewer import ReviewerAgent
from multiagent.agents.security import SecurityAgent
from multiagent.agents.test_runner import TestRunnerAgent
from multiagent.benchmark import BenchmarkRunner, write_benchmark_json
from multiagent.config import BenchmarkModelConfig, load_config
from multiagent.context.store import BenchmarkResult, ContextStore, Finding
from multiagent.llm.gateway import LLMGateway
from multiagent.log import configure_logging
from multiagent.mcp.client import MCPClient, MCPServerConfig
from multiagent.orchestrator.core import Orchestrator

console = Console()


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    level = "INFO" if getattr(args, "verbose", False) else "WARNING"
    if getattr(args, "quiet", False):
        level = "ERROR"
    configure_logging(level)

    if args.command == "analyze":
        _analyze(args)
        return
    if args.command == "benchmark":
        _benchmark(args)
        return

    _fail("Bilinmeyen komut.")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="multiagent",
        description="Multi-agent kod analiz araci.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Detayli log ciktisi (DEBUG/INFO seviyesi).",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Sadece hatalari goster (ERROR seviyesi).",
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
    analyze_parser.add_argument(
        "--task",
        type=str,
        default="",
        help="Gorev niyeti; memory, coordinator ve benchmark icin kullanilir.",
    )
    analyze_parser.add_argument(
        "--coordinator",
        action="store_true",
        help="Agent secimini CoordinatorAgent ile yapar.",
    )
    analyze_parser.add_argument(
        "--memory",
        action="store_true",
        help="Kalici SQLite hafizayi acar.",
    )
    analyze_parser.add_argument(
        "--memory-path",
        type=Path,
        default=None,
        help="Memory SQLite dosya yolu.",
    )
    analyze_parser.add_argument(
        "--security",
        action="store_true",
        help="SecurityAgent taramasini calistirir.",
    )
    analyze_parser.add_argument(
        "--knowledge-graph",
        action="store_true",
        help="Repo knowledge graph uretimini acar.",
    )
    analyze_parser.add_argument(
        "--max-agent-iterations",
        type=int,
        default=None,
        help="Coordinator tekrar calistirma limiti.",
    )
    analyze_parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help=(
            "Bir agent hata verirse pipeline'i durdurmaz, hatayi trace'e "
            "kaydeder ve devam eder (fail_fast=False)."
        ),
    )
    analyze_parser.add_argument(
        "--trace",
        action="store_true",
        help="Run sonunda agent olay kronolojisini (start/success/error) gosterir.",
    )

    benchmark_parser = subparsers.add_parser(
        "benchmark",
        help="Ayni gorevi birden fazla LLM adapter'i ile skorlar.",
    )
    benchmark_parser.add_argument("repo_path", type=Path)
    benchmark_parser.add_argument("--task", type=str, required=True)
    benchmark_parser.add_argument(
        "--models",
        type=str,
        required=True,
        help="Virgulle ayrilmis model adlari.",
    )
    benchmark_parser.add_argument("--json-out", type=Path, default=None)

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

    context = ContextStore(
        repo_path=repo_path,
        task=str(args.task or ""),
        exclude_dirs=set(config.exclude_dirs),
    )
    context.load_repo(repo_path)

    model = args.model or config.model
    llm = (
        LLMGateway.from_env(model=model)
        if isinstance(model, str)
        else LLMGateway.from_env()
    )

    use_coordinator = bool(args.coordinator) or config.coordinator
    use_memory = bool(args.memory) or config.memory
    use_security = bool(args.security) or config.security or use_coordinator
    use_graph = bool(args.knowledge_graph) or config.knowledge_graph or use_coordinator
    max_iterations = args.max_agent_iterations or config.max_agent_iterations
    fail_fast = not bool(args.continue_on_error) and config.llm_failure_mode == "fatal"

    valid_agent_names = [
        "memory",
        "knowledge-graph",
        "security",
        "reviewer",
        "architect",
        "test-runner",
        "build",
    ]
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
                    "memory, knowledge-graph, security, reviewer, architect, "
                    "test-runner, build, github_pr"
                )
        if "github_pr" in requested_names and "github_pr" not in valid_agent_names:
            valid_agent_names.append("github_pr")

        active_names = [name for name in valid_agent_names if name in requested_names]
        if use_memory and "memory" not in active_names:
            active_names.insert(0, "memory")
        if use_graph and "knowledge-graph" not in active_names:
            active_names.insert(0, "knowledge-graph")
        if use_security and "security" not in active_names:
            active_names.insert(1 if use_graph else 0, "security")
    else:
        # Check config agents
        active_names = [name for name in valid_agent_names if name in config.agents]
        if use_memory and "memory" not in active_names:
            active_names.insert(0, "memory")
        if use_graph and "knowledge-graph" not in active_names:
            active_names.insert(0, "knowledge-graph")
        if use_security and "security" not in active_names:
            active_names.insert(1 if use_graph else 0, "security")
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

    memory_path = args.memory_path or Path(config.memory_config.path)
    if not memory_path.is_absolute():
        memory_path = repo_path / memory_path

    agents_map: dict[str, Agent] = {
        "knowledge-graph": KnowledgeGraphAgent(),
        "security": SecurityAgent(),
        "reviewer": ReviewerAgent(llm=llm, tools=mcp_client, require_mcp=require_mcp),
        "architect": ArchitectAgent(llm=llm, tools=mcp_client, require_mcp=require_mcp),
        "test-runner": TestRunnerAgent(
            llm=llm, tools=mcp_client, require_mcp=require_mcp
        ),
        "build": BuildAgent(
            llm=llm, apply=bool(args.apply), tools=mcp_client, require_mcp=require_mcp
        ),
    }
    memory_agent = (
        MemoryAgent(memory_path) if use_memory or "memory" in active_names else None
    )
    if memory_agent is not None:
        agents_map["memory"] = memory_agent

    if "github_pr" in active_names:
        agents_map["github_pr"] = GitHubPRAgent(
            llm=llm,
            dry_run=not bool(args.execute_pr),
            tools=mcp_client,
            require_mcp=require_mcp,
        )

    if use_coordinator:
        coordinator_agents = {
            name: agent for name, agent in agents_map.items() if name in active_names
        }
        coordinator = CoordinatorAgent(
            agents=coordinator_agents,
            knowledge_graph_enabled=use_graph,
            security_enabled=use_security,
            open_pr=bool(args.open_pr or args.execute_pr),
            apply_changes=bool(args.apply),
            rerun_tests_after_apply=max_iterations > 1,
            fail_fast=fail_fast,
        )
        old_findings_len = len(context.findings)
        old_decisions_len = len(context.decisions)
        context = coordinator.run(context)
        agent_results = [
            (
                "coordinator",
                context.findings[old_findings_len:],
                context.decisions[old_decisions_len:],
            )
        ]
    else:
        context, agent_results = _run_linear_agents(
            context, active_names, agents_map, fail_fast=fail_fast
        )

    if memory_agent is not None:
        memory_agent.persist(context)

    json_out = args.json_out
    if isinstance(json_out, Path):
        context.save(json_out)

    _render_result(
        context,
        agent_results,
        json_out=json_out if isinstance(json_out, Path) else None,
    )

    if getattr(args, "trace", False):
        _render_trace(context, llm=llm)


def _render_trace(context: ContextStore, llm: LLMGateway | None = None) -> None:
    """Print the chronological list of agent events for this run."""
    if not context.agent_trace:
        return

    table = Table(title="Agent Olay Kronolojisi", show_lines=False)
    table.add_column("Agent", style="cyan", no_wrap=True)
    table.add_column("Aksiyon", style="magenta")
    table.add_column("Detay")

    action_style = {
        "start": "dim",
        "success": "green",
        "error": "red",
        "skip": "yellow",
    }

    for trace in context.agent_trace:
        style = action_style.get(trace.action, "white")
        table.add_row(trace.agent, trace.action, trace.reason, style=style)

    console.print(table)

    if llm is not None and llm.metrics.total_calls > 0:
        m = llm.metrics
        console.print(
            Panel(
                f"[bold]LLM:[/bold] {m.total_calls} cagri, "
                f"{m.failed_calls} hatali, "
                f"{m.total_duration_seconds:.2f}s toplam sure",
                title="LLM Metrikleri",
                border_style="blue",
            )
        )


def _run_linear_agents(
    context: ContextStore,
    active_names: list[str],
    agents_map: dict[str, Agent],
    fail_fast: bool = True,
) -> tuple[ContextStore, list[tuple[str, list[Finding], list[str]]]]:
    agent_results: list[tuple[str, list[Finding], list[str]]] = []

    for name in active_names:
        agent = agents_map[name]
        old_findings_len = len(context.findings)
        old_decisions_len = len(context.decisions)

        orchestrator = Orchestrator(agents=[agent], fail_fast=fail_fast)
        context = orchestrator.run(context)
        context.add_trace(name, "run", "linear pipeline")

        new_findings = context.findings[old_findings_len:]
        new_decisions = context.decisions[old_decisions_len:]
        agent_results.append((name, new_findings, new_decisions))

    return context, agent_results


def _benchmark(args: argparse.Namespace) -> None:
    repo_path = args.repo_path
    if (
        not isinstance(repo_path, Path)
        or not repo_path.exists()
        or not repo_path.is_dir()
    ):
        _fail(f"Repo dizini bulunamadi: {repo_path}")

    config = load_config(
        repo_path / "multiagent.toml"
        if (repo_path / "multiagent.toml").exists()
        else repo_path / ".multiagent.toml"
    )
    model_names = [name.strip() for name in args.models.split(",") if name.strip()]
    configured = {model.name: model for model in config.benchmark_models}
    models = [
        configured.get(
            name,
            BenchmarkModelConfig(name=name, provider="ollama", model=name),
        )
        for name in model_names
    ]
    results = BenchmarkRunner(models).run(repo_path, str(args.task))
    if isinstance(args.json_out, Path):
        write_benchmark_json(args.json_out, results)
    _render_benchmark(results)


def _render_benchmark(results: list[BenchmarkResult]) -> None:
    table = Table(title="Benchmark Results", header_style="bold cyan")
    table.add_column("Name")
    table.add_column("Provider")
    table.add_column("Model")
    table.add_column("Score", justify="right")
    table.add_column("Tests")
    table.add_column("Diff")
    table.add_column("High Sec", justify="right")
    table.add_column("Seconds", justify="right")
    table.add_column("Error")
    for result in results:
        table.add_row(
            result.name,
            result.provider,
            result.model,
            f"{result.score:.2f}",
            "yes" if result.tests_passed else "no",
            "yes" if result.diff_generated else "no",
            str(result.high_security_findings),
            f"{result.duration_seconds:.2f}",
            result.error or "",
        )
    console.print(table)


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
        "memory": "Memory Agent",
        "knowledge-graph": "Knowledge Graph Agent",
        "security": "Security Agent",
        "coordinator": "Coordinator Agent",
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

    if context.agent_trace:
        trace_table = Table(title="Agent Trace", header_style="bold cyan")
        trace_table.add_column("Agent")
        trace_table.add_column("Action")
        trace_table.add_column("Reason")
        for trace in context.agent_trace:
            trace_table.add_row(trace.agent, trace.action, trace.reason)
        console.print()
        console.print(trace_table)


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


if __name__ == "__main__":
    main()
