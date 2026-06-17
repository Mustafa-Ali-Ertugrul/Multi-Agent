from pathlib import Path

from multiagent.config import load_config


def test_load_config_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path / "non_existent.toml")
    assert config.model is None
    assert config.agents == ["reviewer", "architect", "test-runner", "build"]
    assert config.require_mcp is False
    assert config.mcp_args == []
    assert config.exclude_dirs == [".venv", "node_modules", ".git"]
    assert config.coordinator is False
    assert config.memory is False


def test_load_config_from_toml(tmp_path: Path) -> None:
    toml_path = tmp_path / "multiagent.toml"
    toml_path.write_text(
        """
[multiagent]
model = "qwen2.5-coder"
agents = ["reviewer", "github_pr"]
require_mcp = true
mcp_command = "python"
mcp_args = ["-m", "mcp_server"]
exclude_dirs = ["node_modules"]
"""
    )
    config = load_config(toml_path)
    assert config.model == "qwen2.5-coder"
    assert config.agents == ["reviewer", "github_pr"]
    assert config.require_mcp is True
    assert config.mcp_command == "python"
    assert config.mcp_args == ["-m", "mcp_server"]
    assert config.exclude_dirs == ["node_modules"]


def test_load_config_invalid_toml(tmp_path: Path) -> None:
    toml_path = tmp_path / "bad.toml"
    toml_path.write_text("bad syntax [")
    config = load_config(toml_path)
    assert config.model is None


def test_load_config_reads_v02_platform_options(tmp_path: Path) -> None:
    toml_path = tmp_path / ".multiagent.toml"
    toml_path.write_text(
        "\n".join(
            [
                "[multiagent]",
                "coordinator = true",
                "memory = true",
                "security = true",
                "knowledge_graph = true",
                "max_agent_iterations = 3",
                'memory_path = ".multiagent/custom.sqlite"',
                "",
                "[multiagent.benchmark]",
                "models = [",
                '  { name = "qwen", provider = "ollama", model = "qwen2.5" },',
                "]",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(toml_path)

    assert config.coordinator is True
    assert config.memory is True
    assert config.security is True
    assert config.knowledge_graph is True
    assert config.max_agent_iterations == 3
    assert config.memory_config.path == ".multiagent/custom.sqlite"
    assert config.benchmark_models[0].name == "qwen"
