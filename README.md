# why-was-fable-banned

**English** · [한국어](README.ko.md)

> Gate for AI coding agents: blocks edits until a spec passes.

![license](https://img.shields.io/badge/license-MIT-blue)
![python](https://img.shields.io/badge/python-3-3776AB?logo=python&logoColor=white)
![Claude Code](https://img.shields.io/badge/Claude%20Code-native%20hooks-d97757)
![Codex](https://img.shields.io/badge/Codex-worktree--accept-10a37f)
[![tests](https://github.com/SihyeonJeon/why-was-fable-banned/actions/workflows/ci.yml/badge.svg)](https://github.com/SihyeonJeon/why-was-fable-banned/actions/workflows/ci.yml)

![why-was-fable-banned](assets/social-preview.jpg)

The agent can't edit code until it writes `.wfb/spec.json` and a deterministic
gate accepts it: restated goal, non-goals, context chosen by authority, ≥2 rejected
alternatives with the boundary each breaks, risks, and runnable acceptance. One
shared gate, installed as hooks. Works in **Claude Code** and **Codex**.

**Same prompt, same model — gate off vs on.** *"Implement a water-current + fish
simulation,"* Opus 4.8, identical prompt both runs:

![Opus 4.8 on the same prompt, without and with the WFB gate](assets/opus-wfb-compare.gif)

Left (naked) stops at thin ripples. Right, the gate makes the model keep working until
its own acceptance criteria pass — a volumetric vortex with schooling fish. One
anecdote (n=1), not a capability benchmark; measured numbers are [below](#benchmarks).

![demo: edit blocked until the spec passes, then applied](assets/demo.gif)

> [!NOTE]
> A spec must exist and pass before edits land, and unspeced or forbidden-path work
> never reaches your repo. Every change ships with an auditable decision record.

## Why "Fable-style"

Fable-style discipline means spec before code, scoped execution, and verification you
can re-run — long-horizon work that doesn't drift. WFB doesn't make the model that
disciplined; it **externalizes the discipline as a hard gate** the model can't skip:

- **No edit before a passing spec** — `PreToolUse` hook exits 2 until the spec validates.
- **No "done" without live acceptance output** — verification is fail-closed.
- **Forbidden paths are enforced, not suggested.**
- **High-risk work auto-escalates** to a heavier gate (typo → LIGHT, auth/migration → HEAVY).
- **Codex changes land only through a throwaway worktree**, after the gate passes.

It enforces *process*, not *capability* — see the [honest benchmark](#benchmarks).

## Install

```sh
git clone https://github.com/SihyeonJeon/why-was-fable-banned
cd why-was-fable-banned && sh install.sh
```

`python3` only, stdlib. Remove: `sh install.sh --uninstall`.

## Scope

- `sh install.sh` installs **machine-wide**: every Claude Code project on this computer (and every subagent / orchestrated worker) inherits the gate
- `sh install.sh --here` installs for **this repo only** (Claude Code project-level `.claude/settings.json`)
- **Toggle in-session at three scopes** by typing (the hook handles it, never sent to the model):

  | type | scope | persists |
  | --- | --- | --- |
  | `wfb off` / `wfb on` | this **project** dir | across sessions in this repo |
  | `wfb off here` / `wfb on here` | this **session** only | this chat |
  | `wfb off all` / `wfb on all` | the whole **machine** | everywhere |

  Most-specific wins (session > project > machine > default on), so you can turn the project off and force one hard session on. State is a file, so it survives reboots until you flip it back. `wfb status` shows all three. One-off env bypass: `WFB_BYPASS=1`.
- **Status line**: when the gate is on, `[why-was-fable-banned]` shows in the Claude Code status line (installed only if you don't already have one; otherwise the installer prints how to add the segment)
- **Works wherever Claude Code runs**: terminal, the VS Code and JetBrains extensions, desktop (they share the same hooks), plus Codex. It does not apply to non-Claude-Code/Codex agents (e.g. Cursor's own agent)

## How it works

- **Block**: a `PreToolUse` hook intercepts every edit and exits 2 until the spec passes
- **Spec**: restated goal · non-goals · context by authority · ≥2 rejected alternatives · risks · runnable acceptance · forbidden paths
- **Verify**: "done" isn't done until each acceptance command shows live output (fail closed)
- **Apply**: on headless Codex the worker runs in a throwaway git worktree; only a gate-passing diff reaches your repo

## Quickstart

1. `sh install.sh`: wires the hooks at user level (every project + subagent inherits it)
2. Prompt your agent to do real work: a gated task auto-starts
3. The agent writes `.wfb/spec.json` (it's told exactly what to fill); edits stay blocked until it passes
4. It implements, runs the acceptance commands, records evidence, then closes

Grade auto-scales the depth: typos (LIGHT) require only a restated goal + one
acceptance check; auth/payments/migration (HEAVY) pay the full gate.

## Supported agents

- **Claude Code**: native hooks, in-session block; the grade-specific contract is injected up front
- **Codex**: `wfb-codex-accept "<goal>" --repo <dir>` (worktree-accept; headless)

## Where the rules came from

Recorded real engineering sessions with hooks (42 traces), extracted them as a
structured decision schema, generalized 19 into 8 decision axes, and cross-checked
the generalization with a second model. Observable artifacts only: no
chain-of-thought, local, secrets masked.

<details>
<summary>Three layers, increasing cost and depth</summary>

| layer | checks | how |
| --- | --- | --- |
| `gates/wfb_gate.py` | **form**: fields, real paths, forbidden, fail-closed | deterministic, free |
| `gates/wfb_judge.py` | **meaning**: 0–2 rubric, gaming detection | optional LLM judge |
| `bench/` | **correctness**: hidden grader | runs the tests |

</details>

## Benchmarks

Measured in this repo, reproducible (`bash bench/run_quality.sh`, `bash tests/run_all.sh`):

| measure | gate OFF | gate ON |
| --- | --- | --- |
| Decision record per change | none | **enforced** |
| Unspeced or forbidden-path edits reaching the repo | possible | **blocked** |
| Adversarial / edge gate tests (downgrade, bypass, malformed, no-brick) | n/a | **35/35 pass** |

### Measured: SWE-bench, gate OFF vs ON (same model — Opus, both arms)

| benchmark | naked (gate OFF) | gated (gate ON) |
| --- | --- | --- |
| SWE-bench Verified (light-repo slice, N=28) | 22/28 | **23/28** |
| SWE-bench Pro (qutebrowser, N=10) | 7/10 | **8/10** |
| **combined (N=38)** | **29/38** | **31/38** |

**+2 across 38 tasks, zero regressions** (the gate never lost a task naked solved; it
won the ones it won by matching the exact test contract instead of a plausible-but-wrong
shortcut) — at **~2–3× the tokens**. This is small and within noise: the gate enforces
*process*, not *capability*. On toy tasks with a hidden grader it shows **no lift at
all** (both arms 10/10) — see [bench/BENCHMARK.md](bench/BENCHMARK.md). Raw per-instance
results: `bench/results/verified/`, `bench/results/pro/`.

Validated live: a Codex run left a protected file untouched and applied only the
gate-passing diff; if verification is incomplete it retries, then rejects rather than
apply. Details: [bench/BENCHMARK.md](bench/BENCHMARK.md) · [TOKEN_BUDGET.md](TOKEN_BUDGET.md).

## FAQ

**What is why-was-fable-banned (WFB)?** A spec-first, evidence-gated edit boundary for
AI coding agents. It blocks an agent (Claude Code or Codex) from editing code until it
writes a spec a deterministic gate accepts, and blocks "done" until live acceptance
output proves the work.

**Does it make Opus or Codex smarter?** No. It enforces *process*, not *capability*. On
SWE-bench it lifts the same Opus model by +2/38 at ~2–3× tokens (within noise); on toy
tasks, no lift. Its value is enforcement, evidence, and an auditable decision record —
not injecting intelligence.

**Is it a Fable 5 plugin?** No. It's a model-agnostic gate installed as hooks. It runs
the same discipline Fable-style autonomy implies — spec, scope, re-runnable verification
— as an external boundary, so Opus 4.8 or Codex must follow it whether or not the model
would on its own.

**How is it different from a prompt, CLAUDE.md, or a behavior plugin?** Those are
suggestions the model can ignore. WFB is hard enforcement: a `PreToolUse` hook exits 2
and the edit never happens until the spec passes. Forbidden paths and fail-closed
verification are enforced, not requested.

**Works with:** Claude Code (terminal, VS Code / JetBrains extensions, desktop) and
Codex. Not other agents (e.g. Cursor's own agent).

## License

PRs welcome. MIT.
