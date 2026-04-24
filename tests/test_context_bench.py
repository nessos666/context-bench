import json
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


def test_add_session_change_preserves_cwd(tmp_path):
    session_dir = str(tmp_path / "sessions")
    save_session(
        "s6",
        "api",
        [],
        "fix route",
        ["/proj/src/api/"],
        session_dir=session_dir,
        cwd="/proj",
    )
    add_session_change("s6", "/proj/src/api.py", session_dir=session_dir)
    s = load_session("s6", session_dir=session_dir)
    assert s["cwd"] == "/proj"
    assert "/proj/src/api.py" in s["changed_files"]


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


# ── Task 4: Loader ────────────────────────────────────────────────────────────
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
    assert "image.png" not in ctx or "PNG" not in ctx


def test_load_rejects_path_traversal(tmp_path):
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("TOP SECRET")
    topic = Topic(id="x", keywords=[], root=str(tmp_path), paths=["../secret.txt"])
    ctx = load_context(topic, max_chars=8000)
    assert "TOP SECRET" not in ctx


# ── Task 5: Bootstrap ─────────────────────────────────────────────────────────
import time
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
    for i in range(200):
        (tmp_path / f"file_{i}.py").write_text("x = 1")
    start = time.monotonic()
    bootstrap(str(tmp_path), timeout_ms=200)
    elapsed_ms = (time.monotonic() - start) * 1000
    assert elapsed_ms < 400


# ── Task 6: cmd_prompt ────────────────────────────────────────────────────────
import io
from context_bench import cmd_prompt


def _make_db(tmp_path, root=None) -> Database:
    r = root or str(tmp_path)
    (tmp_path / "routes.py").write_text("def get_route(): pass\n")
    return Database(
        projects=[
            Topic(
                id="api",
                keywords=["api", "route", "endpoint"],
                root=r,
                paths=["routes.py"],
                confidence=0.8,
            )
        ]
    )


def test_prompt_injects_context_on_match(tmp_path, monkeypatch, capsys):
    db_path = str(tmp_path / "projects.json")
    session_dir = str(tmp_path / "sessions")
    save_db(_make_db(tmp_path), db_path=db_path)

    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"prompt": "fix the api route", "session_id": "p-s1"})),
    )
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

    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps({"prompt": "talk about gardening", "session_id": "p-s2"})
        ),
    )
    with pytest.raises(SystemExit):
        cmd_prompt(db_path=db_path, session_dir=session_dir, cwd=str(tmp_path))

    out = capsys.readouterr().out
    assert json.loads(out) == {}


def test_prompt_persists_prompt_in_session(tmp_path, monkeypatch, capsys):
    db_path = str(tmp_path / "projects.json")
    session_dir = str(tmp_path / "sessions")
    save_db(_make_db(tmp_path), db_path=db_path)

    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"prompt": "fix the api route", "session_id": "p-s3"})),
    )
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
    db = Database(
        projects=[
            Topic(id="api", keywords=["api", "route"], root=other_root, paths=["src/"])
        ]
    )
    save_db(db, db_path=db_path)

    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"prompt": "fix the api route", "session_id": "p-s4"})),
    )
    with pytest.raises(SystemExit):
        cmd_prompt(db_path=db_path, session_dir=session_dir, cwd=str(tmp_path))

    out = capsys.readouterr().out
    assert json.loads(out) == {}


def test_prompt_bootstraps_when_no_db(tmp_path, monkeypatch, capsys):
    db_path = str(tmp_path / "projects.json")
    session_dir = str(tmp_path / "sessions")

    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"prompt": "hello world", "session_id": "boot-s1"})),
    )
    with pytest.raises(SystemExit):
        cmd_prompt(db_path=db_path, session_dir=session_dir, cwd=str(tmp_path))

    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed == {} or "hookSpecificOutput" in parsed


# ── Task 7: cmd_track ─────────────────────────────────────────────────────────
from context_bench import cmd_track


def test_track_records_changed_file(tmp_path, monkeypatch):
    session_dir = str(tmp_path / "sessions")
    save_session(
        "t-s1", "api", [], "fix api", ["/proj/src/api/"], session_dir=session_dir
    )

    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {
                    "session_id": "t-s1",
                    "tool_input": {"file_path": "/proj/src/api/routes.py"},
                }
            )
        ),
    )
    with pytest.raises(SystemExit):
        cmd_track(session_dir=session_dir)

    s = load_session("t-s1", session_dir=session_dir)
    assert "/proj/src/api/routes.py" in s["changed_files"]


def test_track_no_crash_when_session_missing(tmp_path, monkeypatch):
    session_dir = str(tmp_path / "sessions")
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {
                    "session_id": "no-session",
                    "tool_input": {"file_path": "/tmp/x.py"},
                }
            )
        ),
    )
    with pytest.raises(SystemExit):
        cmd_track(session_dir=session_dir)


