import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from multiagent.log import get_logger

log = get_logger("config")


@dataclass
class MemoryConfig:
    path: str = ".multiagent/memory.sqlite"


@dataclass
class BenchmarkModelConfig:
    name: str
    provider: str
    model: str
    base_url: str | None = None
    api_key_env: str | None = None
    cost_per_1k_tokens: float | None = None


@dataclass
class Config:
    model: str | None = None
    base_url: str | None = None
    agents: list[str] = field(
        default_factory=lambda: ["reviewer", "architect", "test-runner", "build"]
    )
    mcp_command: str | None = None
    mcp_args: list[str] = field(default_factory=list)
    mcp_url: str | None = None
    require_mcp: bool = False
    coordinator: bool = False
    memory: bool = False
    security: bool = False
    knowledge_graph: bool = False
    max_agent_iterations: int = 2
    memory_config: MemoryConfig = field(default_factory=MemoryConfig)
    benchmark_models: list[BenchmarkModelConfig] = field(default_factory=list)
    exclude_dirs: list[str] = field(
        default_factory=lambda: [".venv", "node_modules", ".git"]
    )
    # "fatal" (default) raises on LLM/MCP errors; "fallback" logs and continues.
    llm_failure_mode: str = "fatal"


def load_config(path: Path | None = None) -> Config:
    default_names = ["multiagent.toml", ".multiagent.toml"]
    target_path = None

    if path and path.exists():
        target_path = path
    elif not path:
        for name in default_names:
            p = Path(name)
            if p.exists():
                target_path = p
                break

    if not target_path:
        return Config()

    try:
        with open(target_path, "rb") as f:
            data = tomllib.load(f)
    except Exception as exc:
        log.warning(
            "Uyari: %s okunamadi, varsayilan Config kullaniliyor: %s",
            target_path,
            exc,
        )
        return Config()

    c = Config()
    if "multiagent" in data:
        cfg = data["multiagent"]
        if "model" in cfg:
            c.model = str(cfg["model"])
        if "base_url" in cfg:
            c.base_url = str(cfg["base_url"])
        if "agents" in cfg and isinstance(cfg["agents"], list):
            c.agents = [str(a) for a in cfg["agents"]]
        if "mcp_command" in cfg:
            c.mcp_command = str(cfg["mcp_command"])
        if "mcp_args" in cfg and isinstance(cfg["mcp_args"], list):
            c.mcp_args = [str(a) for a in cfg["mcp_args"]]
        if "mcp_url" in cfg:
            c.mcp_url = str(cfg["mcp_url"])
        if "require_mcp" in cfg:
            c.require_mcp = bool(cfg["require_mcp"])
        if "coordinator" in cfg:
            c.coordinator = bool(cfg["coordinator"])
        if "memory" in cfg:
            if isinstance(cfg["memory"], bool):
                c.memory = cfg["memory"]
            elif isinstance(cfg["memory"], dict):
                c.memory = True
                if "path" in cfg["memory"]:
                    c.memory_config.path = str(cfg["memory"]["path"])
        if "security" in cfg:
            c.security = bool(cfg["security"])
        if "knowledge_graph" in cfg:
            c.knowledge_graph = bool(cfg["knowledge_graph"])
        if "max_agent_iterations" in cfg:
            try:
                c.max_agent_iterations = max(1, int(cfg["max_agent_iterations"]))
            except (TypeError, ValueError):
                c.max_agent_iterations = 2
        if "exclude_dirs" in cfg and isinstance(cfg["exclude_dirs"], list):
            c.exclude_dirs = [str(a) for a in cfg["exclude_dirs"]]
        if "llm_failure_mode" in cfg:
            mode = str(cfg["llm_failure_mode"]).lower()
            if mode in {"fatal", "fallback"}:
                c.llm_failure_mode = mode
        if "memory_path" in cfg:
            c.memory_config.path = str(cfg["memory_path"])
        if "benchmark" in data["multiagent"] and isinstance(
            data["multiagent"]["benchmark"], dict
        ):
            benchmark_cfg = data["multiagent"]["benchmark"]
            raw_models = benchmark_cfg.get("models", [])
            if isinstance(raw_models, list):
                c.benchmark_models = [
                    _read_benchmark_model(item)
                    for item in raw_models
                    if isinstance(item, dict)
                ]

    return c


def _read_benchmark_model(data: dict[object, object]) -> BenchmarkModelConfig:
    cost = data.get("cost_per_1k_tokens")
    parsed_cost = float(cost) if isinstance(cost, (int, float)) else None
    return BenchmarkModelConfig(
        name=str(data.get("name", data.get("model", "model"))),
        provider=str(data.get("provider", "ollama")),
        model=str(data.get("model", data.get("name", "model"))),
        base_url=str(data["base_url"]) if "base_url" in data else None,
        api_key_env=str(data["api_key_env"]) if "api_key_env" in data else None,
        cost_per_1k_tokens=parsed_cost,
    )
