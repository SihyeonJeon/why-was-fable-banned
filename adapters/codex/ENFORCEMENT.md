# Codex enforcement design

Goal: force the SPEC → IMPLEMENT → VERIFY procedure on Codex (and whatever model
it drives, e.g. gpt-5.5), so a weaker model is gated through the same process —
and so an orchestrator's spawned workers all ride on top of the gate.

## Enforcement tiers for Codex

| Tier | Mechanism | Strength | Status |
|---|---|---|---|
| **Worktree-accept (PRIMARY headless)** | `forge-codex-accept.sh`: run the worker in a **throwaway git worktree**, then apply its diff to the real repo **only if** the spec+done gate passes and it touched no `forbidden_paths` | **Total enforcement at the acceptance boundary** — the real repo never receives unspeced / forbidden work; ≈ ONE codex pass | co-designed + cross-verified with the Codex CLI; mechanics tested (accept + reject paths) |
| Native hooks | `[[hooks.PreToolUse]]` blocks `apply_patch` (exit 2) in one session | hard in-session **when it fires** | scripts proven by simulation; **does NOT fire in headless `codex exec`** — edits are native `file_change`, not `apply_patch` (see caveat) |
| AGENTS.md | global `~/.codex/AGENTS.md` mandate | soft; reduces gate round-trips | done |
| forge-codex wrapper | phase-gated multi-`codex exec` loop | hard but **~10×** (measured) | older fallback for non-git contexts |

### Worktree-accept — the answer to "can you enforce everything headless?"

Yes. Mid-edit *interception* is unavailable in `codex exec` (file writes bypass
the hook), but *enforcement* does not require interception — it requires that
unaccepted work never reaches the real repo:

```sh
git -C $REPO worktree add --detach $WT $BASE     # disposable copy
forge_gate scaffold --root $WT --goal "$TASK"
codex exec -s workspace-write -C $WT "$TASK"      # ONE pass; writes spec + code in $WT
git -C $WT diff --name-only $BASE > .forge/edits.txt   # real edit set (hooks don't fire)
forge_gate validate --root $WT --gate done        # spec + evidence + forbidden_paths
# PASS -> git -C $REPO apply --index <$WT diff>     ;  FAIL -> discard $WT, repo untouched
```

The `forbidden_paths` check, which the PostToolUse hook would feed in Claude Code,
is fed here from `git diff` — so the "no conflict with architecture/policy"
guarantee holds headless too. Cost is ≈ one worker pass (not the wrapper's 3),
the spec adds ~1–2k tokens. Co-designed with Codex, which hardened the original
acceptance-gate idea: disposable worktree (no polluted-rerun / canonical-repo
mutation), git-diff verification, apply-only-on-pass, re-validate after apply.

Codex's hook engine (v0.124.0+, [docs](https://developers.openai.com/codex/hooks))
mirrors Claude Code's on paper: same events, same exit-2 block protocol, so the
**same `adapters/hooks/*.py` are wired for both** (matcher `apply_patch|Edit|Write`;
an edit arrives as `tool_name:"apply_patch"` with the path inside
`tool_input.command`). The shared hook **scripts** are verified by simulation
(block on a real edit, allow `.forge/` authoring, log the patched path).

> **Honesty caveat (measured, ≥5 runs, incl. a Codex-CLI consult):** the PreToolUse
> hook **does not fire in `codex exec --json`**. Tried: repo-local
> `<repo>/.codex/hooks.json`, `--dangerously-bypass-hook-trust`, and (per Codex's own
> advice) adding `[projects."<dir>"] trust_level = "trusted"` to `~/.codex/config.toml`
> + `-C <dir>`. In every run a trivial marker+`exit 2` hook never ran and the edit
> went through. Root cause (from the event stream): in exec `--json`, edits surface
> as native **`file_change`** items — there is no `apply_patch`/tool-call event for a
> PreToolUse hook to intercept. Codex's docs/CLI claim hooks run in exec, but
> empirically they do not gate `file_change` here (possibly a TUI-only path, or a
> 0.139 limitation). **So for headless Codex, the confirmed enforcement is the
> wrapper** (~10×) or the soft AGENTS.md mandate. **Claude Code's native hooks DO
> fire** (the live mechanism running this very session), so its in-session ~<2× path
> is real. Promote this tier table only if/when Codex headless firing is reproduced
> (likely interactive `codex` TUI, untestable from here).

## Honest ceiling

This forces the *process*. It does not raise the model's reasoning ceiling. A
weaker model on the gate produces a spec and evidence it otherwise would skip;
whether that closes the gap to a reference model is the benchmark question, not a
claim made here.

## Runtime findings (verified live against codex-cli 0.139)

Resolved by driving the real binary:

1. **[sandbox/exec invocation] — RESOLVED.** Non-interactive `codex exec` needs
   three things or it fails: `--skip-git-repo-check` (else: *"Not inside a trusted
   directory and --skip-git-repo-check was not specified"*), a writable sandbox
   `-s workspace-write`, and stdin closed `< /dev/null` (else it blocks on
   *"Reading additional input from stdin..."*). All three are now baked into the
   wrapper's `CODEX=(...)` array + per-call `< /dev/null`.
2. **[output-schema] — DROPPED.** `--output-schema` runs OpenAI strict structured
   output, which 400s unless every object has `additionalProperties:false` and all
   properties are `required` (*"'additionalProperties' is required ... to be
   false"*). It also constrains only the final message, not the written file. The
   gate validates the **file**, so it is the source of truth; the wrapper no longer
   passes `--output-schema`. `spec.schema.json` stays as the human/agent contract.
3. **[single-session resume] — CONFIRMED, and it is the token-efficiency fix.**
   The wrapper runs SPEC / IMPLEMENT / VERIFY as `codex exec` then
   `codex exec resume <thread_id> ...`, so the model's exploration is retained
   across phases (verified: a resume call saw and extended a file written in the
   prior turn). Caveat learned the hard way: **`codex exec resume` has NO `-s/`
   `--sandbox` flag** (it inherits the session's sandbox) — passing `-s` makes
   resume reject the whole call. First-call and resume-call option sets differ in
   the wrapper. The resumed turns are ~92% cached input, so the cumulative context
   is nearly free — this is what keeps the wrapper near the in-session token cost.

4. **[native hooks] — RESOLVED.** Codex 0.124.0+ has a full hook engine
   ([docs](https://developers.openai.com/codex/hooks)). PreToolUse blocks via exit
   2 + stderr (also `{"decision":"block"}` / `permissionDecision:"deny"`). stdin
   payload carries `tool_name` (`apply_patch`/`Bash`), `tool_input.command`, `cwd`,
   `model`, `transcript_path`. Config in `~/.codex/hooks.json` or config.toml
   `[[hooks.PreToolUse]]`; repo-local `<repo>/.codex/hooks.json` also works. Trust:
   `/hooks` interactively, or `--dangerously-bypass-hook-trust` for automation.
   **This is now the primary path** (see the tier table). The execpolicy/`--output-
   schema` ideas are obsolete for gating.

## Files

- `adapters/hooks/*.py` — the shared, runtime-agnostic hooks (the enforcement).
- `install.sh` — merges native hooks into `~/.codex/hooks.json`, places the global
  `AGENTS.md` mandate, and puts the `forge-codex` fallback on PATH. Idempotent.
- `AGENTS.md` — global procedure mandate (soft tier; fewer gate round-trips).
- `forge-codex.sh` — the fallback wrapper (no-hook environments; ~10×).
- `spec.schema.json` — the spec contract (human/agent reference).
- `execpolicy.rules.template` — legacy, superseded by native hooks.
