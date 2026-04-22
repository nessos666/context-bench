# context-bench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-learning Claude Code hook that automatically detects the current project from the first user message and injects relevant file context — without any manual configuration.

**Architecture:** Single Python file `context_bench.py` handles three hook modes (`prompt`, `track`, `learn`) via CLI argument. Data is stored in `~/.context-bench/projects.json`. Three Claude Code hooks wire it together: UserPromptSubmit injects context, PostToolUse tracks file changes, SessionEnd updates confidence scores. The original prompt is persisted in the session file during `cmd_prompt()` so `cmd_learn()` can access it for new topic detection.

**Tech Stack:** Python 3.9+, stdlib only (json, os, sys, pathlib, re, datetime, tempfile, signal)

---

## File Structure

```
context-bench/
├── context_bench.py          ← Main hook script (all logic here)
├── install.sh                ← Writes 3 hooks into ~/.claude/settings.json
├── uninstall.sh              ← Removes hooks from settings.json
├── tests/
│   └── test_context_bench.py ← All tests (pytest) — tests handlers directly, not via subprocess
├── examples/
│   ├── python-project.json
│   ├── node-project.json
│   └── rust-project.json
├── .github/workflows/
│   └── tests.yml
├── CONTRIBUTING.md
├── README.md
└── LICENSE
```

**Testing note:** Handler functions (`cmd_prompt`, `cmd_track`, `cmd_learn`) are tested by calling them directly with patched `sys.stdin`/`sys.stdout` — NOT via subprocess. This avoids monkeypatch being silently ignored in child processes.

---

### Task 1: Project scaffold

**Files:**
- Create: `context_bench.py` (empty scaffold)
- Create: `tests/test_context_bench.py` (empty)
- Create: `README.md`, `LICENSE`, `CONTRIBUTING.md`

- [ ] **Step 1: Init git repo and create file structure**

```bash
cd /home/boobi/HAUPTLAGER/05_Strategien_Entwicklung/context-bench
git init
touch context_bench.py
mkdir -p tests examples .github/workflows
touch tests/test_context_bench.py tests/__init__.py
touch examples/python-project.json examples/node-project.json examples/rust-project.json
touch .github/workflows/tests.yml
touch CONTRIBUTING.md
echo "# context-bench" > README.md
echo "MIT License" > LICENSE
```

- [ ] **Step 2: Write minimal context_bench.py scaffold**

```python
#!/usr/bin/env python3
"""context-bench — self-learning Claude Code hook for automatic context injection."""
from __future__ import annotations

import json
import os
import sys


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: context_bench.py [prompt|track|learn]", file=sys.stderr)
        sys.exit(1)
    mode = sys.argv[1]
    if mode == "prompt":
        cmd_prompt()
    elif mode == "track":
        cmd_track()
    elif mode == "learn":
        cmd_learn()
    else:
        print(f"Unknown mode: {mode}", file=sys.stderr)
        sys.exit(1)


def cmd_prompt() -> None:
    sys.exit(0)


def cmd_track() -> None:
    sys.exit(0)


def cmd_learn() -> None:
    sys.exit(0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Write smoke test (subprocess, just exit codes)**

```python
# tests/test_context_bench.py
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
    result = run_subprocess("track", '{"session_id": "s1", "tool_input": {"file_path": "/tmp/x.py"}}')
    assert result.returncode == 0


def test_learn_exits_zero():
    result = run_subprocess("learn", '{"session_id": "s1"}')
    assert result.returncode == 0
```

- [ ] **Step 4: Run tests**

```bash
cd /home/boobi/HAUPTLAGER/05_Strategien_Entwicklung/context-bench
pytest tests/test_context_bench.py -v
```

Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add context_bench.py tests/ examples/ .github/ CONTRIBUTING.md README.md LICENSE
git commit -m "feat: project scaffold with empty hook modes"
```

---

### Task 2: Data model + DB helpers

**Files:**
- Modify: `context_bench.py` — add dataclasses, load_db, save_db, session helpers

**Design decision:** Session files live at `~/.context-bench/sessions/<session_id>.json` (not `session_changes.json` from spec — per-session files are safer for concurrent hooks).

- [ ] **Step 1: Write failing tests**

```python
# Add to tests/test_context_bench.py
import json
import os
import io
import sys
import tempfile
import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from context_bench import (
    Topic, Settings, Database,
    load_db, save_db, load_session, save_session, add_session_change, cleanup_session,
)


def test_default_settings():
    s = Settings()
    assert s.max_context_chars == 8000
    assert s.min_confidence_threshold == 0.3
    assert s.match_threshold == 0.5
    assert s.decay_days == 30


def test_topic_creation():
    t = Topic(id="api", keywords=["api", "route"], root="/home/user/proj", paths=["src/api/"])
    assert t.confidence == 0.5
    assert t.uses == 0


def test_save_and_load_db(tmp_path):
    db_path = str(tmp_path / "projects.json")
    db = Database(projects=[
        Topic(id="api", keywords=["api"], root="/proj", paths=["src/"])
    ])
    save_db(db, db_path=db_path)
    loaded = load_db(db_path=db_path)
    assert loaded is not None
    assert len(loaded.projects) == 1
    assert loaded.projects[0].id == "api"


def test_load_db_returns_none_when_missing(tmp_path):
    assert load_db(db_path=str(tmp_path / "nonexistent.json")) is None


def test_save_session_and_load(tmp_path):
    session_dir = str(tmp_path / "sessions")
    save_session("s1", "api", [], "", [], session_dir=session_dir)
    s = load_session("s1", session_dir=session_dir)
    assert s["matched_topic"] == "api"
    assert s["changed_files"] == []


def test_add_session_change(tmp_path):
    session_dir = str(tmp_path / "sessions")
    save_session("s2", "api", [], "", [], session_dir=session_dir)
    add_session_change("s2", "/proj/src/api.py", session_dir=session_dir)
    s = load_session("s2", session_dir=session_dir)
    assert "/proj/src/api.py" in s["changed_files"]


def test_add_session_change_deduplicates(tmp_path):
    session_dir = str(tmp_path / "sessions")
    save_session("s3", None, [], "", [], session_dir=session_dir)
    add_session_change("s3", "/tmp/x.py", session_dir=session_dir)
    add_session_change("s3", "/tmp/x.py", session_dir=session_dir)
    s = load_session("s3", session_dir=session_dir)
    assert s["changed_files"].count("/tmp/x.py") == 1


def test_cleanup_session(tmp_path):
    session_dir = str(tmp_path / "sessions")
    save_session("s4", None, [], "", [], session_dir=session_dir)
    assert load_session("s4", session_dir=session_dir) is not None
    cleanup_session("s4", session_dir=session_dir)
    assert load_session("s4", session_dir=session_dir) is None
```

