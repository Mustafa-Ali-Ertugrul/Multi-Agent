from __future__ import annotations

import argparse
from pathlib import Path
from typing import NoReturn

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from multiagent.agents.reviewer import ReviewerAgent
from multiagent.context.store import ContextStore
from multiagent.llm.gateway import LLMGateway
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

    return parser


def _analyze(args: argparse.Namespace) -> None:
    repo_path = args.repo_path
    if not isinstance(repo_path, Path):
        _fail("repo-path gecerli bir dosya yolu olmali.")
    if not repo_path.exists() or not repo_path.is_dir():
        _fail(f"Repo dizini bulunamadi: {repo_path}")

    context = ContextStore(repo_path=repo_path)
    context.load_repo(repo_path)

    model = args.model
    llm = (
        LLMGateway.from_env(model=model)
        if isinstance(model, str)
        else LLMGateway.from_env()
    )
    reviewer = ReviewerAgent(llm=llm)
    orchestrator = Orchestrator(llm=llm, agents=[reviewer])

    result = orchestrator.run(context)

    json_out = args.json_out
    if isinstance(json_out, Path):
        result.save(json_out)

    _render_result(result, json_out=json_out if isinstance(json_out, Path) else None)


def _render_result(context: ContextStore, json_out: Path | None) -> None:
    console.print(
        Panel.fit(
            f"[bold]Repo:[/bold] {context.repo_path}\n"
            f"[bold]Python dosyasi:[/bold] {len(context.files)}\n"
            f"[bold]Bulgu:[/bold] {len(context.findings)}",
            title="Multiagent Analiz",
            border_style="cyan",
        )
    )

    if context.findings:
        table = Table(title="Bandit Bulgulari", header_style="bold magenta")
        table.add_column("Seviye", style="bold")
        table.add_column("Dosya")
        table.add_column("Satir", justify="right")
        table.add_column("Kaynak")
        table.add_column("Mesaj")

        for finding in context.findings:
            table.add_row(
                _severity_label(finding.severity),
                finding.file,
                str(finding.line),
                finding.source,
                finding.message,
            )
        console.print(table)
    else:
        console.print("[green]Bandit bulgusu yok.[/green]")

    if context.decisions:
        console.print(
            Panel(
                "\n\n".join(context.decisions),
                title="Ozet Rapor",
                border_style="green",
            )
        )

    if json_out is not None:
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
