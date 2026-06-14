# I Built a Claude Code Plugin That Remembers Your Project — So You Don't Have To

**Every Claude session starts the same way.** You describe your project. Again. Which files matter. Again. What the architecture looks like. Again.

After 50 sessions, I'd spent more time re-explaining my codebase than actually building things. So I fixed it.

## The Problem

Claude Code is powerful. But it has amnesia. Every new session is a blank slate. You either:

- Paste project context manually (wastes first 5 minutes)
- Write a CLAUDE.md (static, goes stale)
- Use `/init` (still requires you to remember)

None of these **learn**. They don't get better over time. They don't notice when you switch projects mid-session.

## The Solution: context-bench

A single Python file. Zero dependencies. Three hooks. It watches your Claude sessions and learns what matters.

```
You type: "fix the parser in my strategy builder"
         │
         ▼
[UserPromptSubmit hook fires]
         │
context-bench:
  ├─ Keywords: "parser" + "strategy" + "builder"  
  ├─ Match: "nq-strategy-builder" (confidence 0.85)
  └─ Injects: engine/parser.py, engine/knowledge.py
         │
         ▼
Claude responds with full project context — you said nothing
```

It works through three hooks registered in Claude Code:

| Hook | When | What happens |
|------|------|-------------|
| `UserPromptSubmit` | You send a message | Matches keywords → injects relevant file paths |
| `PostToolUse` | Claude reads/writes a file | Records which files were touched |
| `SessionEnd` | Session closes | Updates confidence scores, decays old topics |

## How It Learns (No ML, No API Calls)

After a few sessions, it builds a confidence model:

- You mention "parser" + "strategy" → match found → +0.15 confidence
- You switch to a Node.js project → new topic created at 0.5
- You stop working on a project → confidence decays -0.01/day
- Topic drops below 0.3 → auto-removed

That's it. Deterministic. Transparent. **200ms bootstrap** on first run.

## Why This Matters

**Token efficiency.** Every time you re-explain your project, you're burning tokens. Context window is expensive. context-bench moves project context from *your prompt* to *injected metadata* — invisible to you, free in token terms.

**Zero maintenance.** No config files. No manual topic registration. It learns what your projects are by watching what you work on.

**Actually works offline.** stdlib only. No API. No telemetry. No network.

## Installation

```bash
claude plugin add nessos666/context-bench
```

Done. Three hooks registered. Starts learning immediately.

To disable temporarily:
```bash
touch ~/.context-bench/DISABLED
```

## The Numbers

- **200ms** — bootstrap time (first run)
- **<50ms** — hook latency (subsequent calls)
- **1 file** — `context_bench.py`
- **0 dependencies** — Python stdlib only
- **0 API calls** — completely offline

## What People Miss About AI Tools

The best tools don't ask you for input. They observe. They learn. They fade into the background.

context-bench is 2,131 lines of Python. It's not a product. It's a pattern.

**Your tools should know what you're working on without being told.**

---

*Built by [nessos666](https://github.com/nessos666). MIT License. Works with Claude Code. Star it if you hate repeating yourself.*

---

## PS: For Developers

If you want to write your own Claude Code hooks, the pattern is simple:

1. Register hooks in `~/.claude/settings.json`
2. Each hook receives the full session context as JSON on stdin
3. Return whatever you want injected — or nothing

context-bench is open source. Steal the pattern. Build your own. The hooks API is underused and incredibly powerful.
