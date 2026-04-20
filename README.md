# context-bench

**Your AI editor knows what you're working on — automatically.**

A self-learning Claude Code hook that detects your current project from your first message and injects the right file context — without any manual configuration.

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

```bash
git clone https://github.com/nessos666/context-bench
cd context-bench
./install.sh
```

`install.sh` registers three hooks in `~/.claude/settings.json` and copies `context_bench.py` to `~/.context-bench/`.

## Uninstall

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

## Requirements

- Python 3.9+ (stdlib only, no dependencies)
- Claude Code with hooks support

## License

MIT
