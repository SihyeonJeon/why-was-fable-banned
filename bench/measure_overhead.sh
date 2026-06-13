#!/usr/bin/env bash
# Measure forge token overhead: same task, naked codex vs single-session forge-codex.
# Target: cache_adj overhead < 2.0x.  Uses gpt-5.5 at FORGE_EFFORT (default medium).
set +e
FORGE="$(cd "$(dirname "$0")/.." && pwd)"
SUM="python3 $FORGE/bench/sum_tokens.py"
EFFORT="${FORGE_EFFORT:-medium}"
TASK="${BENCH_TASK:-Add a function slugify(s) to slug.py: lowercase the input, replace runs of non-alphanumeric characters with a single hyphen, and strip leading/trailing hyphens. Add a pytest test file test_slug.py with 3 cases. Stdlib only.}"
B=/tmp/forge_bench; rm -rf "$B"; mkdir -p "$B"

echo "=== ARM naked (codex exec, effort=$EFFORT) ==="
N="$B/naked"; mkdir -p "$N"; (cd "$N" && git init -q)
( cd "$N" && codex exec --json --skip-git-repo-check -s workspace-write \
    -c model=gpt-5.5 -c model_reasoning_effort="$EFFORT" "$TASK" < /dev/null > run.jsonl 2>/dev/null )
naked="$($SUM "$N/run.jsonl")"
echo "$naked"

echo "=== ARM forged (forge-codex, single session, effort=$EFFORT) ==="
F="$B/forged"; mkdir -p "$F"; (cd "$F" && git init -q)
( cd "$F" && FORGE_EFFORT="$EFFORT" "$FORGE/adapters/codex/forge-codex.sh" "$TASK" )
forged="$($SUM "$F/.forge/codex_run.jsonl")"
echo "$forged"

echo "=== RESULT ==="
python3 - "$naked" "$forged" <<'PY'
import json, sys
n = json.loads(sys.argv[1]); f = json.loads(sys.argv[2])
print(f"naked : {n}")
print(f"forged: {f}")
for k in ("raw_total", "cache_adj"):
    r = (f[k] / n[k]) if n[k] else 0.0
    verdict = "PASS (<2x)" if 0 < r < 2 else "OVER 2x"
    print(f"  {k:9s} forged/naked = {r:.2f}x  -> {verdict}")
PY
echo "=== artifacts ==="
echo "naked files:";  ls "$N" 2>/dev/null
echo "forged files:"; ls "$F" 2>/dev/null; echo "forged spec gate:"; python3 "$FORGE/gates/forge_gate.py" status --root "$F" 2>/dev/null
