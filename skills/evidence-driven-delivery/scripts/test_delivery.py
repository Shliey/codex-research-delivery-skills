"""Portable regression/integration suite; all generated projects use temp dirs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("edd_runtime", SKILL / "scripts" / "delivery.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def event(name, status="completed", readiness="READY", details=""):
    return {"status": status, "readiness": readiness, "event": name, "details": details}


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="edd-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "AGENTS.md").write_text("# Existing rules\nPreserve this instruction.\n", encoding="utf-8")
        self.c = runtime.Controller(self.root)
        self.c.init()
        p = self.c.project()
        p["commands"] = {"test": {"argv": [sys.executable, "-c", "print('verified')"], "required": True}}
        runtime.write(self.root / ".workflow" / "project.json", p)
        self.c.start("Implement bounded behavior", scope="bounded", mode="light",
                     authorization={"source": "human:test", "scope": "bounded", "actions": ["implement"]})

    def fixture_contract(self):
        (self.root / "acceptance.md").write_text("### Requirement: Valid output\n#### Scenario: Success\n", encoding="utf-8")
        return {"tasks": {"T1": {"writes": ["implementation.py"], "depends": []}},
                "scenarios": [{"id": "S1", "requirement": "Valid output", "source": "acceptance.md",
                               "heading": "#### Scenario: Success", "tasks": ["T1"], "checks": ["test"]}]}

    def ready(self):
        self.c.bind(self.fixture_contract())
        self.c.step(event("LIGHT_READY"))
        self.c.review("design", [], "test review of fixture")
        self.c.step(event("READY"))
        self.c.review("planning", [], "test planning of fixture")
        self.c.step(event("DELIVERY_READY"))
        self.c.step(event("AUTHORIZED"))

    def test_init_idempotent_and_override_preserved(self):
        self.c.init()
        text = (self.root / "AGENTS.md").read_text()
        self.assertEqual(text.count("<!-- evidence-driven-delivery:start -->"), 1)
        self.assertIn("Preserve this instruction", text)
        self.assertIn("test", self.c.project()["commands"])
        self.assertTrue(self.c.doctor()["ok"])

    def test_single_copy_contains_all_references(self):
        for doc in [SKILL / "SKILL.md", *SKILL.glob("references/*.md")]:
            for target in re.findall(r"\]\(([^)]+)\)", doc.read_text(encoding="utf-8")):
                if not target.startswith("https:"):
                    self.assertTrue((doc.parent / target).is_file(), target)
        for name in ("workflow.json", "policy.json", "skill-result.schema.json", "run-state.schema.json"):
            runtime.read(SKILL / "assets" / name)

    def test_read_only_request_writes_nothing(self):
        root = self.root / "untouched"
        root.mkdir()
        before = list(root.iterdir())
        result = runtime.Controller(root).start("Review only", review_only=True)
        self.assertEqual(result["state"], "OBSERVATIONAL")
        self.assertEqual(list(root.iterdir()), before)

    def test_existing_issue_and_change_and_run_entries(self):
        c = runtime.Controller(self.root)
        issue = c.start("Existing issue", issue=".workflow/issues/I1.md")
        self.assertEqual(issue["state"], "CHANGE_PLANNING")
        c2 = runtime.Controller(self.root)
        same = c2.start("Different wording", issue=".workflow/issues/I1.md")
        self.assertEqual(issue["id"], same["id"])
        changed = c.start("Existing change", change="fix-parser")
        self.assertEqual(changed["state"], "DESIGN_REVIEW")

    def test_unknown_event_is_diagnostic_and_resumable(self):
        result = self.c.step(event("TYPO_EVENT"))
        self.assertEqual(result["state"], "ERROR")
        self.assertIn("TYPO_EVENT", result["diagnostic"])
        self.assertEqual(self.c.resume()["state"], "INTAKE")

    def test_three_repairs_then_pause(self):
        self.c.step(event("LIGHT_READY"))
        for _ in range(3):
            self.assertEqual(self.c.step(event("AUTO_FIXABLE", details="missing-error-path"))["state"], "DESIGN_REPAIR")
            self.c.step(event("UPDATED"))
        result = self.c.step(event("AUTO_FIXABLE", details="missing-error-path"))
        self.assertEqual(result["state"], "PAUSED")
        self.assertEqual(result["resumeState"], "DESIGN_REVIEW")
        self.assertTrue((self.c.folder / "handoff.md").is_file())

    def test_decision_resumes_and_invalidates_on_changes(self):
        (self.root / "scope.md").write_text("original")
        d = self.c.request_decision("Allow endpoint?", "deploy", ["scope.md"], ["yes", "no"])
        with self.assertRaises(ValueError):
            self.c.resume()
        self.assertEqual(self.c.decide(d["id"], "yes", "human:reply")["state"], "INTAKE")
        self.assertTrue(self.c.authorized(self.c.load(), "deploy"))
        (self.root / "scope.md").write_text("changed")
        self.assertFalse(self.c.authorized(self.c.load(), "deploy"))

    def test_stale_pending_decision_replace(self):
        (self.root / "scope.md").write_text("a")
        d = self.c.request_decision("Choose behavior", "scope_change", ["scope.md"], ["a", "b"])
        (self.root / "scope.md").write_text("b")
        with self.assertRaises(ValueError):
            self.c.decide(d["id"], "a", "human:old-answer")
        self.c.replace_decision(d["id"])
        new = self.c.request_decision("Choose updated behavior", "scope_change", ["scope.md"], ["a", "b"])
        self.assertNotEqual(d["id"], new["id"])

    def test_crash_after_write_reconciles_without_replay(self):
        self.assertTrue(self.c.begin("create-issue", ["issue.md"])["replay"])
        (self.root / "issue.md").write_text("created once")
        c = runtime.Controller(self.root, self.c.run)
        self.assertFalse(c.begin("create-issue", ["issue.md"])["replay"])
        expected = hashlib.sha256((self.root / "issue.md").read_bytes()).hexdigest()
        c.reconcile("create-issue", {"issue.md": expected})
        self.assertEqual(c.load()["operations"]["create-issue"]["state"], "complete")
        self.assertEqual((self.root / "issue.md").read_text(), "created once")

    def test_operation_and_process_single_writer(self):
        self.c.begin("one", ["one.md"])
        with self.assertRaises(ValueError):
            self.c.begin("two", ["two.md"])
        with self.c.locked():
            with self.assertRaises(ValueError):
                self.c.resume()

    def test_evidence_changes_and_log_tampering(self):
        self.ready()
        self.c.step(event("IMPLEMENTATION_COMPLETE"))
        self.assertEqual(self.c.check("test")["exitCode"], 0)
        self.c.finish_task("T1")
        self.c.review("semantic", [], "checked implementation and scope")
        self.assertTrue(self.c.evidence_status()["ok"])
        log = self.root / self.c.load()["evidence"][-1]["log"]
        log.write_text("tampered")
        self.assertFalse(self.c.evidence_status()["ok"])
        self.c.check("test")
        self.c.finish_task("T1")
        self.c.review("semantic", [], "checked again")
        self.assertTrue(self.c.evidence_status()["ok"])
        (self.root / "implementation.py").write_text("print('changed')")
        self.assertFalse(self.c.evidence_status()["ok"])
        with self.assertRaises(ValueError):
            self.c.step(event("VERIFIED"))

    def test_auth_cannot_follow_changed_scope(self):
        state = self.c.load()
        state["scope"] = "expanded"
        self.assertFalse(self.c.authorized(state, "implement"))

    def test_dependency_cycle_rejected(self):
        contract = self.fixture_contract()
        contract["tasks"]["T1"]["depends"] = ["T1"]
        with self.assertRaises(ValueError):
            self.c.bind(contract)

    def test_wait_cancel_and_light_completion(self):
        self.c.step(event("WAIT", status="blocked", readiness="NOT_READY", details="tool unavailable"))
        self.assertEqual(self.c.resume()["state"], "INTAKE")
        self.ready()
        self.c.step(event("IMPLEMENTATION_COMPLETE"))
        self.c.check("test")
        self.c.finish_task("T1")
        self.c.review("semantic", [], "review fixture")
        self.c.step(event("VERIFIED"))
        self.assertEqual(self.c.step(event("LIGHT_COMPLETE"))["state"], "COMPLETED")

    def test_cancel_is_distinct_and_terminal_immutable(self):
        self.assertEqual(self.c.step(event("CANCEL"))["state"], "CANCELLED")
        with self.assertRaises(ValueError):
            self.c.resume()

    def test_implementation_failure_returns_to_bounded_repair(self):
        self.ready()
        for _ in range(3):
            self.assertEqual(self.c.step(event("REPAIRABLE_FAILURE", status="failed", readiness="NOT_READY", details="unit:case-1"))["state"], "IMPLEMENTING")
        self.assertEqual(self.c.step(event("REPAIRABLE_FAILURE", status="failed", readiness="NOT_READY", details="unit:case-1"))["state"], "PAUSED")

    def test_policy_change_invalidates_implementation_grant(self):
        self.assertTrue(self.c.authorized(self.c.load(), "implement"))
        policy = self.c.policy()
        policy["approvalRequired"].append("additional-action")
        runtime.write(self.c.control / "policy.json", policy)
        self.assertFalse(self.c.authorized(self.c.load(), "implement"))

    def test_schema_rejects_extra_fields_and_wrong_types(self):
        malformed = event("LIGHT_READY")
        malformed["evidence"] = "not-an-array"
        self.assertEqual(self.c.step(malformed)["state"], "ERROR")

    def test_design_edit_invalidates_review(self):
        self.c.bind(self.fixture_contract())
        self.c.step(event("LIGHT_READY"))
        self.c.review("design", [], "reviewed")
        (self.root / "design.md").write_text("new decision")
        with self.assertRaises(ValueError):
            self.c.step(event("READY"))

    def test_failed_command_never_verifies(self):
        self.ready()
        project = self.c.project()
        project["commands"]["test"]["argv"] = [sys.executable, "-c", "raise SystemExit(1)"]
        runtime.write(self.c.control / "project.json", project)
        self.assertEqual(self.c.check("test")["exitCode"], 1)
        with self.assertRaises(ValueError):
            self.c.finish_task("T1")

    def test_no_verifier_is_a_completion_blocker(self):
        project = self.c.project()
        project["commands"] = {}
        runtime.write(self.c.control / "project.json", project)
        self.assertFalse(self.c.evidence_status()["ok"])

    def test_doctor_reports_bad_transition_target(self):
        wf = self.c.workflow()
        wf["states"]["INTAKE"]["events"]["BAD"] = "DOES_NOT_EXIST"
        runtime.write(self.c.control / "workflow.json", wf)
        self.assertFalse(self.c.doctor()["ok"])

    def test_relative_escape_and_external_write_denied(self):
        with self.assertRaises(ValueError):
            self.c.begin("bad-path", ["../outside.txt"])
        with self.assertRaises(ValueError):
            self.c.begin("remote", ["receipt.json"], action="external_write")

    def test_export_excludes_target_state_and_runs(self):
        output = self.root / "skill.zip"
        runtime.package_skill(output)
        with runtime.zipfile.ZipFile(output) as archive:
            names = archive.namelist()
            self.assertIn("evidence-driven-delivery/SKILL.md", names)
            self.assertFalse(any("__pycache__" in n or "/.workflow/" in n for n in names))

    def test_state_schema_and_event_projection_recovery(self):
        runtime.validate(self.c.load(), runtime.read(self.c.control / "run-state.schema.json"))
        (self.c.folder / "events.jsonl").write_text("interrupted")
        self.c.resume()
        events = [json.loads(line) for line in (self.c.folder / "events.jsonl").read_text().splitlines()]
        self.assertEqual(events, self.c.load()["history"])


@unittest.skipUnless(shutil.which("openspec"), "OpenSpec CLI required for full integration")
class IntegrationTests(unittest.TestCase):
    def run_delivery(self, stack):
        with tempfile.TemporaryDirectory(prefix="edd-" + stack + "-") as temp:
            root = Path(temp)
            package = root / ".agents" / "skills" / "evidence-driven-delivery"
            shutil.copytree(SKILL, package, ignore=shutil.ignore_patterns("__pycache__"))
            module_spec = importlib.util.spec_from_file_location("isolated_" + stack, package / "scripts" / "delivery.py")
            mod = importlib.util.module_from_spec(module_spec)
            module_spec.loader.exec_module(mod)
            self.assertEqual(mod.ASSETS, package / "assets")
            (root / "tests").mkdir()
            (root / "AGENTS.md").write_text("# Target rules\nKeep local conventions.\n")
            if stack == "typescript":
                runtime.write(root / "package.json", {"type": "module", "scripts": {"test": "node --test tests/parser.test.ts"}})
                runtime.write(root / "tsconfig.json", {"compilerOptions": {"strict": True}})
                code = root / "parser.ts"
                code.write_text("export function parse(value: string): number { return Number(value); }\n")
            else:
                (root / "pyproject.toml").write_text('[project]\nname="demo"\nversion="0.0.0"\n')
                code = root / "parser.py"
                code.write_text("def parse(value):\n    return float(value)\n")
            c = mod.Controller(root)
            self.assertTrue(c.init()["ok"])
            self.assertIn(stack, c.project()["stacks"])
            def command(argv):
                r = mod.argv_run(argv, root)
                self.assertEqual(r["exitCode"], 0, r["output"])
                return r
            command(["openspec", "init", "--tools", "none", "--no-copilot-cloud", "--no-animation"])
            c.start("Reject invalid numeric input", scope="Reject invalid input; retain numeric conversion", mode="full",
                    authorization={"source": "integration:human-goal", "scope": "Reject invalid input; retain numeric conversion", "actions": ["implement"]})
            issue = ".workflow/issues/I-001.md"
            (root / issue).parent.mkdir(parents=True, exist_ok=True)
            c.begin("create-issue", [issue])
            (root / issue).write_text("# I-001 Reject invalid input\nWhy now: NaN leaks.\nScope: numeric input validation.\nNon-goals: new formats.\nAcceptance: valid numbers pass; invalid values fail clearly.\n")
            c.complete("create-issue")
            c.step(event("ISSUE_READY"))
            change = "reject-invalid"
            command(["openspec", "new", "change", change, "--json"])
            folder = root / "openspec" / "changes" / change
            (folder / "proposal.md").write_text("## Why\nInvalid input leaks invalid numbers. Source: I-001.\n## What Changes\nReject invalid numeric input.\n## Capabilities\n### New Capabilities\n- `numeric-input`: clear validation.\n## Impact\nLocal parser only.\n")
            (folder / "design.md").write_text("## Context\nParser converts numbers.\n## Goals / Non-Goals\nValidate input; no new formats.\n## Decisions\nThrow a clear error for nonfinite input.\n## Risks / Trade-offs\nExisting valid values retain behavior.\n")
            specfile = folder / "specs" / "numeric-input" / "spec.md"
            specfile.parent.mkdir(parents=True)
            specfile.write_text("## Purpose\nProvide clear rejection of invalid numeric inputs while retaining valid numeric conversions.\n\n## ADDED Requirements\n\n### Requirement: Validate numeric input\nThe parser SHALL reject nonfinite inputs with a clear error and retain valid numbers.\n\n#### Scenario: Valid input\n- **WHEN** the input is 42\n- **THEN** the result is 42\n\n#### Scenario: Invalid input\n- **WHEN** the input is invalid\n- **THEN** an Invalid numeric input error is raised\n")
            tasks = folder / "tasks.md"
            tasks.write_text("## 1. Parser\n- [ ] 1.1 Validate values and verify valid and invalid test cases.\n")
            c.step(event("CHANGE_REVIEWABLE"))
            check = "test" if stack == "typescript" else "python-test"
            contract = {"tasks": {"T1": {"writes": [code.name, "tests"], "depends": []}}, "scenarios": [
                {"id": name, "requirement": "Validate numeric input", "source": specfile.relative_to(root).as_posix(),
                 "heading": "#### Scenario: " + heading, "tasks": ["T1"], "checks": [check]}
                for name, heading in [("S1", "Valid input"), ("S2", "Invalid input")]]}
            c.bind(contract, issue=issue, change=change)
            c.review("design", [], "integration semantic review of complete artifacts")
            c.step(event("READY"))
            c.review("planning", [], "T1 owns parser and tests; two scenarios covered")
            c.step(event("DELIVERY_READY"))
            c.step(event("AUTHORIZED"))
            c.begin("implement-T1", [code.name])
            if stack == "typescript":
                code.write_text("export function parse(value: string): number {\n const n = Number(value);\n if (!Number.isFinite(n)) throw new Error('Invalid numeric input');\n return n;\n}\n")
                (root / "tests" / "parser.test.ts").write_text("import {test} from 'node:test';\nimport assert from 'node:assert/strict';\nimport {parse} from '../parser.ts';\ntest('valid',()=>assert.equal(parse('42'),42));\ntest('invalid',()=>assert.throws(()=>parse('bad'),/Invalid numeric input/));\n")
            else:
                code.write_text("import math\ndef parse(value):\n    try:\n        n = float(value)\n    except (ValueError, TypeError):\n        raise ValueError('Invalid numeric input') from None\n    if not math.isfinite(n):\n        raise ValueError('Invalid numeric input')\n    return n\n")
                (root / "tests" / "test_parser.py").write_text("import unittest\nfrom parser import parse\nclass ParserTest(unittest.TestCase):\n    def test_valid(self):\n        self.assertEqual(parse('42'), 42)\n    def test_invalid(self):\n        with self.assertRaisesRegex(ValueError, 'Invalid numeric input'):\n            parse('bad')\n")
            c.complete("implement-T1")
            tasks.write_text(tasks.read_text().replace("[ ]", "[x]"))
            c.step(event("IMPLEMENTATION_COMPLETE"))
            self.assertEqual(c.check(check)["exitCode"], 0)
            c.finish_task("T1")
            command(["openspec", "validate", change, "--strict", "--no-interactive"])
            c.review("semantic", [], "valid/invalid scenarios reviewed against parser, tests, non-goals and diff")
            self.assertTrue(c.evidence_status()["ok"])
            c.step(event("VERIFIED"))
            c.step(event("LOCAL_COMPLETE"))
            main = "openspec/specs/numeric-input/spec.md"
            # CLI archive combines actual synchronization and moving. Capture
            # both postconditions once and adopt the archived artifact below.
            c.begin("synced", [main, "openspec/changes/reject-invalid/proposal.md"])
            command(["openspec", "archive", change, "--yes", "--json"])
            self.assertIn("### Requirement: Validate numeric input", (root / main).read_text())
            archived = list((root / "openspec" / "changes" / "archive").glob("*-reject-invalid/proposal.md"))
            self.assertEqual(len(archived), 1)
            c.complete("synced")
            c.step(event("SYNCED"))
            archived_path = archived[0].relative_to(root).as_posix()
            c.begin("archived", [archived_path, main])
            c.complete("archived")
            self.assertEqual(c.step(event("ARCHIVED"))["state"], "ARCHIVED")
            self.assertEqual(len(c.load()["decisions"]), 0)
            print("INTEGRATION", stack, "ARCHIVED", "real tests + OpenSpec sync/archive", flush=True)

    @unittest.skipUnless(shutil.which("node") and shutil.which("npm"), "Node 22.18+/npm required")
    def test_typescript_full_delivery(self):
        self.run_delivery("typescript")

    def test_python_full_delivery(self):
        self.run_delivery("python")


if __name__ == "__main__":
    unittest.main(verbosity=2)