def test_track_deduplicates_files(tmp_path, monkeypatch):
    session_dir = str(tmp_path / "sessions")
    save_session("t-s2", None, ["/tmp/x.py"], "", [], session_dir=session_dir)

    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {
                    "session_id": "t-s2",
                    "tool_input": {"file_path": "/tmp/x.py"},
                }
            )
        ),
    )
    with pytest.raises(SystemExit):
        cmd_track(session_dir=session_dir)

    s = load_session("t-s2", session_dir=session_dir)
    assert s["changed_files"].count("/tmp/x.py") == 1


def test_track_normalizes_relative_paths(tmp_path, monkeypatch):
    session_dir = str(tmp_path / "sessions")
    save_session("t-s3", "api", [], "fix api", [], session_dir=session_dir)

    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {
                    "session_id": "t-s3",
                    "tool_input": {"file_path": "src/api/routes.py"},  # relative path
                }
            )
        ),
    )
    with pytest.raises(SystemExit):
        cmd_track(session_dir=session_dir)

    s = load_session("t-s3", session_dir=session_dir)
    # must be stored as absolute path
    assert s["changed_files"][0].startswith("/")


# ── Task 8: cmd_learn + apply_decay ──────────────────────────────────────────
from context_bench import cmd_learn, apply_decay
from datetime import date, timedelta


def test_learn_increases_confidence_when_files_changed(tmp_path, monkeypatch):
    db_path = str(tmp_path / "projects.json")
    session_dir = str(tmp_path / "sessions")
    save_db(
        Database(
            projects=[
                Topic(
                    id="api",
                    keywords=["api"],
                    root="/proj",
                    paths=["src/api/"],
                    confidence=0.5,
                )
            ]
        ),
        db_path=db_path,
    )
    save_session(
        "l-s1",
        "api",
        ["/proj/src/api/routes.py"],
        "fix api",
        ["/proj/src/api/"],
        session_dir=session_dir,
    )

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "l-s1"})))
    with pytest.raises(SystemExit):
        cmd_learn(db_path=db_path, session_dir=session_dir)

    loaded = load_db(db_path=db_path)
    assert loaded.projects[0].confidence == pytest.approx(0.65, abs=0.01)


def test_learn_path_boundary_no_false_match(tmp_path, monkeypatch):
    """Ensure /proj/src/api2/file.py does NOT match injected path /proj/src/api/."""
    db_path = str(tmp_path / "projects.json")
    session_dir = str(tmp_path / "sessions")
    save_db(
        Database(
            projects=[
                Topic(
                    id="api",
                    keywords=["api"],
                    root="/proj",
                    paths=["src/api/"],
                    confidence=0.5,
                )
            ]
        ),
        db_path=db_path,
    )
    save_session(
        "l-boundary",
        "api",
        ["/proj/src/api2/routes.py"],
        "fix api",
        ["/proj/src/api/"],
        session_dir=session_dir,
    )

    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps({"session_id": "l-boundary"}))
    )
    with pytest.raises(SystemExit):
        cmd_learn(db_path=db_path, session_dir=session_dir)

    loaded = load_db(db_path=db_path)
    # Should decrease (no real overlap), not increase
    assert loaded.projects[0].confidence == pytest.approx(0.45, abs=0.01)


def test_learn_decreases_confidence_when_files_not_changed(tmp_path, monkeypatch):
    db_path = str(tmp_path / "projects.json")
    session_dir = str(tmp_path / "sessions")
    save_db(
        Database(
            projects=[
                Topic(
                    id="api",
                    keywords=["api"],
                    root="/proj",
                    paths=["src/api/"],
                    confidence=0.5,
                )
            ]
        ),
        db_path=db_path,
    )
    save_session(
        "l-s2", "api", [], "fix api", ["/proj/src/api/"], session_dir=session_dir
    )

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "l-s2"})))
    with pytest.raises(SystemExit):
        cmd_learn(db_path=db_path, session_dir=session_dir)

    loaded = load_db(db_path=db_path)
    assert loaded.projects[0].confidence == pytest.approx(0.45, abs=0.01)


def test_learn_removes_dead_topics(tmp_path, monkeypatch):
    db_path = str(tmp_path / "projects.json")
    session_dir = str(tmp_path / "sessions")
    save_db(
        Database(
            projects=[
                Topic(
                    id="api",
                    keywords=["api"],
                    root="/proj",
                    paths=["src/"],
                    confidence=0.2,
                )
            ]
        ),
        db_path=db_path,
    )
    save_session("l-s3", "api", [], "fix api", [], session_dir=session_dir)

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "l-s3"})))
    with pytest.raises(SystemExit):
        cmd_learn(db_path=db_path, session_dir=session_dir)

    loaded = load_db(db_path=db_path)
    assert len(loaded.projects) == 0


def test_apply_decay_reduces_old_topics():
    old_date = (date.today() - timedelta(days=40)).isoformat()
    db = Database(
        projects=[
            Topic(
                id="api",
                keywords=[],
                root="/p",
                paths=[],
                confidence=0.8,
                last_used=old_date,
            )
        ],
        settings=Settings(decay_days=30),
    )
    apply_decay(db)
    assert db.projects[0].confidence < 0.8


