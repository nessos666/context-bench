#!/usr/bin/env bash
set -euo pipefail

DEST_DIR="$HOME/.context-bench"
SETTINGS="$HOME/.claude/settings.json"

echo "Uninstalling context-bench..."

if [ -f "$SETTINGS" ]; then
    python3 - <<PYEOF
import json, os

settings_path = "$SETTINGS"
script_path = "$DEST_DIR/context_bench.py"

with open(settings_path, "r") as f:
    cfg = json.load(f)

hooks = cfg.get("hooks", {})

def remove_cb_hooks(hook_list):
    return [h for h in hook_list if not any(
        script_path in str(item.get("command", ""))
        for item in h.get("hooks", [])
    )]

for event in ["UserPromptSubmit", "PostToolUse", "SessionEnd"]:
    if event in hooks:
        hooks[event] = remove_cb_hooks(hooks[event])
        if not hooks[event]:
            del hooks[event]

with open(settings_path, "w") as f:
    json.dump(cfg, f, indent=2)

print(f"Hooks removed from {settings_path}")
PYEOF
fi

rm -rf "$DEST_DIR"
echo "context-bench uninstalled."