- [ ] **Step 2: Run tests — must FAIL**

```bash
pytest tests/test_context_bench.py::test_default_settings -v
```

Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement data model in context_bench.py**

Replace entire file:

```python
#!/usr/bin/env python3
"""context-bench — self-learning Claude Code hook for automatic context injection."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path
from typing import Optional

# ── Default paths (overridable via parameters for testing) ───────────────────
_DEFAULT_DB_DIR = os.path.expanduser("~/.context-bench")
_DEFAULT_DB_PATH = os.path.join(_DEFAULT_DB_DIR, "projects.json")
_DEFAULT_SESSION_DIR = os.path.join(_DEFAULT_DB_DIR, "sessions")
_DEFAULT_ERROR_LOG = os.path.join(_DEFAULT_DB_DIR, "error.log")


# ── Data model ───────────────────────────────────────────────────────────────
@dataclass
class Topic:
    id: str
    keywords: list[str]
    root: str
    paths: list[str]
    confidence: float = 0.5
    uses: int = 0
    last_used: Optional[str] = None
    created: str = field(default_factory=lambda: date.today().isoformat())


@dataclass(frozen=True)
class Settings:
    max_context_chars: int = 8000
    min_confidence_threshold: float = 0.3
    match_threshold: float = 0.5
    decay_days: int = 30


@dataclass
class Database:
    version: int = 1
    projects: list[Topic] = field(default_factory=list)
    settings: Settings = field(default_factory=Settings)


# ── DB helpers ───────────────────────────────────────────────────────────────
def load_db(db_path: str = _DEFAULT_DB_PATH) -> Optional[Database]:
    if not os.path.exists(db_path):
        return None
    try:
        with open(db_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        projects = [Topic(**p) for p in raw.get("projects", [])]
        settings_raw = raw.get("settings", {})
        valid_keys = {f.name for f in Settings.__dataclass_fields__.values()} if hasattr(Settings, '__dataclass_fields__') else set(asdict(Settings()).keys())
        settings = Settings(**{k: v for k, v in settings_raw.items() if k in valid_keys})
        return Database(version=raw.get("version", 1), projects=projects, settings=settings)
    except Exception as e:
        _log_error(f"load_db failed: {e}")
        return None


def save_db(db: Database, db_path: str = _DEFAULT_DB_PATH) -> None:
    db_dir = os.path.dirname(db_path)
    os.makedirs(db_dir, exist_ok=True)
    data = {
        "version": db.version,
        "projects": [asdict(p) for p in db.projects],
        "settings": asdict(db.settings),
    }
    tmp_fd, tmp_path = tempfile.mkstemp(dir=db_dir, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, db_path)  # atomic on POSIX
    except Exception as e:
        _log_error(f"save_db failed: {e}")
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _log_error(msg: str, error_log: str = _DEFAULT_ERROR_LOG) -> None:
    os.makedirs(os.path.dirname(error_log), exist_ok=True)
    try:
        with open(error_log, "a", encoding="utf-8") as f:
            f.write(f"{date.today().isoformat()} {msg}\n")
    except OSError:
        pass


# ── Session helpers ───────────────────────────────────────────────────────────
def _session_path(session_id: str, session_dir: str = _DEFAULT_SESSION_DIR) -> str:
    os.makedirs(session_dir, exist_ok=True)
    safe = session_id.replace("/", "_")[:64]
    return os.path.join(session_dir, f"{safe}.json")


def load_session(session_id: str, session_dir: str = _DEFAULT_SESSION_DIR) -> Optional[dict]:
    path = _session_path(session_id, session_dir)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_session(
    session_id: str,
    matched_topic: Optional[str],
    changed_files: list[str],
    prompt: str,
    injected_paths: list[str],
    session_dir: str = _DEFAULT_SESSION_DIR,
) -> None:
    """Save session state. prompt and injected_paths are needed by cmd_learn."""
    path = _session_path(session_id, session_dir)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=session_dir, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump({
                "session_id": session_id,
                "matched_topic": matched_topic,
                "changed_files": changed_files,
                "prompt": prompt,
                "injected_paths": injected_paths,
            }, f)
        os.replace(tmp_path, path)
    except Exception as e:
        _log_error(f"save_session failed: {e}")
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def add_session_change(session_id: str, file_path: str, session_dir: str = _DEFAULT_SESSION_DIR) -> None:
    session = load_session(session_id, session_dir) or {
        "session_id": session_id, "matched_topic": None,
        "changed_files": [], "prompt": "", "injected_paths": [],
    }
    if file_path and file_path not in session["changed_files"]:
        session["changed_files"].append(file_path)
    save_session(
        session_id,
        session.get("matched_topic"),
        session["changed_files"],
        session.get("prompt", ""),
        session.get("injected_paths", []),
        session_dir=session_dir,
    )


def cleanup_session(session_id: str, session_dir: str = _DEFAULT_SESSION_DIR) -> None:
    path = _session_path(session_id, session_dir)
    if os.path.exists(path):
        os.unlink(path)


# ── Hook entry points (to be implemented in later tasks) ─────────────────────
def cmd_prompt() -> None:
    sys.exit(0)


def cmd_track() -> None:
    sys.exit(0)


def cmd_learn() -> None:
    sys.exit(0)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: context_bench.py [prompt|track|learn]", file=sys.stderr)
        sys.exit(1)
    mode = sys.argv[1]
    if mode == "prompt":
        cmd_prompt()
    elif mode == "track":
        cmd_track()
    elif mode == "learn":
        cmd_learn()
    else:
        print(f"Unknown mode: {mode}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests — must pass**

```bash
pytest tests/test_context_bench.py -v
```

Expected: all PASS (3 smoke + 8 new DB tests = 11 total)

- [ ] **Step 5: Commit**

```bash
git add context_bench.py tests/test_context_bench.py
git commit -m "feat: data model, atomic DB save, session helpers with prompt persistence"
```

---

### Task 3: Matcher

**Files:**
- Modify: `context_bench.py` — add `compute_match_score()`
- Modify: `tests/test_context_bench.py` — add matcher tests

- [ ] **Step 1: Write failing tests**

```python
# Add to tests/test_context_bench.py
import pytest
from context_bench import compute_match_score, Topic


