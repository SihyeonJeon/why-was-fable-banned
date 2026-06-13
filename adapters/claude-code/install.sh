#!/usr/bin/env bash
# fable-forge — Claude Code installer.
# Wires the forge hooks into user-level ~/.claude/settings.json so EVERY project,
# session, and orchestrated subagent inherits the gate. Idempotent. No deps but
# python3 (already required by the hooks).
#
#   sh install.sh            install / refresh
#   sh install.sh --uninstall   remove forge hooks
set -eu

HOOK_DIR="$(cd "$(dirname "$0")/../hooks" && pwd)"   # shared, runtime-agnostic hooks
SETTINGS="${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"
MODE="install"
[ "${1:-}" = "--uninstall" ] && MODE="uninstall"

mkdir -p "$(dirname "$SETTINGS")"
[ -f "$SETTINGS" ] || echo '{}' > "$SETTINGS"

HOOK_DIR="$HOOK_DIR" SETTINGS="$SETTINGS" MODE="$MODE" python3 - <<'PY'
import json, os, sys

hook_dir = os.environ["HOOK_DIR"]
path = os.environ["SETTINGS"]
mode = os.environ["MODE"]
TAG = "fable-forge"  # our hook commands contain the hook_dir path -> identifiable

with open(path, encoding="utf-8") as f:
    try:
        cfg = json.load(f)
    except Exception:
        cfg = {}

hooks = cfg.setdefault("hooks", {})

def strip_ours(event):
    groups = hooks.get(event, [])
    kept = []
    for g in groups:
        g2 = dict(g)
        g2["hooks"] = [h for h in g.get("hooks", [])
                       if TAG not in (h.get("command", ""))]
        if g2["hooks"]:
            kept.append(g2)
    if kept:
        hooks[event] = kept
    elif event in hooks:
        del hooks[event]

for ev in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"):
    strip_ours(ev)

if mode == "install":
    def cmd(name):
        return {"type": "command", "command": f'python3 "{hook_dir}/{name}"'}
    hooks.setdefault("UserPromptSubmit", []).append({"hooks": [cmd("user_prompt_submit.py")]})
    hooks.setdefault("PreToolUse", []).append(
        {"matcher": "Edit|Write|MultiEdit|NotebookEdit", "hooks": [cmd("pre_tool_use.py")]})
    hooks.setdefault("PostToolUse", []).append(
        {"matcher": "Edit|Write|MultiEdit|NotebookEdit", "hooks": [cmd("post_tool_use.py")]})
    hooks.setdefault("Stop", []).append({"hooks": [cmd("stop.py")]})

with open(path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
    f.write("\n")

print(f"fable-forge: {mode} complete -> {path}")
print("  events:", ", ".join(k for k in ("UserPromptSubmit","PreToolUse","PostToolUse","Stop") if k in hooks))
PY

if [ "$MODE" = "install" ]; then
  echo "fable-forge: active for all Claude Code sessions. Disable per project with: touch .forge/OFF"
  echo "             one-off bypass: FORGE_BYPASS=1"
else
  echo "fable-forge: removed."
fi
