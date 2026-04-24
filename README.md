# context-bench

**Your AI editor knows what you're working on — automatically.**

A self-learning Claude Code plugin that detects your current project from your first message and injects the right file context — without any manual configuration.

## How it works

```
1. You type your first message
2. context-bench reads the prompt (UserPromptSubmit hook)
3. Keywords are matched against your project topics
4. Relevant files are injected as invisible context
5. Claude responds with full project context already loaded
6. File changes are tracked (PostToolUse hook)
7. Confidence scores update at session end (SessionEnd hook)
```

## Installation

### As Claude Code Plugin (recommended)

```bash
claude plugin add nessos666/context-bench
```

That's it. The plugin registers all hooks automatically.

### Standalone (manual)

```bash
git clone https://github.com/nessos666/context-bench
cd context-bench
./install.sh
```

`install.sh` registers three hooks in `~/.claude/settings.json` and copies `context_bench.py` to `~/.context-bench/`.

### Local testing

```bash
claude --plugin-dir ./context-bench
```

## Toggle (disable/enable)

To temporarily disable context-bench without uninstalling:

```bash
touch ~/.context-bench/DISABLED   # disable
rm ~/.context-bench/DISABLED      # enable again
```

When disabled, all hooks exit immediately (no context injected, no tracking). The `learn` hook still cleans up session files to prevent leaks.

If you use Claude Code skills, you can add shortcuts:

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

## Uninstall

Plugin mode:
```bash
claude plugin remove context-bench
```

Standalone:
```bash
./uninstall.sh
```

## How it learns

Each project topic has a `confidence` score (0–1):

- Match found + files changed → `+0.15`
- Match found + no files changed → `−0.05`
- No match + files changed → new topic created with `0.5`
- Topic idle > 30 days → gradual decay (`−0.01/day`)
- Topic below `0.3` → removed automatically

Topics are stored in `~/.context-bench/projects.json`.

## Bootstrap

On first run (no `projects.json` yet), context-bench scans the current directory for framework markers:

| Marker | Detected as |
|--------|-------------|
| `pyproject.toml` / `requirements.txt` / `setup.py` | Python project |
| `package.json` | Node.js project |
| `go.mod` | Go project |
| `Cargo.toml` | Rust project |
| `pom.xml` | Java project |

The bootstrap completes within 200ms to avoid blocking hooks.

## Architecture

```
context_bench.py (single file, zero dependencies)
├── cmd_prompt()  → UserPromptSubmit  → match topic, inject context
├── cmd_track()   → PostToolUse       → record changed files
└── cmd_learn()   → SessionEnd        → update confidence, create topics, decay
```

Data model:
- **Topic**: id, keywords, root, paths, confidence, uses, last_used
- **Database**: version, projects[], settings
- **Session**: matched_topic, changed_files, prompt, injected_paths, cwd

## Requirements

- Python 3.9+ (stdlib only, no dependencies)
- Claude Code with hooks support

## License

MIT
