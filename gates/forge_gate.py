#!/usr/bin/env python3
"""fable-forge gate engine — self-contained, stdlib only, model-agnostic.

Enforces the SPEC -> IMPLEMENT -> VERIFY procedure by validating a lightweight
spec artifact (`.forge/spec.json`) under the project root. Runtime adapters
(Claude Code hooks, Codex execpolicy/wrapper) call this and block on a non-zero
exit. No dependency on fable-pack; nothing networked; secrets never read.

Subcommands:
  scaffold  --root R --goal G [--grade L]   create .forge/, ACTIVE marker, spec skeleton
  validate  --root R --gate spec|done       exit 0 pass / 1 fail; prints failures
  active    --root R                         exit 0 if a task is active, else 1
  status    --root R                         human-readable state
  close     --root R                         clear ACTIVE (after done gate passes)
  classify  --text T                         exit 0 if prompt is work-shaped, else 1

Exit codes: 0 = pass/yes, 1 = fail/no, 2 = usage/internal error.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from pathlib import Path

FORGE_DIR = ".forge"
SPEC_NAME = "spec.json"
ACTIVE_NAME = "ACTIVE"

ALT_CATEGORIES = {"tempting_shortcut", "architecture", "scope", "compatibility"}
SEVERITIES = {"low", "medium", "high", "blocking"}
ACC_TYPES = {"command", "grep", "stat", "artifact", "human_visual", "test"}
# Evidence that is really a non-run admission — the honesty invariant, enforced.
FAKE_MARKERS = ("not run", "notrun", "did not run", "didn't run", "assumed",
                "would pass", "should pass", "to be done", "tbd", "todo",
                "n/a", "pending", "placeholder", "will run", "not yet")

SPEC_TEMPLATE = {
    "grade": "STANDARD",
    "phase": "SPEC",
    "raw_goal": "",
    "restated_goal": "",
    "non_goals": [],
    "ambiguities": [],              # {question, resolution, authority}
    "must_read": [],                # {path, authority_reason}
    "similar_implementations": [],  # {path, symbol, why}  (HEAVY: mirror to avoid breaking an invariant)
    "constraints": {"architectural": [], "invariant": [], "convention": []},  # arch: {constraint, evidence_ref}
    "rejected_alternatives": [],    # {category, alternative, broken_boundary}
    "risks": [],                    # {risk, severity, mitigation, acceptance_ref}
    "observations": [],             # {observation, changed_understanding(bool), evidence_ref}  (validation loop)
    "deferred": [],                 # tracked backlog / abandoned-but-recorded paths
    "forbidden_paths": [],          # globs the change must NOT touch (architecture/policy); verified at done
    "acceptance_criteria": [],      # {criterion, verify:{type,value}, evidence}
}

# Work-shaped prompt heuristic (English + Korean). Questions / chatter do not gate.
WORK_RE = re.compile(
    r"\b(implement|fix|refactor|add|build|create|write|change|update|migrat|"
    r"remove|delete|rename|optimi|debug|patch|integrat|wire|hook up|set up)\b",
    re.I,
)
WORK_KO = ("구현", "수정", "고쳐", "고치", "추가", "만들", "리팩", "변경", "바꿔",
           "바꾸", "삭제", "지워", "통합", "연결", "배선", "최적화", "패치")
QUESTION_KO_ENDINGS = ("나요", "까요", "가요", "은가", "는가", "ㄴ가", "?", "？")
HEAVY_RE = re.compile(r"\b(auth|payment|migrat|security|crypto|password|secret|"
                      r"billing|token|permission|delete)\b", re.I)
HEAVY_KO = ("보안", "결제", "인증", "마이그", "비밀번호", "권한", "토큰", "과금")


def spec_path(root: Path) -> Path:
    return root / FORGE_DIR / SPEC_NAME


def active_path(root: Path) -> Path:
    return root / FORGE_DIR / ACTIVE_NAME


def load_spec(root: Path):
    p = spec_path(root)
    if not p.exists():
        return None, f"no spec at {p}"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # malformed JSON must read as a gate failure, not crash
        return None, f"spec.json is not valid JSON: {exc}"
    if not isinstance(data, dict):
        return None, "spec.json must be a JSON object"
    return data, None


def _nonempty(v) -> bool:
    return isinstance(v, str) and v.strip() != ""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _inv_text(x) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return x.get("invariant") or x.get("text") or ""
    return ""


def _forbidden_hits(spec: dict, root) -> list:
    """Edits (recorded by the PostToolUse hook in .forge/edits.txt) that match a
    forbidden_paths glob — i.e. the implementation touched an architecture/policy
    boundary the spec declared off-limits. Verifies no-conflict, not just declares."""
    pats = [p for p in spec.get("forbidden_paths", []) if isinstance(p, str) and p.strip()]
    if not pats or root is None:
        return []
    log = Path(root) / FORGE_DIR / "edits.txt"
    if not log.exists():
        return []
    try:
        edited = [ln.strip() for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except Exception:
        return []
    hits = []
    for ed in edited:
        for pat in pats:
            if fnmatch.fnmatch(ed, pat) or (pat.strip("*/ ") and pat.strip("*/ ") in ed):
                hits.append((ed, pat))
                break
    return hits


def _effective_grade(spec: dict, root) -> str:
    """Grade drives enforcement depth. Read it from the scaffold-written
    `.forge/GRADE` (authoritative) so a model cannot silently downgrade in spec.json
    to skip checks. Falls back to spec.grade only when no GRADE file exists."""
    if root is not None:
        gf = Path(root) / FORGE_DIR / "GRADE"
        if gf.exists():
            try:
                g = gf.read_text(encoding="utf-8").strip().upper()
                if g in ("LIGHT", "STANDARD", "HEAVY"):
                    return g
            except Exception:
                pass
    return (spec.get("grade") or "STANDARD").upper()


# ---------------------------------------------------------------- spec gate ---
def gate_spec(spec: dict, root=None) -> list[str]:
    """Grade-tiered. LIGHT pays almost nothing (token lever); STANDARD adds the
    core decision artifacts; HEAVY enforces the full Fable depth. `root` (when
    given) lets must_read paths be checked for real existence."""
    grade = _effective_grade(spec, root)
    e: list[str] = []

    # ---- ALL grades: minimal viable spec ----
    rg, raw = spec.get("restated_goal", ""), spec.get("raw_goal", "")
    if not _nonempty(rg):
        e.append("restated_goal is empty — restate intent as 'achieve X without Y, scoped to Z'.")
    elif _norm(rg) == _norm(raw) and _nonempty(raw):
        e.append("restated_goal is identical to the raw ask — you under-interpreted; normalize it.")

    good_acc = [c for c in spec.get("acceptance_criteria", [])
                if isinstance(c, dict) and _nonempty((c.get("verify") or {}).get("value"))]
    if not good_acc:
        e.append("acceptance_criteria needs >=1 entry with a runnable command/check in verify.value (not prose).")
    for i, c in enumerate(spec.get("acceptance_criteria", [])):
        if isinstance(c, dict):
            vt = ((c.get("verify") or {}).get("type") or "").strip().lower()
            if vt and vt not in ACC_TYPES:
                e.append(f"acceptance_criteria[{i}].verify.type '{vt}' not in {sorted(ACC_TYPES)}.")

    if grade == "LIGHT":
        return e

    # ---- STANDARD and HEAVY ----
    if not [x for x in spec.get("non_goals", []) if _nonempty(x)]:
        e.append("non_goals is empty — fence the over-broad version you are NOT doing.")

    for i, a in enumerate(spec.get("ambiguities", [])):
        if not isinstance(a, dict):
            e.append(f"ambiguities[{i}] must be an object {{question,resolution,authority}}.")
        elif not (_nonempty(a.get("question")) and _nonempty(a.get("resolution")) and _nonempty(a.get("authority"))):
            e.append(f"ambiguities[{i}] needs question + resolution + the authority that resolved it.")

    mr = [m for m in spec.get("must_read", [])
          if isinstance(m, dict) and _nonempty(m.get("path")) and _nonempty(m.get("authority_reason"))]
    if not mr:
        e.append("must_read needs >=1 file justified by authority (a contract/boundary it owns).")
    if root is not None:
        for i, m in enumerate(spec.get("must_read", [])):
            if isinstance(m, dict) and _nonempty(m.get("path")) and not m.get("external"):
                if not (Path(root) / m["path"]).exists():
                    e.append(f"must_read[{i}] path '{m['path']}' not found under root — read a real file or set external:true.")

    good_alts = []
    for i, a in enumerate(spec.get("rejected_alternatives", [])):
        if not isinstance(a, dict):
            e.append(f"rejected_alternatives[{i}] must be an object.")
            continue
        # The Fable pattern is "name a category + the boundary it breaks" — the
        # taxonomy is descriptive, not prescriptive. Require a non-empty category
        # (recommend the canonical four) but don't reject a valid label we didn't
        # enumerate; the broken_boundary is what carries the reasoning.
        cat = (a.get("category") or "").strip()
        if not cat:
            e.append(f"rejected_alternatives[{i}] needs a category (recommended: {sorted(ALT_CATEGORIES)}).")
        if _nonempty(a.get("alternative")) and _nonempty(a.get("broken_boundary")) and cat:
            good_alts.append(a)
    if len(good_alts) < 2:
        e.append("need >=2 rejected_alternatives, each with a valid category + the broken boundary it violates.")

    for i, r in enumerate(spec.get("risks", [])):
        if not isinstance(r, dict):
            e.append(f"risks[{i}] must be an object.")
            continue
        sev = (r.get("severity") or "").strip().lower()
        if not sev:
            e.append(f"risks[{i}] needs a severity ({sorted(SEVERITIES)}) — rate by blast radius, not effort.")
        elif sev not in SEVERITIES:
            e.append(f"risks[{i}].severity '{sev}' not in {sorted(SEVERITIES)}.")
        if not _nonempty(r.get("mitigation")):
            e.append(f"risks[{i}] needs a runnable mitigation, not 'be careful'.")
        if sev in {"high", "blocking"} and not _nonempty(r.get("acceptance_ref")):
            e.append(f"risks[{i}] is {sev} — mirror it into an acceptance criterion (acceptance_ref).")

    # STANDARD anchor: the cheapest constraint — what must NOT change. Without it,
    # later risk/alternative/acceptance decisions have nothing to anchor on.
    if not [x for x in ((spec.get("constraints") or {}).get("invariant") or []) if _nonempty(_inv_text(x))]:
        e.append("constraints.invariant needs >=1 — what must NOT change "
                 "(don't delete prior work / don't leak / don't weaken a check).")

    if grade != "HEAVY":
        return e

    # ---- HEAVY only: full Fable depth (constraint provenance, mirror, validation) ----
    cons = spec.get("constraints") or {}
    arch = cons.get("architectural") or []
    if not arch:
        e.append("HEAVY: constraints.architectural needs >=1 {constraint, evidence_ref}.")
    for i, c in enumerate(arch):
        if not (isinstance(c, dict) and _nonempty(c.get("constraint")) and _nonempty(c.get("evidence_ref"))):
            e.append(f"HEAVY: constraints.architectural[{i}] must be {{constraint, evidence_ref}} — pin what proved it.")

    si = [s for s in spec.get("similar_implementations", [])
          if isinstance(s, dict) and _nonempty(s.get("path")) and _nonempty(s.get("why"))]
    if not si:
        e.append("HEAVY: similar_implementations needs >=1 {path, why} to mirror — avoid breaking an invariant.")

    return e


# ---------------------------------------------------------------- done gate ---
def gate_done(spec: dict, root=None) -> list[str]:
    grade = _effective_grade(spec, root)
    e = gate_spec(spec, root)  # done implies spec still valid
    acc = [c for c in spec.get("acceptance_criteria", []) if isinstance(c, dict)]
    if not acc:
        e.append("no acceptance_criteria to verify.")
    for i, c in enumerate(acc):
        ev = c.get("evidence")
        if not _nonempty(ev):
            e.append(f"acceptance_criteria[{i}] has no evidence — run the check and cite live output (fail closed).")
        elif not c.get("deferred"):
            hit = next((m for m in FAKE_MARKERS if m in ev.lower()), None)
            if hit:
                e.append(f"acceptance_criteria[{i}] evidence reads as unfilled/fabricated ('{hit}') — "
                         "run it for real, or mark the criterion deferred with a handoff.")
    for ed, pat in _forbidden_hits(spec, root):
        e.append(f"edited '{ed}' which matches forbidden_paths '{pat}' — architecture/policy "
                 "conflict; revert that change or, if it is genuinely required, justify it by "
                 "moving the path out of forbidden_paths with a reason.")
    if grade == "HEAVY":
        good_obs = [o for o in spec.get("observations", [])
                    if isinstance(o, dict) and _nonempty(o.get("observation"))]
        if not good_obs:
            e.append("HEAVY: validation loop unrecorded — log >=1 observation (what a read revealed, "
                     "with changed_understanding + evidence_ref) so decisions trace to evidence.")
    return e


# ----------------------------------------------------------------- commands ---
def cmd_scaffold(args) -> int:
    root = Path(args.root).resolve()
    fdir = root / FORGE_DIR
    fdir.mkdir(parents=True, exist_ok=True)
    grade = (args.grade or _grade_for(args.goal or "")).upper()
    sp = spec_path(root)
    if not sp.exists():
        spec = dict(SPEC_TEMPLATE)
        spec["raw_goal"] = args.goal or ""
        spec["grade"] = grade
        sp.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    # Authoritative grade lock: the gate reads enforcement level from here, not from
    # spec.json — so a model can't silently downgrade HEAVY->LIGHT to skip checks.
    gf = fdir / "GRADE"
    if not gf.exists():
        gf.write_text(grade, encoding="utf-8")
    active_path(root).write_text(args.goal or "", encoding="utf-8")
    print(f"forge: task active at {fdir} (grade {gf.read_text(encoding='utf-8').strip()})")
    return 0


LIGHT_RE = re.compile(r"\b(typo|comment|rename|format|lint|bump|tweak|whitespace|"
                      r"docstring|wording|copy(?:edit)?)\b", re.I)
LIGHT_KO = ("오타", "주석", "포맷", "줄바꿈", "띄어쓰기", "문구", "오탈자")


def _grade_for(text: str) -> str:
    """Grade scales gate depth — the token lever. LIGHT tasks pay almost nothing;
    HEAVY (auth/payments/security) pay full enforcement, matching where Fable
    itself escalates."""
    if HEAVY_RE.search(text) or any(k in text for k in HEAVY_KO):
        return "HEAVY"
    if LIGHT_RE.search(text) or any(k in text for k in LIGHT_KO):
        return "LIGHT"
    return "STANDARD"


def cmd_validate(args) -> int:
    root = Path(args.root).resolve()
    spec, err = load_spec(root)
    if err:
        print(f"forge {args.gate} gate: BLOCKED\n  - {err}", file=sys.stderr)
        return 1
    errs = gate_spec(spec, root) if args.gate == "spec" else gate_done(spec, root)
    if errs:
        print(f"forge {args.gate} gate: BLOCKED ({len(errs)} unmet)", file=sys.stderr)
        for x in errs:
            print(f"  - {x}", file=sys.stderr)
        return 1
    print(f"forge {args.gate} gate: PASS")
    return 0


def cmd_active(args) -> int:
    return 0 if active_path(Path(args.root).resolve()).exists() else 1


def cmd_status(args) -> int:
    root = Path(args.root).resolve()
    if not active_path(root).exists():
        print("forge: no active task")
        return 0
    spec, err = load_spec(root)
    if err:
        print(f"forge: active task, spec error: {err}")
        return 0
    se = gate_spec(spec, root)
    print(f"forge: active | grade {spec.get('grade')} | phase {spec.get('phase')} | "
          f"spec gate {'PASS' if not se else f'BLOCKED ({len(se)})'}")
    return 0


def cmd_close(args) -> int:
    root = Path(args.root).resolve()
    spec, err = load_spec(root)
    if err:
        print(f"forge: cannot close — {err}", file=sys.stderr)
        return 1
    de = gate_done(spec, root)
    if de:
        forced = args.force and os.environ.get("FORGE_BYPASS") == "1"
        if not forced:
            print(f"forge: done gate BLOCKED ({len(de)}) — not closing:", file=sys.stderr)
            for x in de:
                print(f"  - {x}", file=sys.stderr)
            if args.force:
                print("  (refusing --force without FORGE_BYPASS=1 — forcing is an audited bypass)", file=sys.stderr)
            return 1
        print(f"forge: FORCED close past {len(de)} unmet done-gate item(s) via FORGE_BYPASS.", file=sys.stderr)
    ap = active_path(root)
    if ap.exists():
        ap.unlink()
    print("forge: task closed")
    return 0


def cmd_classify(args) -> int:
    t = args.text or ""
    if any(t.rstrip().endswith(s) for s in QUESTION_KO_ENDINGS):
        return 1  # question -> not work
    work = bool(WORK_RE.search(t)) or any(k in t for k in WORK_KO)
    return 0 if work else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="forge_gate")
    sub = p.add_subparsers(dest="cmd", required=True)

    sc = sub.add_parser("scaffold"); sc.add_argument("--root", required=True)
    sc.add_argument("--goal", default=""); sc.add_argument("--grade", default="")
    sc.set_defaults(fn=cmd_scaffold)

    v = sub.add_parser("validate"); v.add_argument("--root", required=True)
    v.add_argument("--gate", choices=["spec", "done"], required=True)
    v.set_defaults(fn=cmd_validate)

    a = sub.add_parser("active"); a.add_argument("--root", required=True); a.set_defaults(fn=cmd_active)
    s = sub.add_parser("status"); s.add_argument("--root", required=True); s.set_defaults(fn=cmd_status)
    c = sub.add_parser("close"); c.add_argument("--root", required=True)
    c.add_argument("--force", action="store_true"); c.set_defaults(fn=cmd_close)
    cl = sub.add_parser("classify"); cl.add_argument("--text", default=""); cl.set_defaults(fn=cmd_classify)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except Exception as exc:
        # Enforcement commands fail CLOSED (a gate bug must not silently disable
        # enforcement); housekeeping commands fail open. The host-side hook keeps
        # its own crash guard so a gate bug can't brick the tool pipeline.
        fail_closed = getattr(args, "cmd", "") in ("validate", "close")
        kind = "failing closed" if fail_closed else "failing open"
        print(f"forge_gate internal error ({kind}): {exc}", file=sys.stderr)
        return 1 if fail_closed else 0


if __name__ == "__main__":
    raise SystemExit(main())
