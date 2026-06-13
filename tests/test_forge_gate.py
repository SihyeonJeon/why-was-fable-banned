"""Regression tests for the forge gate engine. Run: python3 -m unittest -q
(from ~/fable-forge) — stdlib only, no network, no fable-pack dependency."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gates"))
import forge_gate as fg  # noqa: E402


def spec(**over):
    base = {
        "grade": "STANDARD",
        "raw_goal": "add a GET /health endpoint",
        "restated_goal": "Add a GET /health endpoint without changing existing routes, scoped to real.py.",
        "non_goals": ["no auth changes"],
        "constraints": {"invariant": ["existing routes must keep working"]},
        "must_read": [{"path": "real.py", "authority_reason": "owns the routing table"}],
        "rejected_alternatives": [
            {"category": "scope", "alternative": "new framework", "broken_boundary": "over-broad, no consumer"},
            {"category": "tempting_shortcut", "alternative": "skip tests", "broken_boundary": "hides regressions"},
        ],
        "risks": [{"risk": "route clash", "severity": "medium", "mitigation": "grep routes first"}],
        "acceptance_criteria": [{"criterion": "200", "verify": {"type": "command", "value": "curl -sf localhost/health"}}],
    }
    base.update(over)
    return base


class GateSpec(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "real.py").write_text("x=1")

    def test_standard_valid_passes(self):
        self.assertEqual(fg.gate_spec(spec(), self.d), [])

    def test_light_minimal_passes(self):
        s = {"grade": "LIGHT", "raw_goal": "fix typo",
             "restated_goal": "Correct 'recieve' spelling without touching surrounding copy.",
             "acceptance_criteria": [{"criterion": "fixed", "verify": {"type": "grep", "value": "! grep -q recieve f"}}]}
        self.assertEqual(fg.gate_spec(s, self.d), [])

    def test_restated_equal_raw_blocks(self):
        e = fg.gate_spec(spec(restated_goal=spec()["raw_goal"]), self.d)
        self.assertTrue(any("identical to the raw ask" in x for x in e))

    def test_missing_invariant_blocks(self):
        e = fg.gate_spec(spec(constraints={"invariant": []}), self.d)
        self.assertTrue(any("constraints.invariant" in x for x in e))

    def test_nonexistent_must_read_blocks(self):
        e = fg.gate_spec(spec(must_read=[{"path": "ghost.py", "authority_reason": "x"}]), self.d)
        self.assertTrue(any("not found under root" in x for x in e))

    def test_external_must_read_allowed(self):
        s = spec(must_read=[{"path": "/etc/hosts", "authority_reason": "x", "external": True}])
        self.assertEqual(fg.gate_spec(s, self.d), [])

    def test_one_rejected_alt_blocks_standard(self):
        e = fg.gate_spec(spec(rejected_alternatives=[
            {"category": "scope", "alternative": "a", "broken_boundary": "b"}]), self.d)
        self.assertTrue(any("rejected_alternatives" in x for x in e))

    def test_noncanonical_category_accepted(self):
        # the taxonomy is descriptive; a sensible label we didn't enumerate must pass
        s = spec(rejected_alternatives=[
            {"category": "dependency", "alternative": "add lib X", "broken_boundary": "new dep, no consumer"},
            {"category": "performance", "alternative": "cache all", "broken_boundary": "premature, no measured need"}])
        self.assertEqual(fg.gate_spec(s, self.d), [])

    def test_empty_category_blocks(self):
        e = fg.gate_spec(spec(rejected_alternatives=[
            {"category": "", "alternative": "a", "broken_boundary": "b"},
            {"category": "scope", "alternative": "c", "broken_boundary": "d"}]), self.d)
        self.assertTrue(any("needs a category" in x for x in e))

    def test_risk_without_severity_blocks(self):
        e = fg.gate_spec(spec(risks=[{"risk": "x", "mitigation": "y"}]), self.d)
        self.assertTrue(any("needs a severity" in x for x in e))

    def test_high_risk_needs_mirror(self):
        e = fg.gate_spec(spec(risks=[{"risk": "x", "severity": "high", "mitigation": "y"}]), self.d)
        self.assertTrue(any("acceptance_ref" in x for x in e))

    def test_heavy_requires_arch_evidence_and_similar(self):
        e = fg.gate_spec(spec(grade="HEAVY"), self.d)
        self.assertTrue(any("architectural" in x for x in e))
        self.assertTrue(any("similar_implementations" in x for x in e))

    def test_bad_acceptance_type_blocks(self):
        s = spec()
        s["acceptance_criteria"][0]["verify"]["type"] = "vibes"
        self.assertTrue(any("verify.type" in x for x in fg.gate_spec(s, self.d)))


class GateDone(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "real.py").write_text("x=1")

    def test_no_evidence_blocks(self):
        self.assertTrue(any("no evidence" in x for x in fg.gate_done(spec(), self.d)))

    def test_fake_evidence_blocks(self):
        s = spec()
        s["acceptance_criteria"][0]["evidence"] = "assumed it would pass"
        self.assertTrue(any("fabricated" in x for x in fg.gate_done(s, self.d)))

    def test_real_evidence_passes(self):
        s = spec()
        s["acceptance_criteria"][0]["evidence"] = "curl -> HTTP 200 OK"
        self.assertEqual(fg.gate_done(s, self.d), [])

    def test_deferred_criterion_skips_fake_check(self):
        s = spec()
        s["acceptance_criteria"][0]["evidence"] = "pending human deploy"
        s["acceptance_criteria"][0]["deferred"] = True
        self.assertEqual(fg.gate_done(s, self.d), [])

    def test_forbidden_path_edit_blocks_done(self):
        (self.d / ".forge").mkdir(exist_ok=True)
        (self.d / ".forge" / "edits.txt").write_text("config/policy.py\nsrc/main.py\n")
        s = spec(forbidden_paths=["config/*"])
        s["acceptance_criteria"][0]["evidence"] = "ran OK"
        self.assertTrue(any("forbidden_paths" in x for x in fg.gate_done(s, self.d)))

    def test_no_forbidden_edit_passes(self):
        (self.d / ".forge").mkdir(exist_ok=True)
        (self.d / ".forge" / "edits.txt").write_text("src/main.py\n")
        s = spec(forbidden_paths=["config/*"])
        s["acceptance_criteria"][0]["evidence"] = "ran OK"
        self.assertEqual(fg.gate_done(s, self.d), [])

    def test_heavy_requires_observation(self):
        s = spec(grade="HEAVY")
        s["constraints"] = {"invariant": ["x"], "architectural": [{"constraint": "c", "evidence_ref": "real.py"}]}
        s["similar_implementations"] = [{"path": "real.py", "why": "mirror"}]
        s["acceptance_criteria"][0]["evidence"] = "ran OK"
        self.assertTrue(any("validation loop" in x for x in fg.gate_done(s, self.d)))
        s["observations"] = [{"observation": "real.py defines routes via a dict", "changed_understanding": True}]
        self.assertEqual(fg.gate_done(s, self.d), [])


class Adversarial(unittest.TestCase):
    """Try to break or game the gate; verify it holds (and document inherent limits)."""
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "real.py").write_text("x=1")

    def _scaffold(self, goal):
        fg.cmd_scaffold(type("A", (), {"root": str(self.d), "goal": goal, "grade": ""})())

    def _load(self):
        return json.loads((self.d / ".forge" / "spec.json").read_text())

    def test_grade_lock_blocks_silent_downgrade(self):
        # HEAVY task auto-graded + locked in .forge/GRADE
        self._scaffold("secure auth token migration for payments")
        self.assertEqual((self.d / ".forge" / "GRADE").read_text().strip(), "HEAVY")
        # attacker rewrites spec.json claiming LIGHT + minimal fields
        s = self._load()
        s["grade"] = "LIGHT"
        s["restated_goal"] = "Migrate auth tokens without dropping sessions, scoped to auth.py."
        s["acceptance_criteria"] = [{"criterion": "ok", "verify": {"type": "command", "value": "pytest"}}]
        e = fg.gate_spec(s, self.d)
        # HEAVY is still enforced (GRADE file wins): many unmet items, not a LIGHT pass
        self.assertGreaterEqual(len(e), 4, e)

    def test_nondict_spec_blocked(self):
        (self.d / ".forge").mkdir(exist_ok=True)
        (self.d / ".forge" / "spec.json").write_text("[1,2,3]")
        rc = fg.cmd_validate(type("A", (), {"root": str(self.d), "gate": "spec"})())
        self.assertEqual(rc, 1)

    def test_garbage_json_blocked(self):
        (self.d / ".forge").mkdir(exist_ok=True)
        (self.d / ".forge" / "spec.json").write_text("{ not json at all ")
        rc = fg.cmd_validate(type("A", (), {"root": str(self.d), "gate": "spec"})())
        self.assertEqual(rc, 1)

    def test_internal_error_fails_closed(self):
        # main() wraps gate calls; a non-dict spec slipping past would fail CLOSED (rc 1)
        rc = fg.main(["validate", "--root", str(self.d), "--gate", "spec"])
        self.assertEqual(rc, 1)  # no spec file -> blocked

    def test_KNOWN_LIMIT_trivial_command_passes(self):
        # DOCUMENTED inherent limit: the gate checks FORM, not SEMANTICS. A trivially
        # passing command ('true') is "runnable", so it passes. Catching this needs the
        # optional judge layer, not the deterministic gate. Asserted so the limit is explicit.
        s = spec()
        s["acceptance_criteria"] = [{"criterion": "ok", "verify": {"type": "command", "value": "true"}}]
        self.assertEqual(fg.gate_spec(s, self.d), [])

    def test_KNOWN_LIMIT_shallow_but_wellformed_passes(self):
        # low-effort-but-structurally-valid rejected_alternatives pass (form, not depth)
        s = spec(rejected_alternatives=[
            {"category": "scope", "alternative": "x", "broken_boundary": "y"},
            {"category": "scope", "alternative": "a", "broken_boundary": "b"}])
        self.assertEqual(fg.gate_spec(s, self.d), [])


class FableMethod(unittest.TestCase):
    """Verify the gate enforces each axis of the Fable decision pattern: removing the
    element for that axis must make the gate block."""
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "real.py").write_text("x=1")

    def _blocks_when(self, **drop):
        s = spec(**drop)
        return fg.gate_spec(s, self.d)

    def test_axis_goal_interpretation(self):           # restated_goal == raw -> block
        self.assertTrue(self._blocks_when(restated_goal=spec()["raw_goal"]))

    def test_axis_scope_by_negation(self):             # non_goals empty -> block
        self.assertTrue(self._blocks_when(non_goals=[]))

    def test_axis_context_by_authority(self):          # must_read missing -> block
        self.assertTrue(self._blocks_when(must_read=[]))

    def test_axis_alternative_analysis(self):          # <2 rejected -> block
        self.assertTrue(self._blocks_when(rejected_alternatives=[]))

    def test_axis_constraint_extraction(self):         # no invariant -> block
        self.assertTrue(self._blocks_when(constraints={"invariant": []}))

    def test_axis_risk_reasoning(self):                # risk without severity -> block
        self.assertTrue(self._blocks_when(risks=[{"risk": "x", "mitigation": "y"}]))

    def test_axis_acceptance_design(self):             # no runnable acceptance -> block
        self.assertTrue(self._blocks_when(acceptance_criteria=[{"criterion": "x"}]))


class Classify(unittest.TestCase):
    def test_work_vs_question(self):
        self.assertEqual(fg.cmd_classify(type("A", (), {"text": "fix the auth bug"})), 0)
        self.assertEqual(fg.cmd_classify(type("A", (), {"text": "이거 어떻게 동작하나요?"})), 1)

    def test_grade_for(self):
        self.assertEqual(fg._grade_for("fix payment auth token"), "HEAVY")
        self.assertEqual(fg._grade_for("fix a typo in the comment"), "LIGHT")
        self.assertEqual(fg._grade_for("add a sort function"), "STANDARD")


if __name__ == "__main__":
    unittest.main()
