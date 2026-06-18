"""Test that ``python -m multiagent`` entry point works."""

import subprocess
import sys


def test_python_m_multiagent_runs() -> None:
    """``python -m multiagent`` should execute without import errors."""
    import os

    env = dict(os.environ)
    env["PYTHONPATH"] = "src"

    result = subprocess.run(
        [sys.executable, "-m", "multiagent", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    # Should exit 0 and show help text
    assert result.returncode == 0
    assert "analyze" in result.stdout.lower() or "usage" in result.stdout.lower()
