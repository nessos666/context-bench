#!/usr/bin/env python3
"""context-bench — self-learning Claude Code hook for automatic context injection."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import date
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
) -> None:
    """Save session state. prompt and injected_paths are needed by cmd_learn."""
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


# ── Hook entry points (implemented in later tasks) ───────────────────────────
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
