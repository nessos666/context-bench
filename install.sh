#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_DIR="$HOME/.context-bench"
DEST_SCRIPT="$DEST_DIR/context_bench.py"
SETTINGS="$HOME/.claude/settings.json"

echo "Installing context-bench..."

mkdir -p "$DEST_DIR"
cp "$SCRIPT_DIR/context_bench.py" "$DEST_SCRIPT"
chmod +x "$DEST_SCRIPT"

if [ ! -f "$SETTINGS" ]; then
    mkdir -p "$(dirname "$SETTINGS")"
    echo '{}' > "$SETTINGS"
fi

python3 - <<PYEOF
import json, os, sys

settings_path = "$SETTINGS"
script_path = "$DEST_SCRIPT"

with open(settings_path, "r") as f:
    cfg = json.load(f)

hooks = cfg.setdefault("hooks", {})

def already_registered(hook_list, script):
    return any(
        script in str(item.get("command", ""))
        for h in hook_list for item in h.get("hooks", [])
    )

if not already_registered(hooks.get("UserPromptSubmit", []), script_path):
    hooks.setdefault("UserPromptSubmit", []).append({
        "hooks": [{"type": "command", "command": f'python3 "{script_path}" prompt', "timeout": 5}]
    })

if not already_registered(hooks.get("PostToolUse", []), script_path):
    hooks.setdefault("PostToolUse", []).append({
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [{"type": "command", "command": f'python3 "{script_path}" track', "timeout": 5}]
    })

if not already_registered(hooks.get("SessionEnd", []), script_path):
    hooks.setdefault("SessionEnd", []).append({
        "hooks": [{"type": "command", "command": f'python3 "{script_path}" learn', "timeout": 10}]
    })

with open(settings_path, "w") as f:
    json.dump(cfg, f, indent=2)

print(f"Hooks registered in {settings_path}")
PYEOF

echo "context-bench installed!"
echo "  Script: $DEST_SCRIPT"
echo "  Data:   $DEST_DIR"
echo "  Hooks:  $SETTINGS"
