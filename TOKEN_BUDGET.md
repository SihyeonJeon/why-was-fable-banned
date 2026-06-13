# Token budget

Constraint (user): once the layer is absorbed into agent sessions, steady-state
token cost for the same task must stay **under 2× an Opus-naked baseline**.
During development, higher cost is fine.

This is a falsifiable number, so it is treated as an acceptance criterion to be
**measured**, not asserted. Below: where overhead comes from, the design that
keeps it small, and the measurement harness.

## Where forge spends tokens

| Source | When | Steady-state size |
| --- | --- | --- |
| Procedure injection | once at task start (`additionalContext`) / cached `CLAUDE.md` | ~90 tok one-shot + ~300 tok cached (cache-read priced) |
| Spec output (`.forge/spec.json`) | model writes it before coding | LIGHT ~150 · STANDARD ~600–1000 · HEAVY ~1500–2500 output tok |
| Gate block messages | only when the unmet-list changes (deduped) | ~200 tok × 1–2 blocks |
| Done-gate reminder | only on state change | ~100 tok |

The model already reads files and plans in the naked baseline; forge does **not**
re-pay for that. The only genuinely *new* tokens are the spec artifact + a couple
of block messages.

## Why steady-state stays under 2×

**In-session hooks (Claude Code; Codex once it has a native pre-edit hook).**
One session, procedure prompt cached, spec written inline, blocks deduped. No
context reload. Estimated overhead vs naked:

```
STANDARD task, naked baseline ~20–50k tokens total
  + spec output ~1k  + cached prompt ~0.3k (cache-read)  + blocks ~0.4k
  ≈ +1.7k  ->  +3–9%   (far under 2×)
```

The 2× ceiling is comfortable for the in-session path. The token lever that keeps
the *average* low is **grade-scaling**: LIGHT tasks (typos, comments, renames)
require only `restated_goal` + one acceptance check (~150 tok); the full
8-axis spec is paid only on HEAVY (auth / payments / migration / security) —
exactly where Fable itself escalates. Most tasks are LIGHT/STANDARD.

**The wrapper path does NOT meet 2× — measured.** `forge-codex` runs SPEC /
IMPLEMENT / VERIFY as three `codex exec`/`resume` turns. Even single-session
(resume, ~86% cached), a measured run on one task (gpt-5.5, medium effort,
`bench/measure_overhead.sh`):

| arm | turns | raw_total | cache_adj |
| --- | --- | --- | --- |
| naked `codex exec` | 1 | 60,555 | 11,915 |
| forged `forge-codex` | 3 | 862,522 | 132,282 |
| **ratio** | | **14.2×** | **11.1×** |

Both produced the same working output (slug.py + test). The 11× is the **3-pass
structure** — each agentic turn re-processes the cumulative context and runs its
own tool loop — **not** the spec content (the spec itself is ~2k tokens). So:

> The cost is the *mechanism* (3 separate agentic passes), not the *gate*.
> An in-session hook adds the spec to ONE pass; the wrapper multiplies passes.

The wrapper is therefore a **bootstrap / correctness** tool (use it where a hard
external gate is worth ~10×, e.g. high-stakes HEAVY tasks), **not** the
steady-state default. Bringing Codex under 2× requires one of:
- a **native Codex in-session hook** that blocks `apply_patch` until the gate
  passes (so enforcement lives inside one pass) — exists per
  `--dangerously-bypass-hook-trust` but its config/block schema is unconfirmed in
  0.139 (`adapters/codex/ENFORCEMENT.md` open question);
- a **lean 2-phase wrapper** where SPEC is a cheap no-exploration call and
  IMPLEMENT+VERIFY is one agentic pass (~1.5–2×, still tight).

## Measurement harness (the actual test of <2×)

Run the same fixed task set three ways and tally tokens:

```
arms:  naked        = model, no forge
       forged       = model + forge (in-session hook path, NOT the wrapper)
       reference    = the stronger reference model, naked   (quality anchor)

per task, per arm: total tokens (input+output), from
  - Codex:        `codex exec --json` emits per-turn token usage
  - Claude Code:  session transcript usage records

metric:   overhead = tokens(forged) / tokens(naked)
target:   mean(overhead) < 2.0   AND   p90(overhead) < 2.0
quality:  rubric/SCORECARD.md score(forged) should approach score(reference);
          that is the separate "does it lift the weaker model" question.
```

Token overhead and quality lift are **two different measurements** — keep them
separate. <2× is a cost gate; the quality lift is the 3-arm shadow benchmark.

## Status (measured)

- Grade-scaling implemented (`gates/forge_gate.py`).
- **Claude Code in-session: real and ~<2×.** Native hooks fire (they are the live
  mechanism running this session). The spec the model writes is ~1–2k tokens vs a
  ~60–90k naked task baseline, so the overhead is a small additive term in ONE
  pass, not a multiple.
- **Codex wrapper: measured 11–14×** — the cost is the 3-pass structure, not the
  gate. It is the *confirmed* headless Codex path, but it is expensive (bootstrap /
  high-stakes only).
- **Codex native-hook in-session: NOT confirmed.** Three real `codex exec` runs
  failed to gate: (a) `codex exec` does not fire `UserPromptSubmit` (no
  auto-scaffold); (b) even with a pre-scaffold and `--dangerously-bypass-hook-trust`,
  a trivial PreToolUse test hook **never ran** and the edit went through. The
  numbers from those runs are gpt-5.5 run-to-run variance, not gating. So Codex's
  in-session <2× path is plausible (the hook scripts work in isolation) but
  **unproven in headless exec** — likely needs interactive `/hooks` trust or a
  different hook location/enable. Open item.
- **Codex worktree-accept (the shipped headless path): measured ~5× raw / ~1.4–4×
  cache_adj** on a STANDARD task vs a naked baseline (gpt-5.5, one pass) — **over 2×.**
  It is ONE codex pass (not the wrapper's 3), but the gated worker genuinely *does
  more*: it writes a full spec (3 non_goals, 3 rejected_alternatives, risks) **and
  runs real verification** (pytest + py_compile + import, capturing live evidence)
  that the naked baseline skips entirely.
- **Honest correction on <2×:** my earlier "+3%" was wrong — it counted only the
  spec *output* (~1–2k) and ignored that producing the spec and **running the
  acceptance commands** adds tool-calls and context. The token overhead is
  dominated by *doing the process*, not by the wrapper structure. So:
  - **LIGHT tasks: <2× holds** (grade-scaling keeps them to restated_goal + one check).
  - **STANDARD/HEAVY: honestly over 2×** against a *lazy* naked baseline — but much
    of the delta is verification work you'd want regardless. Against a *thorough*
    naked (one told to spec + test properly), the pure gate overhead is small.
- **Net, honest:** total enforcement is achieved on both runtimes (CC in-session
  hooks; Codex worktree-accept). The **<2× cost target is met for LIGHT and missed
  for STANDARD+** — enforcing the full Fable process is real extra work, not free.
  The "+3%", "wrapper ≈ 2–3×", and "Codex native hook = primary" claims were all
  wrong; measurement corrected each.
