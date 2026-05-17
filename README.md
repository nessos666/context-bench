<p align="center">
  <h1 align="center">context-bench</h1>
  <p align="center">
    <strong>Your AI editor knows what you're working on — automatically.</strong>
  </p>
  <p align="center">
    <em>A self-learning Claude Code plugin that detects your current project from your first message and injects the right file context — without any manual configuration.</em>
  </p>
  <p align="center">
    <a href="#how-it-works">How It Works</a> · <a href="#installation">Installation</a> · <a href="#learning">How It Learns</a> · <a href="#architecture">Architecture</a> · <a href="#toggle">Toggle</a>
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.9+-blue?logo=python&logoColor=white" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License">
  <img src="https://img.shields.io/badge/dependencies-zero-success" alt="Zero deps">
  <img src="https://img.shields.io/badge/hooks-3_registered-blueviolet" alt="3 hooks">
  <img src="https://img.shields.io/badge/bootstrap-200ms-brightgreen" alt="200ms bootstrap">
  <img src="https://img.shields.io/github/stars/nessos666/context-bench?style=social" alt="Stars">
</p>

---

## The Problem

Every Claude Code session starts the same way: you tell it what project you're working on, what files matter, what the architecture looks like. Then the next session, you do it again.

**That's wasted time and context.**

context-bench solves this by **learning from your sessions**. After a few interactions, it knows:

- What keywords belong to which project
- Which files you typically reference
- Which framework markers (pyproject.toml, package.json, Cargo.toml) identify your stack
- When a project is no longer active (confidence decay)

It then **injects relevant file paths as invisible context** before you even finish typing your first message.

---

## How It Works

```
┌──────────────────────────────────────────────────────────┐
│                  Claude Code Session                      │
│                                                           │
│  User: "fix the parser in my strategy builder"            │
│         │                                                 │
│         ▼                                                 │
│  [UserPromptSubmit hook fires]                            │
│         │                                                 │
│         ▼                                                 │
│  context-bench:                                           │
│    ├─ Keywords: "parser" + "strategy" + "builder"         │
│    ├─ Match: "nq-strategy-builder" (confidence 0.85)      │
│    └─ Inject: /path/to/parser.py, /path/to/knowledge.py   │
│         │                                                 │
│         ▼                                                 │
│  Claude responds with full project context                │
│                                                           │
│  ... user edits files ...                                 │
│         │                                                 │
│  [PostToolUse hook fires] → tracks changed files          │
│                                                           │
│  ... session ends ...                                     │
│         │                                                 │
│  [SessionEnd hook fires] → updates confidence +0.15       │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

### The three hooks

| Hook | Trigger | What it does | Latency |
|------|---------|--------------|---------|
| `UserPromptSubmit` | User sends a message | Matches keywords → injects relevant file paths as context | < 200ms |
| `PostToolUse` | Tool call completes | Records which files were read/written | < 50ms |
| `SessionEnd` | Session closes | Updates confidence scores, decays old topics, creates new ones | < 100ms |

---

## Installation

### As Claude Code Plugin (recommended)

```bash
claude plugin add nessos666/context-bench
```

That's it. The plugin registers all three hooks automatically.

### Standalone (manual)

```bash
git clone https://github.com/nessos666/context-bench
cd context-bench
./install.sh
```

`install.sh` registers the three hooks in `~/.claude/settings.json` and copies `context_bench.py` to `~/.context-bench/`.

### Local testing

```bash
claude --plugin-dir ./context-bench
```

---

## How It Learns

context-bench uses a **confidence-based learning system** — no ML model, no API calls, just deterministic updates:

### Confidence scoring

| Event | Confidence change | Why |
|-------|-------------------|-----|
| Match found + files changed | **+0.15** | Strong signal — you're working on this project |
| Match found + no files changed | **−0.05** | Weak signal — maybe a false positive |
| No match + files changed | **New topic at 0.5** | Discovered a new project organically |
| Topic idle > 30 days | **−0.01/day** | Gradual decay for inactive projects |
| Topic below **0.3** | **Auto-removed** | Confidence too low to be useful |

### Bootstrap (first run)

On first run (no `projects.json` yet), context-bench scans the current directory for framework markers:

| Marker | Detected as |
|--------|-------------|
| `pyproject.toml` / `requirements.txt` / `setup.py` | Python project |
| `package.json` | Node.js project |
| `go.mod` | Go project |
| `Cargo.toml` | Rust project |
| `pom.xml` | Java project |

Bootstrap completes within **200ms** to avoid blocking hooks.

### Data model

```json
{
  "version": 1,
  "projects": [
    {
      "id": "nq-strategy-builder",
      "keywords": ["strategy", "builder", "nq", "fvg", "backtest"],
      "root": "/home/user/projects/strategy-builder",
      "paths": ["engine/parser.py", "sb/cli.py"],
      "confidence": 0.85,
      "uses": 47,
      "last_used": "2026-05-17T10:30:00"
    }
  ]
}
```

---

## Architecture

```
context_bench.py (single file, zero dependencies)
├── cmd_prompt()  → UserPromptSubmit  → match topic, inject context
├── cmd_track()   → PostToolUse       → record changed files
└── cmd_learn()   → SessionEnd        → update confidence, create topics, decay
```

**Single file.** **Zero dependencies.** **Zero API calls.**

---

## Toggle (disable/enable)

Temporarily disable context-bench without uninstalling:

```bash
touch ~/.context-bench/DISABLED   # disable
rm ~/.context-bench/DISABLED      # enable again
```

When disabled, all hooks exit immediately (no context injected, no tracking). The `learn` hook still cleans up session files to prevent leaks.

### Claude Code skill shortcuts

`~/.claude/commands/ctx-bench-aus.md`:
```markdown
Run: mkdir -p ~/.context-bench && touch ~/.context-bench/DISABLED
Output: "context-bench deactivated"
```

`~/.claude/commands/ctx-bench-an.md`:
```markdown
Run: rm -f ~/.context-bench/DISABLED
Output: "context-bench active"
```

---

## Uninstall

Plugin mode:
```bash
claude plugin remove context-bench
```

Standalone:
```bash
./uninstall.sh
```

---

## Requirements

- **Python 3.9+** (stdlib only, no dependencies)
- **Claude Code** with hooks support

---

## Project Structure

```
├── context_bench.py              # Single-file plugin (hooks + learning)
├── hooks/hooks.json              # Hook registration
├── install.sh                    # Hook installer
├── uninstall.sh                  # Hook remover
├── .github/workflows/tests.yml   # CI pipeline
├── tests/test_context_bench.py   # Test suite
└── examples/
    ├── node-project.json         # Example project manifest
    ├── python-project.json
    └── rust-project.json
```

---

## Testing

```bash
pytest tests/ -v
```

```bash
# Manual test
python context_bench.py prompt "fix the parser in my strategy builder"
```

---

## License

MIT

<p align="center">
  <small>Built because repeating your project context every session is a waste of tokens — and brainpower.<br>
  <strong>github.com/nessos666</strong></small>
</p>