def test_partial_keyword_match():
    topic = Topic(id="api", keywords=["api", "route", "fastapi"], root="/p", paths=[])
    score = compute_match_score("fix the api route", topic)
    assert score == pytest.approx(2/3, abs=0.01)


def test_no_keyword_match():
    topic = Topic(id="api", keywords=["api", "route"], root="/p", paths=[])
    score = compute_match_score("fix the database", topic)
    assert score == 0.0


def test_all_keywords_match():
    topic = Topic(id="api", keywords=["api", "route"], root="/p", paths=[])
    score = compute_match_score("fix the api route endpoint", topic)
    assert score == 1.0


def test_empty_keywords():
    topic = Topic(id="api", keywords=[], root="/p", paths=[])
    score = compute_match_score("anything", topic)
    assert score == 0.0


def test_case_insensitive():
    topic = Topic(id="api", keywords=["API"], root="/p", paths=[])
    score = compute_match_score("fix the api", topic)
    assert score == 1.0


def test_match_score_exactly_at_threshold():
    # score == match_threshold (0.5) must be counted as a match
    topic = Topic(id="api", keywords=["api", "route"], root="/p", paths=[])
    score = compute_match_score("fix the api", topic)
    assert score == pytest.approx(0.5)
    assert score >= 0.5  # must be treated as match
```

- [ ] **Step 2: Run tests — must FAIL**

```bash
pytest tests/test_context_bench.py::test_partial_keyword_match -v
```

Expected: FAIL with `ImportError: cannot import name 'compute_match_score'`

- [ ] **Step 3: Add compute_match_score to context_bench.py**

Add after the session helpers section, before the hook entry points:

```python
# ── Matcher ───────────────────────────────────────────────────────────────────
def compute_match_score(prompt: str, topic: Topic) -> float:
    """Returns fraction of topic keywords found in prompt (0.0–1.0)."""
    if not topic.keywords:
        return 0.0
    prompt_lower = prompt.lower()
    matches = sum(1 for kw in topic.keywords if kw.lower() in prompt_lower)
    return matches / len(topic.keywords)
```

- [ ] **Step 4: Run tests — must pass**

```bash
pytest tests/test_context_bench.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add context_bench.py tests/test_context_bench.py
git commit -m "feat: keyword matcher with case-insensitive scoring"
```

---

### Task 4: Loader

**Files:**
- Modify: `context_bench.py` — add `load_context()`
- Modify: `tests/test_context_bench.py` — add loader tests

- [ ] **Step 1: Write failing tests**

```python
# Add to tests/test_context_bench.py
from context_bench import load_context


def test_load_single_file(tmp_path):
    f = tmp_path / "routes.py"
    f.write_text("def get(): return 42\n")
    topic = Topic(id="api", keywords=[], root=str(tmp_path), paths=["routes.py"])
    ctx = load_context(topic, max_chars=8000)
    assert "routes.py" in ctx
    assert "def get(): return 42" in ctx


def test_load_truncates_at_max_chars(tmp_path):
    f = tmp_path / "big.py"
    f.write_text("x" * 10000)
    topic = Topic(id="big", keywords=[], root=str(tmp_path), paths=["big.py"])
    ctx = load_context(topic, max_chars=500)
    assert len(ctx) <= 600
    assert "[truncated]" in ctx


def test_load_directory_lists_files(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("# file a")
    (src / "b.py").write_text("# file b")
    topic = Topic(id="src", keywords=[], root=str(tmp_path), paths=["src/"])
    ctx = load_context(topic, max_chars=8000)
    assert "# file a" in ctx or "# file b" in ctx


def test_load_missing_file_does_not_crash(tmp_path):
    topic = Topic(id="x", keywords=[], root=str(tmp_path), paths=["nonexistent.py"])
    ctx = load_context(topic, max_chars=8000)
    assert isinstance(ctx, str)


def test_load_binary_file_skipped(tmp_path):
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    topic = Topic(id="x", keywords=[], root=str(tmp_path), paths=["image.png"])
    ctx = load_context(topic, max_chars=8000)
    # binary file skipped — just header
    assert "image.png" not in ctx or "PNG" not in ctx
```

- [ ] **Step 2: Run tests — must FAIL**

```bash
pytest tests/test_context_bench.py::test_load_single_file -v
```

Expected: FAIL with `ImportError: cannot import name 'load_context'`

- [ ] **Step 3: Add load_context to context_bench.py**

Add after `compute_match_score`:

```python
# ── Loader ───────────────────────────────────────────────────────────────────
_BINARY_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".tar", ".gz",
                ".exe", ".so", ".dylib", ".pyc", ".db", ".sqlite", ".bin"}


def load_context(topic: Topic, max_chars: int) -> str:
    """Read topic files and build context string. Truncates at max_chars."""
    header = f"## Projekt-Kontext (auto-geladen)\n\nTopic: {topic.id}\nDateien:\n\n"
    parts: list[str] = []
    remaining = max_chars - len(header)

    for rel_path in topic.paths:
        abs_path = os.path.join(topic.root, rel_path)
        for file_abs in _collect_files(abs_path):
            if remaining <= 0:
                break
            content = _read_file_safe(file_abs)
            if content is None:
                continue
            rel = os.path.relpath(file_abs, topic.root)
            section = f"### {rel}\n{content}\n\n"
            if len(section) > remaining:
                section = section[:remaining] + "\n[truncated]\n"
                parts.append(section)
                remaining = 0
                break
            parts.append(section)
            remaining -= len(section)

    return header + "".join(parts)


def _collect_files(path: str) -> list[str]:
    if os.path.isfile(path):
        return [path]
    if os.path.isdir(path):
        try:
            return sorted(
                os.path.join(path, e) for e in os.listdir(path)
                if os.path.isfile(os.path.join(path, e))
            )
        except OSError:
            return []
    return []


def _read_file_safe(path: str) -> Optional[str]:
    if Path(path).suffix.lower() in _BINARY_EXTS:
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None
```

- [ ] **Step 4: Run tests — must pass**

```bash
pytest tests/test_context_bench.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add context_bench.py tests/test_context_bench.py
git commit -m "feat: file loader with truncation and binary file skip"
```

---

### Task 5: Bootstrap

**Files:**
- Modify: `context_bench.py` — add `bootstrap()`
- Modify: `tests/test_context_bench.py` — add bootstrap tests

- [ ] **Step 1: Write failing tests**

```python
# Add to tests/test_context_bench.py
from context_bench import bootstrap


