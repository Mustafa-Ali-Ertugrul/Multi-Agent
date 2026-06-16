from pathlib import Path

from multiagent.config import load_config


def test_load_config_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path / "non_existent.toml")
    assert config.model is None
    assert config.agents == ["reviewer", "architect", "test-runner", "build"]
    assert config.require_mcp is False
    assert config.mcp_args == []
    assert config.exclude_dirs == [".git", "__pycache__", ".venv", "venv"]


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
