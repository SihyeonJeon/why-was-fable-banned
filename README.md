# fable-forge

A runtime-agnostic **enforcement layer** that forces an AI coding agent through a
spec-first, evidence-gated engineering procedure: the agent **cannot edit code
until it has written — and the gate has checked — the spec** (restated goal,
non-goals, context rationale by authority, ≥2 rejected alternatives with the
boundary each breaks, risks, and runnable acceptance criteria). Works in **Claude
Code** and **Codex**; one shared gate, installed per-CLI.

**Why.** A coding agent's reasoning evaporates when the session ends, and a rushed
agent skips the spec/verify discipline a careful engineer wouldn't. fable-forge
makes that discipline non-optional and **auditable** — every change carries a
decision record, and unspeced or forbidden work never reaches your repo.

**What it is / isn't.** It enforces *process* and *auditability* — not raw
capability. In our benchmark, forcing the procedure did not make a model produce
more-correct code on tasks it already handles ([`bench/BENCHMARK.md`](bench/BENCHMARK.md));
the value is discipline, evidence, and safety, not an intelligence boost. Quick
quality scoring of the spec's *reasoning* is the optional judge layer
([`JUDGE.md`](JUDGE.md)).

> Quick start: `git clone <this repo> && cd fable-forge && sh install.sh`

Local-only. Framed as **engineering-procedure discipline**, not model
impersonation — the procedure is what's transferable; capability stays the host
model's.

## What it enforces

Distilled from 19 filled decision traces across 7 projects (see
`~/fable-decision-model.md` and `~/fable-decision-insights.ko.md`), reduced to
the rules that survived an independent cross-review and held across unrelated
domains:

1. Don't assert before reading — defer interpretation until ground truth.
2. Context by authority, not topic — scan broad, commit only governing contracts.
3. Scope by negation — fence the over-broad version as non-goals.
4. Reject alternatives by naming the broken boundary — remove a path, don't guard it.
5. "Done" is falsifiable — runnable commands/observations; **no evidence → not done (fail closed)**.
6. Preserve authority in delegation — no self-approval; surface destructive/manual steps.

Plus the values layer (honesty, evidence-over-claims, determinism-over-impression)
that the reference system-prompt analysis showed are model-common — reinforced,
not invented.

## Three enforcement tiers (degrade by runtime capability)

| Tier | Mechanism | Works on |
| --- | --- | --- |
| 1 — Hard gate (in-session) | a native PreToolUse hook blocks edits until the spec passes, inside one session | **Claude Code** — hooks fire (confirmed); ~<2× tokens |
| 1b — Wrapper | phase-gated multi-pass loop | **Codex** — the confirmed headless path, but ~10× tokens |
| 2 — Instruction | procedure prompt injected as system prompt / AGENTS.md | any model incl. GPT-5.5, zero runtime support |

Built **hard-gate-first** on the self-contained `gates/forge_gate.py` engine (no
`fable-pack` dependency). The **shared `adapters/hooks/*.py`** are runtime-agnostic
(exit-2 block; handle both Claude Code `Edit`/`Write` and Codex `apply_patch`).
**Claude Code's native hooks fire** — so its in-session path is real and keeps
tokens near baseline (spec added to one pass, not multiplied). **Codex** has the
same hook engine on paper, but in testing the hook did not fire in headless
`codex exec`, so the confirmed Codex path today is the wrapper (expensive) —
in-session Codex is an open item (see `adapters/codex/ENFORCEMENT.md`).
Orchestration: user-level hooks (`~/.claude/settings.json`) are inherited by every
spawned worker.

## Layout

```
gates/forge_gate.py           the gate engine — deterministic, grade-scaled, stdlib only
prompts/FABLE_PROCEDURE.md    procedure = gate content + soft instruction layer
rubric/SCORECARD.md           0–2 self-check + benchmark scoring rubric
TOKEN_BUDGET.md               the <2x steady-state design + measurement method
tests/test_forge_gate.py      18 gate regression tests
bench/measure_overhead.sh     token overhead measurement (naked vs forged)
adapters/
  claude-code/                hard gate via hooks + install.sh (user-level → all sessions)
  codex/                      forge-codex single-session wrapper + AGENTS.md + ENFORCEMENT.md + install.sh
```

## Grade scaling (the token lever)

A work prompt is auto-graded; the gate depth — and therefore the token cost —
scales with it, matching where Fable itself escalates:

| Grade | Trigger | Gate demands |
| --- | --- | --- |
| LIGHT | typo / comment / rename / format | restated_goal + one runnable acceptance check |
| STANDARD | default work | + non_goals, must_read (real paths), ≥2 rejected_alternatives, risks, ≥1 invariant |
| HEAVY | auth / payments / migration / security | + constraint provenance, similar_implementation, recorded validation loop |

Most tasks are LIGHT/STANDARD, so average overhead stays small — see `TOKEN_BUDGET.md`.

## Validation

Whether this actually lifts a weaker model toward reference behavior is an
empirical claim, not an assumption. The test is a 3-arm shadow benchmark
(`model-naked` vs `model+forge` vs `reference`), same task, same acceptance
commands, blind cross-family judge, scored with `rubric/SCORECARD.md`. Tooling
exists; the measurement is the next milestone. No transfer-effect claim ships
without it.