def test_bootstrap_detects_python(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.poetry]\nname="test"')
    db = bootstrap(str(tmp_path), timeout_ms=500)
    assert db is not None
    assert any(t.id == "python" for t in db.projects)


def test_bootstrap_detects_node(tmp_path):
    (tmp_path / "package.json").write_text('{"name": "test"}')
    db = bootstrap(str(tmp_path), timeout_ms=500)
    assert any(t.id == "node" for t in db.projects)


def test_bootstrap_unknown_returns_empty_db(tmp_path):
    db = bootstrap(str(tmp_path), timeout_ms=500)
    assert db is not None
    assert db.projects == []


def test_bootstrap_sets_correct_root(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    db = bootstrap(str(tmp_path), timeout_ms=500)
    for topic in db.projects:
        assert topic.root == str(tmp_path)


def test_bootstrap_completes_within_timeout(tmp_path):
    import time
    # Create many files to stress the scanner
    for i in range(200):
        (tmp_path / f"file_{i}.py").write_text("x = 1")
    start = time.monotonic()
    bootstrap(str(tmp_path), timeout_ms=200)
    elapsed_ms = (time.monotonic() - start) * 1000
    assert elapsed_ms < 400  # must finish well under double the timeout
```

- [ ] **Step 2: Run tests — must FAIL**

```bash
pytest tests/test_context_bench.py::test_bootstrap_detects_python -v
```

Expected: FAIL with `ImportError: cannot import name 'bootstrap'`

- [ ] **Step 3: Add bootstrap to context_bench.py**

Add after the Loader section:

```python
# ── Bootstrap ─────────────────────────────────────────────────────────────────
import time as _time

_FRAMEWORK_MARKERS: list[tuple[str, str, list[str], list[str]]] = [
    ("pyproject.toml",  "python", ["python", "pip", "pytest", "uv", "poetry"], ["src/", "tests/"]),
    ("requirements.txt","python", ["python", "pip", "requirements"],           ["src/", "tests/"]),
    ("setup.py",        "python", ["python", "setup", "package"],              ["src/", "tests/"]),
    ("package.json",    "node",   ["node", "npm", "javascript", "typescript"],  ["src/", "lib/"]),
    ("go.mod",          "go",     ["go", "golang", "module"],                   ["cmd/", "pkg/"]),
    ("Cargo.toml",      "rust",   ["rust", "cargo", "crate"],                   ["src/"]),
    ("pom.xml",         "java",   ["java", "maven", "spring"],                  ["src/main/", "src/test/"]),
]


def bootstrap(cwd: str, timeout_ms: int = 200) -> Database:
    """Scan cwd for known project patterns. Hard timeout to avoid blocking hooks."""
    deadline = _time.monotonic() + timeout_ms / 1000.0
    projects: list[Topic] = []
    today = date.today().isoformat()

    try:
        for marker, topic_id, keywords, scan_dirs in _FRAMEWORK_MARKERS:
            if _time.monotonic() > deadline:
                break
            if os.path.exists(os.path.join(cwd, marker)):
                existing = [d for d in scan_dirs
                            if os.path.isdir(os.path.join(cwd, d))
                            and _time.monotonic() < deadline]
                paths = existing if existing else [marker]
                projects.append(Topic(
                    id=topic_id,
                    keywords=keywords,
                    root=cwd,
                    paths=paths,
                    confidence=0.5,
                    uses=0,
                    last_used=None,
                    created=today,
                ))
                break
    except Exception as e:
        _log_error(f"bootstrap error: {e}")

    return Database(projects=projects)
```

- [ ] **Step 4: Run tests — must pass**

```bash
pytest tests/test_context_bench.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add context_bench.py tests/test_context_bench.py
git commit -m "feat: bootstrap with 200ms timeout and framework detection"
```

---

### Task 6: `prompt` command (UserPromptSubmit)

**Files:**
- Modify: `context_bench.py` — implement `cmd_prompt()`
- Modify: `tests/test_context_bench.py` — add prompt tests

**Testing approach:** Call `cmd_prompt()` directly. Patch `sys.stdin` with `io.StringIO`. Capture stdout with `capsys`. Pass `db_path`, `session_dir`, `cwd` as function parameters (injected for testing).

- [ ] **Step 1: Write failing tests**

```python
# Add to tests/test_context_bench.py
import io
from context_bench import cmd_prompt, save_db, Database, Topic, load_session


def _make_db(tmp_path, root=None) -> Database:
    r = root or str(tmp_path)
    (tmp_path / "routes.py").write_text("def get_route(): pass\n")
    return Database(projects=[
        Topic(id="api", keywords=["api", "route", "endpoint"], root=r, paths=["routes.py"], confidence=0.8)
    ])


def test_prompt_injects_context_on_match(tmp_path, monkeypatch, capsys):
    db_path = str(tmp_path / "projects.json")
    session_dir = str(tmp_path / "sessions")
    save_db(_make_db(tmp_path), db_path=db_path)

    monkeypatch.setattr("sys.stdin", io.StringIO(
        json.dumps({"prompt": "fix the api route", "session_id": "p-s1"})
    ))
    with pytest.raises(SystemExit):
        cmd_prompt(db_path=db_path, session_dir=session_dir, cwd=str(tmp_path))

    out = capsys.readouterr().out
    result = json.loads(out)
    assert "hookSpecificOutput" in result
    ctx = result["hookSpecificOutput"]["additionalContext"]
    assert "api" in ctx
    assert "get_route" in ctx


def test_prompt_no_output_on_no_match(tmp_path, monkeypatch, capsys):
    db_path = str(tmp_path / "projects.json")
    session_dir = str(tmp_path / "sessions")
    save_db(_make_db(tmp_path), db_path=db_path)

    monkeypatch.setattr("sys.stdin", io.StringIO(
        json.dumps({"prompt": "talk about gardening", "session_id": "p-s2"})
    ))
    with pytest.raises(SystemExit):
        cmd_prompt(db_path=db_path, session_dir=session_dir, cwd=str(tmp_path))

    out = capsys.readouterr().out
    assert json.loads(out) == {}


def test_prompt_persists_prompt_in_session(tmp_path, monkeypatch, capsys):
    db_path = str(tmp_path / "projects.json")
    session_dir = str(tmp_path / "sessions")
    save_db(_make_db(tmp_path), db_path=db_path)

    monkeypatch.setattr("sys.stdin", io.StringIO(
        json.dumps({"prompt": "fix the api route", "session_id": "p-s3"})
    ))
    with pytest.raises(SystemExit):
        cmd_prompt(db_path=db_path, session_dir=session_dir, cwd=str(tmp_path))

    session = load_session("p-s3", session_dir=session_dir)
    assert session["prompt"] == "fix the api route"
    assert session["matched_topic"] == "api"


def test_prompt_filters_by_cwd(tmp_path, monkeypatch, capsys):
    """Topics from a different root must NOT be matched."""
    db_path = str(tmp_path / "projects.json")
    session_dir = str(tmp_path / "sessions")
    other_root = str(tmp_path / "other_project")
    # Topic belongs to other_project, not cwd
    db = Database(projects=[
        Topic(id="api", keywords=["api", "route"], root=other_root, paths=["src/"])
    ])
    save_db(db, db_path=db_path)

    monkeypatch.setattr("sys.stdin", io.StringIO(
        json.dumps({"prompt": "fix the api route", "session_id": "p-s4"})
    ))
    with pytest.raises(SystemExit):
        cmd_prompt(db_path=db_path, session_dir=session_dir, cwd=str(tmp_path))

    out = capsys.readouterr().out
    assert json.loads(out) == {}


def test_prompt_bootstraps_when_no_db(tmp_path, monkeypatch, capsys):
    db_path = str(tmp_path / "projects.json")
    session_dir = str(tmp_path / "sessions")

    monkeypatch.setattr("sys.stdin", io.StringIO(
        json.dumps({"prompt": "hello world", "session_id": "boot-s1"})
    ))
    with pytest.raises(SystemExit):
        cmd_prompt(db_path=db_path, session_dir=session_dir, cwd=str(tmp_path))

    # Must not crash even when no DB exists
    out = capsys.readouterr().out
    assert json.loads(out) == {} or "hookSpecificOutput" in json.loads(out)
```

- [ ] **Step 2: Run tests — must FAIL**

```bash
pytest tests/test_context_bench.py::test_prompt_injects_context_on_match -v
```

Expected: FAIL (cmd_prompt ignores parameters)

- [ ] **Step 3: Implement cmd_prompt() in context_bench.py**

Replace empty `cmd_prompt()`:

```python
def cmd_prompt(
    db_path: str = _DEFAULT_DB_PATH,
    session_dir: str = _DEFAULT_SESSION_DIR,
    cwd: Optional[str] = None,
) -> None:
    """Handle UserPromptSubmit: read prompt, match topic, inject context."""
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}

    prompt = data.get("prompt", "")
    session_id = data.get("session_id", "unknown")
    if cwd is None:
        cwd = os.getcwd()

    try:
        db = load_db(db_path)
        if db is None:
            db = bootstrap(cwd)
            save_db(db, db_path)

        best_topic: Optional[Topic] = None
        best_score = 0.0
        for topic in db.projects:
            # Only match topics that belong to the current working directory
            if not (cwd == topic.root or cwd.startswith(topic.root + os.sep)):
                continue
            score = compute_match_score(prompt, topic)
            if score > best_score:
                best_score, best_topic = score, topic

        if best_topic and best_score >= db.settings.match_threshold:
            context = load_context(best_topic, db.settings.max_context_chars)
            injected = [os.path.join(best_topic.root, p) for p in best_topic.paths]
            save_session(session_id, best_topic.id, [], prompt, injected, session_dir)

            best_topic.confidence = min(1.0, best_topic.confidence + 0.05)
            best_topic.uses += 1
            best_topic.last_used = date.today().isoformat()
            save_db(db, db_path)

            output: dict = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": context,
                }
            }
        else:
            save_session(session_id, None, [], prompt, [], session_dir)
            output = {}

        print(json.dumps(output))
    except Exception as e:
        _log_error(f"cmd_prompt error: {e}")
        print("{}")
    sys.exit(0)