def test_apply_decay_ignores_recent_topics():
    db = Database(
        projects=[
            Topic(
                id="api",
                keywords=[],
                root="/p",
                paths=[],
                confidence=0.8,
                last_used=date.today().isoformat(),
            )
        ],
        settings=Settings(decay_days=30),
    )
    apply_decay(db)
    assert db.projects[0].confidence == pytest.approx(0.8)


def test_apply_decay_is_idempotent_within_same_day():
    old_date = (date.today() - timedelta(days=40)).isoformat()
    db = Database(
        projects=[
            Topic(
                id="api",
                keywords=[],
                root="/p",
                paths=[],
                confidence=0.8,
                last_used=old_date,
            )
        ],
        settings=Settings(decay_days=30),
    )
    apply_decay(db)
    confidence_after_first = db.projects[0].confidence
    apply_decay(db)  # second call same day — must not reduce further
    assert db.projects[0].confidence == pytest.approx(confidence_after_first)


def test_learn_decay_applied_before_pruning(tmp_path, monkeypatch):
    """Topic at 0.32 that gets 10 days decay should fall below 0.3 and be removed."""
    db_path = str(tmp_path / "projects.json")
    session_dir = str(tmp_path / "sessions")
    old_date = (date.today() - timedelta(days=40)).isoformat()
    save_db(
        Database(
            projects=[
                Topic(
                    id="old",
                    keywords=["old"],
                    root="/p",
                    paths=[],
                    confidence=0.32,
                    last_used=old_date,
                )
            ]
        ),
        db_path=db_path,
    )
    save_session("l-s4", None, [], "", [], session_dir=session_dir)

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "l-s4"})))
    with pytest.raises(SystemExit):
        cmd_learn(db_path=db_path, session_dir=session_dir)

    loaded = load_db(db_path=db_path)
    assert len(loaded.projects) == 0


# ── Task 9: New topic detection ───────────────────────────────────────────────
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
    save_session(
        "n-s1",
        None,
        ["/proj/src/api/routes.py"],
        "refactor api endpoint",
        [],
        session_dir=session_dir,
    )

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


def test_new_topic_uses_session_cwd_as_root(tmp_path, monkeypatch):
    """Learned topic root must equal session cwd, not commonpath of changed files."""
    db_path = str(tmp_path / "projects.json")
    session_dir = str(tmp_path / "sessions")
    save_db(Database(projects=[]), db_path=db_path)
    # Changed files are deep inside the repo — root should still be cwd
    cwd = str(tmp_path)
    changed = [str(tmp_path / "src" / "api" / "routes.py")]
    save_session(
        "n-s3", None, changed, "refactor api", [], session_dir=session_dir, cwd=cwd
    )

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "n-s3"})))
    with pytest.raises(SystemExit):
        cmd_learn(db_path=db_path, session_dir=session_dir)

    loaded = load_db(db_path=db_path)
    assert len(loaded.projects) >= 1
    assert loaded.projects[0].root == cwd


# ── Task 10: DISABLED flag ────────────────────────────────────────────────────
from pathlib import Path
from context_bench import main


def _setup_disabled(tmp_path):
    """Create the DISABLED flag at the location main() checks."""
    cb_dir = tmp_path / ".context-bench"
    cb_dir.mkdir(parents=True, exist_ok=True)
    (cb_dir / "DISABLED").touch()
    return cb_dir


def test_prompt_exits_zero_when_disabled(tmp_path, monkeypatch, capsys):
    """prompt gibt {} aus und laeuft durch wenn DISABLED existiert."""
    _setup_disabled(tmp_path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"prompt": "fix the api", "session_id": "d-s1"})),
    )
    monkeypatch.setattr("sys.argv", ["context_bench.py", "prompt"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0


def test_learn_cleans_up_session_when_disabled(tmp_path, monkeypatch):
    """learn raeumt Session-Datei auf, auch wenn DISABLED aktiv ist."""
    cb_dir = _setup_disabled(tmp_path)
    session_dir = str(cb_dir / "sessions")
    # Session vorab anlegen
    save_session("d-s2", "api", [], "fix", [], session_dir=session_dir)
    assert load_session("d-s2", session_dir=session_dir) is not None

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    # cleanup_session has _DEFAULT_SESSION_DIR baked in as a default arg — patch
    # the function so it uses our session_dir instead.
    import context_bench as _cb

    _orig_cleanup = _cb.cleanup_session
    monkeypatch.setattr(
        _cb,
        "cleanup_session",
        lambda sid, sd=session_dir: _orig_cleanup(sid, sd),
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "d-s2"})))
    monkeypatch.setattr("sys.argv", ["context_bench.py", "learn"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    # Session muss weg sein
    assert load_session("d-s2", session_dir=session_dir) is None


def test_track_exits_zero_when_disabled(tmp_path, monkeypatch):
    """track macht sofort exit 0 wenn DISABLED existiert."""
    _setup_disabled(tmp_path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps({"session_id": "d-s3", "tool_input": {"file_path": "/tmp/x.py"}})
        ),
    )
    monkeypatch.setattr("sys.argv", ["context_bench.py", "track"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
