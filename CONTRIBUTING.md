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
