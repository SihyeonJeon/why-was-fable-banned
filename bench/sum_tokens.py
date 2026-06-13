#!/usr/bin/env python3
"""Sum Codex `--json` token usage across all turns in a JSONL run log.
raw_total = input + output + reasoning ; cache_adj = (input - cached) + output + reasoning
(cache_adj is the real billable-ish cost once prompt caching is counted)."""
import json
import sys

ti = to = tr = tc = turns = 0
for ln in open(sys.argv[1], encoding="utf-8", errors="replace"):
    ln = ln.strip()
    if not ln or ln[0] != "{":
        continue
    try:
        o = json.loads(ln)
    except Exception:
        continue
    if o.get("type") == "turn.completed":
        u = o.get("usage", {}) or {}
        ti += u.get("input_tokens", 0)
        to += u.get("output_tokens", 0)
        tr += u.get("reasoning_output_tokens", 0)
        tc += u.get("cached_input_tokens", 0)
        turns += 1

print(json.dumps({
    "turns": turns, "input": ti, "cached": tc, "output": to, "reasoning": tr,
    "raw_total": ti + to + tr, "cache_adj": (ti - tc) + to + tr,
}))