```

- [ ] **Step 4: Run tests — must pass**

```bash
pytest tests/test_context_bench.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add context_bench.py tests/test_context_bench.py
git commit -m "feat: UserPromptSubmit handler with cwd-filter, session persistence"
```

---

### Task 7: `track` command (PostToolUse)

**Files:**
- Modify: `context_bench.py` — implement `cmd_track()`
- Modify: `tests/test_context_bench.py` — add track tests

- [ ] **Step 1: Write failing tests**

```python
# Add to tests/test_context_bench.py
from context_bench import cmd_track


def test_track_records_changed_file(tmp_path, monkeypatch):
    session_dir = str(tmp_path / "sessions")
    save_session("t-s1", "api", [], "fix api", ["/proj/src/api/"], session_dir=session_dir)

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({
        "session_id": "t-s1",
        "tool_input": {"file_path": "/proj/src/api/routes.py"},
    })))
    with pytest.raises(SystemExit):
        cmd_track(session_dir=session_dir)

    s = load_session("t-s1", session_dir=session_dir)
    assert "/proj/src/api/routes.py" in s["changed_files"]


def test_track_no_crash_when_session_missing(tmp_path, monkeypatch):
    session_dir = str(tmp_path / "sessions")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({
        "session_id": "no-session",
        "tool_input": {"file_path": "/tmp/x.py"},
    })))
    with pytest.raises(SystemExit):
        cmd_track(session_dir=session_dir)
    # Must not crash


def test_track_deduplicates_files(tmp_path, monkeypatch):
    session_dir = str(tmp_path / "sessions")
    save_session("t-s2", None, ["/tmp/x.py"], "", [], session_dir=session_dir)

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({
        "session_id": "t-s2",
        "tool_input": {"file_path": "/tmp/x.py"},
    })))
    with pytest.raises(SystemExit):
        cmd_track(session_dir=session_dir)

    s = load_session("t-s2", session_dir=session_dir)
    assert s["changed_files"].count("/tmp/x.py") == 1
```

- [ ] **Step 2: Run tests — must FAIL**

```bash
pytest tests/test_context_bench.py::test_track_records_changed_file -v
```

Expected: FAIL

- [ ] **Step 3: Implement cmd_track() in context_bench.py**

Replace empty `cmd_track()`:

```python
def cmd_track(session_dir: str = _DEFAULT_SESSION_DIR) -> None:
    """Handle PostToolUse: record changed file path to session tracker."""
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}

    session_id = data.get("session_id", "")
    tool_input = data.get("tool_input", {})
    changed_file = tool_input.get("file_path") or tool_input.get("path", "")

    try:
        if session_id and changed_file:
            add_session_change(session_id, changed_file, session_dir)
    except Exception as e:
        _log_error(f"cmd_track error: {e}")

    sys.exit(0)
