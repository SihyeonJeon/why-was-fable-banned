#!/usr/bin/env python3
"""UserPromptSubmit: auto-start a gated task on work-shaped prompts.

Scaffolds `.forge/` and injects the procedure once. Questions / chatter pass
through untouched. `.forge/OFF` disables auto-start. Runtime-agnostic."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import read_payload, project_root, run_gate  # noqa: E402

NOTICE = (
    "[fable-forge] A gated engineering task is now active. Before editing any "
    "implementation file you must write .forge/spec.json: restated_goal (intent + "
    "constraint envelope, not the raw ask), non_goals, must_read (real files chosen "
    "by authority, with reasons), >=1 constraints.invariant, >=2 rejected_alternatives "
    "(category + the boundary each breaks), risks (severity by blast radius + runnable "
    "mitigation), acceptance_criteria (runnable commands). List any architecture/policy "
    "files you must NOT touch in forbidden_paths. Edits are blocked until the SPEC gate "
    "passes; close only when every acceptance criterion cites live evidence. Do not "
    "narrate this to the user."
)


def emit_context(text: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit", "additionalContext": text}}))


def main() -> int:
    if os.environ.get("FORGE_BYPASS") == "1":
        return 0
    payload = read_payload()
    root = project_root(payload)
    if (Path(root) / ".forge" / "OFF").exists():
        return 0
    if run_gate("active", "--root", root)[0] == 0:
        return 0  # already active

    prompt = payload.get("prompt", "") or ""
    if run_gate("classify", "--text", prompt)[0] != 0:
        return 0  # not work-shaped

    run_gate("scaffold", "--root", root, "--goal", prompt[:500])
    emit_context(NOTICE)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        sys.stderr.write(f"fable-forge user_prompt_submit error (failing open): {exc}\n")
        raise SystemExit(0)
