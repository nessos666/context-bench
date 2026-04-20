# context-bench

Self-learning Claude Code hook for automatic context injection.

context-bench runs as a Claude Code hook and automatically injects relevant project context into sessions based on learned usage patterns.

## How it works

Three hook modes:

- `prompt` — called on `UserPromptSubmit`, injects relevant context into the session
- `track` — called on `PostToolUse`, records which files/tools were used
- `learn` — called on `SessionEnd`, updates the context model from session data

## Installation

```bash
git clone https://github.com/nessos666/context-bench.git
cd context-bench
python3 context_bench.py --help
```

## Usage

Configure in `.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [{"command": "python3 /path/to/context_bench.py prompt"}],
    "PostToolUse": [{"command": "python3 /path/to/context_bench.py track"}],
    "SessionEnd": [{"command": "python3 /path/to/context_bench.py learn"}]
  }
}
```

## License

MIT
