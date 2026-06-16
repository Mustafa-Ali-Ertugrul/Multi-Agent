import tomllib
from dataclasses import dataclass, field
from pathlib import Path


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
    exclude_dirs: list[str] = field(
        default_factory=lambda: [".git", "__pycache__", ".venv", "venv"]
    )


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
    except Exception:
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
        if "exclude_dirs" in cfg and isinstance(cfg["exclude_dirs"], list):
            c.exclude_dirs = [str(a) for a in cfg["exclude_dirs"]]

    return c