```

- [ ] **Step 4: Run tests — must pass**

```bash
pytest tests/test_context_bench.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add context_bench.py tests/test_context_bench.py
git commit -m "feat: PostToolUse handler — track changed files per session"
```

---

### Task 8: `learn` command (SessionEnd)

**Files:**
- Modify: `context_bench.py` — implement `cmd_learn()`, `apply_decay()`
- Modify: `tests/test_context_bench.py` — add learn tests

**Important:** decay is applied BEFORE removing dead topics, so topics killed by decay are cleaned up in the same session.

- [ ] **Step 1: Write failing tests**

```python
# Add to tests/test_context_bench.py
from context_bench import cmd_learn, apply_decay
from datetime import timedelta


def test_learn_increases_confidence_when_files_changed(tmp_path, monkeypatch):
    db_path = str(tmp_path / "projects.json")
    session_dir = str(tmp_path / "sessions")
    save_db(Database(projects=[
        Topic(id="api", keywords=["api"], root="/proj", paths=["src/api/"], confidence=0.5)
    ]), db_path=db_path)
    save_session("l-s1", "api", ["/proj/src/api/routes.py"], "fix api", ["/proj/src/api/"], session_dir=session_dir)

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "l-s1"})))
    with pytest.raises(SystemExit):
        cmd_learn(db_path=db_path, session_dir=session_dir)

    loaded = load_db(db_path=db_path)
    assert loaded.projects[0].confidence == pytest.approx(0.65, abs=0.01)


def test_learn_decreases_confidence_when_files_not_changed(tmp_path, monkeypatch):
    db_path = str(tmp_path / "projects.json")
    session_dir = str(tmp_path / "sessions")
    save_db(Database(projects=[
        Topic(id="api", keywords=["api"], root="/proj", paths=["src/api/"], confidence=0.5)
    ]), db_path=db_path)
    save_session("l-s2", "api", [], "fix api", ["/proj/src/api/"], session_dir=session_dir)

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "l-s2"})))
    with pytest.raises(SystemExit):
        cmd_learn(db_path=db_path, session_dir=session_dir)

    loaded = load_db(db_path=db_path)
    assert loaded.projects[0].confidence == pytest.approx(0.45, abs=0.01)


def test_learn_removes_dead_topics(tmp_path, monkeypatch):
    db_path = str(tmp_path / "projects.json")
    session_dir = str(tmp_path / "sessions")
    save_db(Database(projects=[
        Topic(id="api", keywords=["api"], root="/proj", paths=["src/"], confidence=0.2)
    ]), db_path=db_path)
    save_session("l-s3", "api", [], "fix api", [], session_dir=session_dir)

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "l-s3"})))
    with pytest.raises(SystemExit):
        cmd_learn(db_path=db_path, session_dir=session_dir)

    loaded = load_db(db_path=db_path)
    assert len(loaded.projects) == 0


def test_apply_decay_reduces_old_topics():
    old_date = (date.today() - timedelta(days=40)).isoformat()
    db = Database(
        projects=[Topic(id="api", keywords=[], root="/p", paths=[], confidence=0.8, last_used=old_date)],
        settings=Settings(decay_days=30),
    )
    apply_decay(db)
    assert db.projects[0].confidence < 0.8


def test_apply_decay_ignores_recent_topics():
    db = Database(
        projects=[Topic(id="api", keywords=[], root="/p", paths=[], confidence=0.8, last_used=date.today().isoformat())],
        settings=Settings(decay_days=30),
    )
    apply_decay(db)
    assert db.projects[0].confidence == pytest.approx(0.8)


def test_learn_decay_applied_before_pruning(tmp_path, monkeypatch):
    """Topic at 0.32 that gets 10 days decay should fall below 0.3 and be removed."""
    db_path = str(tmp_path / "projects.json")
    session_dir = str(tmp_path / "sessions")
    old_date = (date.today() - timedelta(days=40)).isoformat()  # 10 days past decay
    save_db(Database(projects=[
        Topic(id="old", keywords=["old"], root="/p", paths=[], confidence=0.32, last_used=old_date)
    ]), db_path=db_path)
    save_session("l-s4", None, [], "", [], session_dir=session_dir)

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "l-s4"})))
    with pytest.raises(SystemExit):
        cmd_learn(db_path=db_path, session_dir=session_dir)

    loaded = load_db(db_path=db_path)
    assert len(loaded.projects) == 0
```

- [ ] **Step 2: Run tests — must FAIL**

```bash
pytest tests/test_context_bench.py::test_learn_increases_confidence_when_files_changed -v
```

Expected: FAIL

- [ ] **Step 3: Implement cmd_learn() and apply_decay() in context_bench.py**

Add `apply_decay()` and replace empty `cmd_learn()`:

```python
def apply_decay(db: Database) -> None:
    """Reduce confidence for topics not used within decay_days."""
    today = date.today()
    for topic in db.projects:
        if topic.last_used is None:
            continue
        try:
            last = date.fromisoformat(topic.last_used)
        except ValueError:
            continue
        days_idle = (today - last).days
        if days_idle > db.settings.decay_days:
            penalty = (days_idle - db.settings.decay_days) * 0.01
            topic.confidence = max(0.0, topic.confidence - penalty)


def cmd_learn(
    db_path: str = _DEFAULT_DB_PATH,
    session_dir: str = _DEFAULT_SESSION_DIR,
) -> None:
    """Handle SessionEnd: update confidence based on changed files, then decay."""
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}

    session_id = data.get("session_id", "")

    try:
        session = load_session(session_id, session_dir)
        if session is None:
            sys.exit(0)

        db = load_db(db_path)
        if db is None:
            cleanup_session(session_id, session_dir)
            sys.exit(0)

        matched_id = session.get("matched_topic")
        changed_files: list[str] = session.get("changed_files", [])
        injected_paths: list[str] = session.get("injected_paths", [])

        if matched_id:
            for topic in db.projects:
                if topic.id != matched_id:
                    continue
                files_used = any(
                    changed.startswith(inj.rstrip("/"))
                    for changed in changed_files
                    for inj in injected_paths
                )
                if files_used:
                    topic.confidence = min(1.0, topic.confidence + 0.15)
                else:
                    topic.confidence = max(0.0, topic.confidence - 0.05)
                break

        # Decay first, then prune — topics killed by decay are removed in same session
        apply_decay(db)
        db.projects = [t for t in db.projects if t.confidence >= db.settings.min_confidence_threshold]

        save_db(db, db_path)
        cleanup_session(session_id, session_dir)
    except Exception as e:
        _log_error(f"cmd_learn error: {e}")

    sys.exit(0)
