#!/usr/bin/env python3
"""context-bench — self-learning Claude Code hook for automatic context injection."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
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
    last_decay_date: Optional[str] = None  # NEW: track when decay was last applied


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
        valid_keys = set(asdict(Settings()).keys())
        settings = Settings(
            **{k: v for k, v in settings_raw.items() if k in valid_keys}
        )
        return Database(
            version=raw.get("version", 1), projects=projects, settings=settings
        )
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
            f.write(f"{datetime.now().isoformat()} {msg}\n")
    except OSError:
        pass


# ── Session helpers ───────────────────────────────────────────────────────────
def _session_path(session_id: str, session_dir: str = _DEFAULT_SESSION_DIR) -> str:
    os.makedirs(session_dir, exist_ok=True)
    safe = session_id.replace("/", "_")[:64]
    return os.path.join(session_dir, f"{safe}.json")


def load_session(
    session_id: str, session_dir: str = _DEFAULT_SESSION_DIR
) -> Optional[dict]:
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
    cwd: str = "",
) -> None:
    """Save session state. prompt, injected_paths and cwd are needed by cmd_learn."""
    path = _session_path(session_id, session_dir)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=session_dir, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "session_id": session_id,
                    "matched_topic": matched_topic,
                    "changed_files": changed_files,
                    "prompt": prompt,
                    "injected_paths": injected_paths,
                    "cwd": cwd,
                },
                f,
            )
        os.replace(tmp_path, path)
    except Exception as e:
        _log_error(f"save_session failed: {e}")
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def add_session_change(
    session_id: str, file_path: str, session_dir: str = _DEFAULT_SESSION_DIR
) -> None:
    session = load_session(session_id, session_dir) or {
        "session_id": session_id,
        "matched_topic": None,
        "changed_files": [],
        "prompt": "",
        "injected_paths": [],
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


# ── Matcher ───────────────────────────────────────────────────────────────────
def compute_match_score(prompt: str, topic: Topic) -> float:
    """Returns fraction of topic keywords found in prompt (0.0–1.0)."""
    if not topic.keywords:
        return 0.0
    prompt_lower = prompt.lower()
    matches = sum(1 for kw in topic.keywords if kw.lower() in prompt_lower)
    return matches / len(topic.keywords)


# ── Loader ───────────────────────────────────────────────────────────────────
_BINARY_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".exe",
    ".so",
    ".dylib",
    ".pyc",
    ".db",
    ".sqlite",
    ".bin",
}


def load_context(topic: Topic, max_chars: int) -> str:
    """Read topic files and build context string. Truncates at max_chars."""
    header = f"## Projekt-Kontext (auto-geladen)\n\nTopic: {topic.id}\nDateien:\n\n"
    parts: list[str] = []
    remaining = max_chars - len(header)
    real_root = os.path.realpath(topic.root)

    for rel_path in topic.paths:
        abs_path = os.path.join(topic.root, rel_path)
        # Security: reject paths that escape topic.root
        if (
            not os.path.realpath(abs_path).startswith(real_root + os.sep)
            and os.path.realpath(abs_path) != real_root
        ):
            continue
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
                os.path.join(path, e)
                for e in os.listdir(path)
                if os.path.isfile(os.path.join(path, e))
            )
        except OSError:
            return []
    return []


_MAX_READ_BYTES = 64 * 1024  # 64 KB cap per file before context truncation


def _read_file_safe(path: str) -> Optional[str]:
    if Path(path).suffix.lower() in _BINARY_EXTS:
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(_MAX_READ_BYTES)
    except OSError:
        return None


# ── Bootstrap ─────────────────────────────────────────────────────────────────
import time as _time

_FRAMEWORK_MARKERS: list[tuple[str, str, list[str], list[str]]] = [
    (
        "pyproject.toml",
        "python",
        ["python", "pip", "pytest", "uv", "poetry"],
        ["src/", "tests/"],
    ),
    (
        "requirements.txt",
        "python",
        ["python", "pip", "requirements"],
        ["src/", "tests/"],
    ),
    ("setup.py", "python", ["python", "setup", "package"], ["src/", "tests/"]),
    (
        "package.json",
        "node",
        ["node", "npm", "javascript", "typescript"],
        ["src/", "lib/"],
    ),
    ("go.mod", "go", ["go", "golang", "module"], ["cmd/", "pkg/"]),
    ("Cargo.toml", "rust", ["rust", "cargo", "crate"], ["src/"]),
    ("pom.xml", "java", ["java", "maven", "spring"], ["src/main/", "src/test/"]),
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
                existing = [
                    d
                    for d in scan_dirs
                    if os.path.isdir(os.path.join(cwd, d))
                    and _time.monotonic() < deadline
                ]
                paths = existing if existing else [marker]
                projects.append(
                    Topic(
                        id=topic_id,
                        keywords=keywords,
                        root=cwd,
                        paths=paths,
                        confidence=0.5,
                        uses=0,
                        last_used=None,
                        created=today,
                    )
                )
                break
    except Exception as e:
        _log_error(f"bootstrap error: {e}")

    return Database(projects=projects)


# ── Hook entry points (implemented in later tasks) ───────────────────────────
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
            if not (cwd == topic.root or cwd.startswith(topic.root + os.sep)):
                continue
            score = compute_match_score(prompt, topic)
            if score > best_score:
                best_score, best_topic = score, topic

        if best_topic and best_score >= db.settings.match_threshold:
            context = load_context(best_topic, db.settings.max_context_chars)
            injected = [os.path.join(best_topic.root, p) for p in best_topic.paths]
            save_session(
                session_id, best_topic.id, [], prompt, injected, session_dir, cwd=cwd
            )

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
            save_session(session_id, None, [], prompt, [], session_dir, cwd=cwd)
            output = {}

        print(json.dumps(output))
    except Exception as e:
        _log_error(f"cmd_prompt error: {e}")
        print("{}")
    sys.exit(0)


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
    if changed_file and not os.path.isabs(changed_file):
        changed_file = os.path.abspath(changed_file)

    try:
        if session_id and changed_file:
            add_session_change(session_id, changed_file, session_dir)
    except Exception as e:
        _log_error(f"cmd_track error: {e}")

    sys.exit(0)


_STOPWORDS = {
    "the",
    "a",
    "an",
    "is",
    "it",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "and",
    "or",
    "but",
    "with",
    "from",
    "by",
    "i",
    "my",
    "this",
    "that",
    "how",
    "what",
    "why",
    "fix",
    "add",
    "get",
    "make",
    "run",
    "do",
    "can",
    "will",
    "please",
    "want",
    "need",
    "hello",
    "world",
}


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


def apply_decay(db: Database) -> None:
    """Reduce confidence for topics not used within decay_days. Idempotent per day."""
    today = date.today()
    today_str = today.isoformat()
    for topic in db.projects:
        # Skip if decay already applied today
        if topic.last_decay_date == today_str:
            continue
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
        topic.last_decay_date = today_str


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

        # New topic detection: only when no match but files were changed
        elif changed_files:
            prompt_text = session.get("prompt", "")
            session_cwd = session.get("cwd", "")
            keywords = _extract_keywords(prompt_text, changed_files)
            if keywords:
                # Use session cwd as root (matches cmd_prompt filter),
                # fall back to commonpath only if cwd unknown
                if session_cwd:
                    root = session_cwd
                else:
                    try:
                        root = (
                            os.path.commonpath(changed_files)
                            if len(changed_files) > 1
                            else os.path.dirname(changed_files[0])
                        )
                    except ValueError:
                        root = os.path.dirname(changed_files[0])
                rel_paths = list(
                    dict.fromkeys(
                        os.path.relpath(f, root)
                        for f in changed_files
                        if f.startswith(root)
                    )
                )[:5]
                if not rel_paths:
                    rel_paths = [os.path.basename(f) for f in changed_files[:5]]
                new_topic = Topic(
                    id=keywords[0],
                    keywords=keywords,
                    root=root,
                    paths=rel_paths,
                    confidence=0.5,
                    uses=1,
                    last_used=date.today().isoformat(),
                    created=date.today().isoformat(),
                )
                db.projects.append(new_topic)

        # Decay first, then prune
        apply_decay(db)
        db.projects = [
            t
            for t in db.projects
            if t.confidence >= db.settings.min_confidence_threshold
        ]

        save_db(db, db_path)
        cleanup_session(session_id, session_dir)
    except Exception as e:
        _log_error(f"cmd_learn error: {e}")

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
