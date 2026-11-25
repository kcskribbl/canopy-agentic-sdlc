import tempfile
import unittest
import json
import re
from pathlib import Path

import flow


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.db = flow.db_open(self.home)
        self.addCleanup(self.db.close)

    def staged(self, plan):
        run = plan["run"]
        prd = flow.approve_document(self.db, run, "approve-intent", plan["digest"], "Test intent review")
        return flow.approve_document(self.db, run, "approve-prd", prd["digest"], "Test PRD review")

    def test_requirements_lineage_and_separation(self):
        original = "Make short links safer"
        initial = flow.plan(self.db, "intake", original)
        with self.assertRaises(ValueError):
            flow.approve_document(self.db, "intake", "approve-intent", initial["digest"], "unresolved")
        draft = flow.plan(self.db, "intake", "Build a shortener with analytics", revise=True)
        self.assertEqual(["INTENT.md"], draft["documents"])
        with self.assertRaises(ValueError):
            flow.approve_document(self.db, "intake", "approve-intent", initial["digest"], "stale")
        prd = flow.approve_document(self.db, "intake", "approve-intent", draft["digest"], "Scope agreed")
        docs = json.loads(flow.current(self.db, "intake")["payload"])["documents"]
        self.assertIn(original, docs["INTENT.md"])
        self.assertIn("Build a shortener with analytics", docs["INTENT.md"])
        self.assertIn(draft["digest"], docs["PRD.md"])
        ids = re.findall(r"\*\*((?:FR|SEC|NFR|BR)-\d+)\*\*", docs["PRD.md"])
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue({"FR-001", "FR-003", "SEC-001", "SEC-002"} <= set(ids))
        for rid in ids:
            self.assertIn(f"- {rid}:", docs["PRD.md"])
        self.assertNotIn("SPEC.md", docs)
        with self.assertRaises(ValueError):
            flow.validate(self.db, "intake", prd["digest"])
        stage = flow.approve_document(self.db, "intake", "approve-prd", prd["digest"], "Test approval")
        self.assertIn("SPEC.md", stage["documents"])
        self.assertIn(flow.project.STATS, stage["proposed_files"])

    def test_revision_invalidates_approval_and_requires_human_acceptance(self):
        run = flow.plan(self.db, "links", "Make links safer")
        self.assertEqual("needs_clarification", run["state"])
        current = self.staged(flow.plan(self.db, "links", "Create short links", revise=True))
        with self.assertRaises(ValueError):
            flow.validate(self.db, "links", run["digest"])
        result = flow.validate(self.db, "links", current["digest"], lambda p: (True, "injected test result"))
        self.assertEqual("awaiting_acceptance", result["state"])
        self.assertEqual({}, flow.snapshot(self.db))
        flow.decide(self.db, "links", "accept", current["digest"], "synthetic reviewer")
        before = flow.snapshot(self.db)
        stats = self.staged(flow.plan(self.db, "stats", "Add analytics"))
        self.assertIn("inspect", stats["graph"])
        self.assertEqual([flow.project.STATS], stats["proposed_files"])
        flow.validate(self.db, "stats", stats["digest"], lambda p: (True, "synthetic"))
        flow.decide(self.db, "stats", "accept", stats["digest"], "synthetic reviewer")
        flow.decide(self.db, "stats", "rollback", stats["digest"], "synthetic rollback")
        self.assertEqual(before, flow.snapshot(self.db))

    def test_safe_stop_after_one_repair_and_no_partial_product(self):
        plan = self.staged(flow.plan(self.db, "r", "Create short links"))
        for i in range(2):
            if i:
                plan = self.staged(flow.plan(self.db, "r", "Create short links", revise=True))
            result = flow.validate(self.db, "r", plan["digest"], lambda p: (False, "injected failure"))
            self.assertEqual("safe_stop", result["state"])
        with self.assertRaisesRegex(ValueError, "exhausted"):
            flow.plan(self.db, "r", "Create short links", revise=True)
        self.assertEqual({}, flow.snapshot(self.db))

    def test_no_proposal_writes_to_trusted_tests_or_build(self):
        for index, path in enumerate(("../outside.java", "pom.xml", "src/test/java/Test.java")):
            with self.assertRaisesRegex(ValueError, "planned Java"):
                self.staged(flow.plan(self.db, f"invalid{index}", "Build short links", {path: "bad"}))

    def test_failed_or_missing_graph_dependency_cannot_be_joined(self):
        with self.assertRaisesRegex(ValueError, "no runnable"):
            flow.run_checks({"test": ["unknown"], "join": ["test"]}, {"authorize"}, {"test": lambda: True})

    def test_preview_layers_only_planned_changes_over_accepted_snapshot(self):
        baseline = self.staged(flow.plan(self.db, "base", "Build short links with analytics"))
        flow.validate(self.db, "base", baseline["digest"], lambda p: (True, "synthetic"))
        flow.decide(self.db, "base", "accept", baseline["digest"], "test baseline")
        base = flow.snapshot(self.db)
        plan = self.staged(flow.plan(self.db, "preview", "Add read-only link expansion with Karate"))
        data = json.loads(flow.current(self.db, "preview")["payload"])
        self.assertIn("inspect", plan["graph"])
        self.assertIn("FR-004", data["documents"]["PRD.md"])
        self.assertIn("karate-junit5", data["candidate"]["pom.xml"])
        self.assertTrue(any(p.endswith(".feature") for p in plan["proposed_files"]))
        self.assertEqual(set(base) & set(plan["proposed_files"]), {"pom.xml"})
        for path in base.keys() - {"pom.xml"}:
            self.assertEqual(base[path], data["candidate"][path])
        self.assertEqual(base, flow.snapshot(self.db))
        with self.assertRaisesRegex(ValueError, "Only the planned"):
            flow.project.prepare_preview(base, {"pom.xml": "override"})

    def test_checkout_published_only_after_accept_and_rollback_protects_edits(self):
        app = self.home / "urlShortener"
        baseline = self.staged(flow.plan(self.db, "base", "Build short links with analytics"))
        flow.validate(self.db, "base", baseline["digest"], lambda p: (True, "test"))
        flow.decide(self.db, "base", "accept", baseline["digest"], "test", app)
        before = flow.snapshot(self.db)
        preview = self.staged(flow.plan(self.db, "preview", "Add read-only link expansion with Karate"))
        flow.validate(self.db, "preview", preview["digest"], lambda p: (True, "test"))
        self.assertFalse((app / flow.project.PREVIEW).exists())
        flow.decide(self.db, "preview", "accept", preview["digest"], "test", app)
        accepted = flow.snapshot(self.db)
        self.assertEqual(accepted, {k: (app / k).read_text(encoding="utf-8") for k in accepted})
        pom = app / "pom.xml"
        pom.write_text("local edit", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Local changes"):
            flow.decide(self.db, "preview", "rollback", preview["digest"], "test", app)
        self.assertEqual(accepted, flow.snapshot(self.db))
        self.assertEqual("local edit", pom.read_text(encoding="utf-8"))
        pom.write_text(accepted["pom.xml"], encoding="utf-8")
        flow.decide(self.db, "preview", "rollback", preview["digest"], "test", app)
        self.assertEqual(before, {k: (app / k).read_text(encoding="utf-8") for k in before})
        self.assertFalse((app / flow.project.PREVIEW).exists())