```

- [ ] **Step 4: Run tests — must pass**

```bash
pytest tests/test_context_bench.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add context_bench.py tests/test_context_bench.py
git commit -m "feat: SessionEnd handler — confidence update, decay-then-prune"
```

---

### Task 9: New topic detection

**Files:**
- Modify: `context_bench.py` — add `_extract_keywords()`, new topic logic in `cmd_learn()`
- Modify: `tests/test_context_bench.py` — add new topic tests

- [ ] **Step 1: Write failing tests**

```python
# Add to tests/test_context_bench.py
from context_bench import _extract_keywords


def test_extract_keywords_from_prompt():
    kws = _extract_keywords("refactor the api models route endpoint", [])
    assert "api" in kws
    assert "models" in kws or "model" in kws


def test_extract_keywords_from_filenames():
    kws = _extract_keywords("", ["/proj/src/api/routes.py", "/proj/src/api/models.py"])
    assert "routes" in kws or "api" in kws or "models" in kws


def test_extract_keywords_excludes_stopwords():
    kws = _extract_keywords("fix the and or but", [])
    assert "the" not in kws
    assert "and" not in kws


def test_new_topic_created_when_no_match(tmp_path, monkeypatch):
    db_path = str(tmp_path / "projects.json")
    session_dir = str(tmp_path / "sessions")
    save_db(Database(projects=[]), db_path=db_path)
    save_session("n-s1", None, ["/proj/src/api/routes.py"], "refactor api endpoint", [], session_dir=session_dir)

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "n-s1"})))
    with pytest.raises(SystemExit):
        cmd_learn(db_path=db_path, session_dir=session_dir)

    loaded = load_db(db_path=db_path)
    assert len(loaded.projects) >= 1
    new_topic = loaded.projects[0]
    assert new_topic.confidence == pytest.approx(0.5)
    assert len(new_topic.keywords) > 0


def test_no_new_topic_when_no_files_changed(tmp_path, monkeypatch):
    db_path = str(tmp_path / "projects.json")
    session_dir = str(tmp_path / "sessions")
    save_db(Database(projects=[]), db_path=db_path)
    save_session("n-s2", None, [], "hello world", [], session_dir=session_dir)

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "n-s2"})))
    with pytest.raises(SystemExit):
        cmd_learn(db_path=db_path, session_dir=session_dir)

    loaded = load_db(db_path=db_path)
    assert len(loaded.projects) == 0
```

- [ ] **Step 2: Run tests — must FAIL**

```bash
pytest tests/test_context_bench.py::test_extract_keywords_from_prompt -v
```

Expected: FAIL with `ImportError`

- [ ] **Step 3: Add _extract_keywords and new topic logic to context_bench.py**

Add before `cmd_learn()`:

```python
_STOPWORDS = {"the", "a", "an", "is", "it", "in", "on", "at", "to", "for",
               "of", "and", "or", "but", "with", "from", "by", "i", "my",
               "this", "that", "how", "what", "why", "fix", "add", "get",
               "make", "run", "do", "can", "will", "please", "want", "need",
               "hello", "world"}


def _extract_keywords(prompt: str, changed_files: list[str]) -> list[str]:
    """Extract meaningful keywords from prompt words + changed file stems."""
    words: set[str] = set()
    for w in prompt.lower().split():
        w = w.strip(".,!?;:'\"()")
        if len(w) >= 3 and w not in _STOPWORDS and w.isalpha():
            words.add(w)
    for f in changed_files:
        stem = Path(f).stem.lower()
        for part in stem.replace("-", "_").split("_"):
            if len(part) >= 3 and part not in _STOPWORDS:
                words.add(part)
    return sorted(words)[:10]
```

Add new topic block inside `cmd_learn()`, after the `if matched_id:` block:

```python
        # New topic detection: only when no match but files were changed
        elif changed_files:
            prompt_text = session.get("prompt", "")
            keywords = _extract_keywords(prompt_text, changed_files)
            if keywords:
                try:
                    common = (os.path.commonpath(changed_files)
                              if len(changed_files) > 1
                              else os.path.dirname(changed_files[0]))
                except ValueError:
                    common = os.path.dirname(changed_files[0])
                rel_paths = list(dict.fromkeys(
                    os.path.relpath(f, common) for f in changed_files
                ))[:5]
                new_topic = Topic(
                    id=keywords[0],
                    keywords=keywords,
                    root=common,
                    paths=rel_paths,
                    confidence=0.5,
                    uses=1,
                    last_used=date.today().isoformat(),
                    created=date.today().isoformat(),
                )
                db.projects.append(new_topic)
```

- [ ] **Step 4: Run tests — must pass**

```bash
pytest tests/test_context_bench.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add context_bench.py tests/test_context_bench.py
git commit -m "feat: auto-create new topics from unmatched sessions with file changes"
```

---

### Task 10: install.sh + uninstall.sh

**Files:**
- Create: `install.sh`
- Create: `uninstall.sh`

- [ ] **Step 1: Write install.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_DIR="$HOME/.context-bench"
DEST_SCRIPT="$DEST_DIR/context_bench.py"
SETTINGS="$HOME/.claude/settings.json"

echo "Installing context-bench..."

mkdir -p "$DEST_DIR"
cp "$SCRIPT_DIR/context_bench.py" "$DEST_SCRIPT"
chmod +x "$DEST_SCRIPT"

if [ ! -f "$SETTINGS" ]; then
    mkdir -p "$(dirname "$SETTINGS")"
    echo '{}' > "$SETTINGS"
fi

python3 - <<PYEOF
import json, os, sys

settings_path = "$SETTINGS"
script_path = "$DEST_SCRIPT"

with open(settings_path, "r") as f:
    cfg = json.load(f)

hooks = cfg.setdefault("hooks", {})

# Only add if not already registered (idempotent)
def already_registered(hook_list, script):
    return any(
        script in str(item.get("command", ""))
        for h in hook_list for item in h.get("hooks", [])
    )

if not already_registered(hooks.get("UserPromptSubmit", []), script_path):
    hooks.setdefault("UserPromptSubmit", []).append({
        "hooks": [{"type": "command", "command": f"python3 {script_path} prompt"}]
    })

if not already_registered(hooks.get("PostToolUse", []), script_path):
    hooks.setdefault("PostToolUse", []).append({
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [{"type": "command", "command": f"python3 {script_path} track"}]
    })

if not already_registered(hooks.get("SessionEnd", []), script_path):
    hooks.setdefault("SessionEnd", []).append({
        "hooks": [{"type": "command", "command": f"python3 {script_path} learn"}]
    })

with open(settings_path, "w") as f:
    json.dump(cfg, f, indent=2)

print(f"Hooks registered in {settings_path}")
PYEOF

echo "context-bench installed!"
echo "  Script: $DEST_SCRIPT"
echo "  Data:   $DEST_DIR"
echo "  Hooks:  $SETTINGS"
```

