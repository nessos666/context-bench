import subprocess
import sys
import os

ROOT = os.path.dirname(os.path.dirname(__file__))


def run_subprocess(mode: str, stdin: str = "{}") -> subprocess.CompletedProcess:
    """Run hook as subprocess — only use for exit-code checks, not logic tests."""
    return subprocess.run(
        [sys.executable, os.path.join(ROOT, "context_bench.py"), mode],
        input=stdin,
        capture_output=True,
        text=True,
    )


def test_prompt_exits_zero():
    result = run_subprocess("prompt", '{"prompt": "fix the api", "session_id": "s1"}')
    assert result.returncode == 0


def test_track_exits_zero():
    result = run_subprocess(
        "track", '{"session_id": "s1", "tool_input": {"file_path": "/tmp/x.py"}}'
    )
    assert result.returncode == 0


def test_learn_exits_zero():
    result = run_subprocess("learn", '{"session_id": "s1"}')
    assert result.returncode == 0
