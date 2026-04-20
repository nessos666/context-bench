import subprocess
import sys
import os

import pytest


ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from context_bench import (  # noqa: E402
    Topic,
    Settings,
    Database,
    load_db,
    save_db,
    load_session,
    save_session,
    add_session_change,
    cleanup_session,
)


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


# ── Data model + DB helper tests ─────────────────────────────────────────────


def test_default_settings():
    s = Settings()
    assert s.max_context_chars == 8000
    assert s.min_confidence_threshold == 0.3
    assert s.match_threshold == 0.5
    assert s.decay_days == 30


def test_topic_creation():
    t = Topic(
        id="api", keywords=["api", "route"], root="/home/user/proj", paths=["src/api/"]
    )
    assert t.confidence == 0.5
    assert t.uses == 0


def test_save_and_load_db(tmp_path):
    db_path = str(tmp_path / "projects.json")
    db = Database(
        projects=[Topic(id="api", keywords=["api"], root="/proj", paths=["src/"])]
    )
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


def test_save_session_persists_prompt_and_injected_paths(tmp_path):
    session_dir = str(tmp_path / "sessions")
    save_session(
        "s5", "api", [], "fix the route", ["/proj/src/api/"], session_dir=session_dir
    )
    s = load_session("s5", session_dir=session_dir)
    assert s["prompt"] == "fix the route"
    assert "/proj/src/api/" in s["injected_paths"]


# ── Task 3: Matcher ───────────────────────────────────────────────────────────
from context_bench import compute_match_score


def test_partial_keyword_match():
    topic = Topic(id="api", keywords=["api", "route", "fastapi"], root="/p", paths=[])
    score = compute_match_score("fix the api route", topic)
    assert score == pytest.approx(2 / 3, abs=0.01)


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
    topic = Topic(id="api", keywords=["api", "route"], root="/p", paths=[])
    score = compute_match_score("fix the api", topic)
    assert score == pytest.approx(0.5)
    assert score >= 0.5