- [ ] **Step 2: Write uninstall.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail

DEST_DIR="$HOME/.context-bench"
SETTINGS="$HOME/.claude/settings.json"

echo "Uninstalling context-bench..."

if [ -f "$SETTINGS" ]; then
    python3 - <<PYEOF
import json, os

settings_path = "$SETTINGS"
script_path = "$DEST_DIR/context_bench.py"

with open(settings_path, "r") as f:
    cfg = json.load(f)

hooks = cfg.get("hooks", {})

def remove_cb_hooks(hook_list):
    return [h for h in hook_list if not any(
        script_path in str(item.get("command", ""))
        for item in h.get("hooks", [])
    )]

for event in ["UserPromptSubmit", "PostToolUse", "SessionEnd"]:
    if event in hooks:
        hooks[event] = remove_cb_hooks(hooks[event])
        if not hooks[event]:
            del hooks[event]

with open(settings_path, "w") as f:
    json.dump(cfg, f, indent=2)

print(f"Hooks removed from {settings_path}")
PYEOF
fi

rm -rf "$DEST_DIR"
echo "context-bench uninstalled."
```

- [ ] **Step 3: Verify syntax**

```bash
bash -n install.sh && echo "install.sh OK"
bash -n uninstall.sh && echo "uninstall.sh OK"
chmod +x install.sh uninstall.sh
```

Expected: both print `OK`

- [ ] **Step 4: Run full test suite**

```bash
pytest tests/test_context_bench.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add install.sh uninstall.sh
git commit -m "feat: idempotent install.sh and uninstall.sh for settings.json"
```

---

### Task 11: Examples + CI

**Files:**
- Modify: `examples/python-project.json`, `examples/node-project.json`, `examples/rust-project.json`
- Create: `.github/workflows/tests.yml`
- Modify: `CONTRIBUTING.md`

- [ ] **Step 1: Write example files**

`examples/python-project.json`:
```json
{
  "version": 1,
  "projects": [
    {
      "id": "api",
      "keywords": ["api", "endpoint", "route", "fastapi", "flask"],
      "root": "/home/user/myproject",
      "paths": ["src/api/", "config/api.yaml"],
      "confidence": 0.87,
      "uses": 14,
      "last_used": "2026-04-20",
      "created": "2026-04-01"
    }
  ],
  "settings": {
    "max_context_chars": 8000,
    "min_confidence_threshold": 0.3,
    "match_threshold": 0.5,
    "decay_days": 30
  }
}
```

`examples/node-project.json`:
```json
{
  "version": 1,
  "projects": [
    {
      "id": "frontend",
      "keywords": ["react", "component", "tsx", "hook", "state"],
      "root": "/home/user/webapp",
      "paths": ["src/components/", "src/hooks/"],
      "confidence": 0.9,
      "uses": 22,
      "last_used": "2026-04-20",
      "created": "2026-03-15"
    }
  ],
  "settings": {
    "max_context_chars": 8000,
    "min_confidence_threshold": 0.3,
    "match_threshold": 0.5,
    "decay_days": 30
  }
}
```

`examples/rust-project.json`:
```json
{
  "version": 1,
  "projects": [
    {
      "id": "parser",
      "keywords": ["parser", "token", "ast", "lexer", "parse"],
      "root": "/home/user/rust-parser",
      "paths": ["src/"],
      "confidence": 0.75,
      "uses": 5,
      "last_used": "2026-04-18",
      "created": "2026-04-10"
    }
  ],
  "settings": {
    "max_context_chars": 8000,
    "min_confidence_threshold": 0.3,
    "match_threshold": 0.5,
    "decay_days": 30
  }
}
```

- [ ] **Step 2: Write .github/workflows/tests.yml**

```yaml
name: Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]
        python-version: ["3.9", "3.10", "3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install pytest
        run: pip install pytest

      - name: Run tests
        run: pytest tests/ -v
```

- [ ] **Step 3: Write CONTRIBUTING.md**

```markdown
# Contributing to context-bench

## Setup

```bash
git clone https://github.com/nessos666/context-bench
cd context-bench
pip install pytest
pytest tests/ -v
```

## Architecture

`context_bench.py` is one file. Three modes:
- `prompt` — called by UserPromptSubmit hook
- `track` — called by PostToolUse hook (Write/Edit/MultiEdit)
- `learn` — called by SessionEnd hook

State lives in `~/.context-bench/projects.json`.

## Making changes

1. Write a failing test first (TDD)
2. Implement the minimal fix
3. All tests must pass: `pytest tests/ -v`

## Commit style

```
feat: add new feature
fix: fix a bug
test: add or fix tests
docs: documentation only
```
```

- [ ] **Step 4: Final full test run**

```bash
pytest tests/test_context_bench.py -v --tb=short
```

Expected: ALL PASS, 0 failures

- [ ] **Step 5: Final commit**

```bash
git add examples/ .github/ CONTRIBUTING.md
git commit -m "feat: examples, CI, contributing guide — v1.0 complete"
```

---

## Summary

| Task | Was es baut | Kritische Fixes (Codex) |
|------|-------------|------------------------|
| 1 | Scaffold | — |
| 2 | Datenmodell + DB | Prompt in Session persistiert; `os.replace()` für atomic write |
| 3 | Matcher | — |
| 4 | Loader | — |
| 5 | Bootstrap | 200ms Timeout implementiert |
| 6 | UserPromptSubmit | cwd-Filter verhindert Kontext aus falschem Projekt |
| 7 | PostToolUse | — |
| 8 | SessionEnd | Decay VOR Pruning; `injected_paths` aus Session statt Neuberechnung |
| 9 | New Topic Detection | Prompt aus Session gelesen (nicht SessionEnd-stdin) |
| 10 | install.sh / uninstall.sh | Idempotent (kein Doppel-Eintrag) |
| 11 | Examples + CI | — |
