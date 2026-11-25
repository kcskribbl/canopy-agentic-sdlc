import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import control
import sdlc_agents as agents
from sdlc_reports import export, metrics
from sdlc_store import sha


class GraphTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store = control.Store(self.root)
        self.addCleanup(self.store.db.close)
        self.spec = dict(project="links",kind="greenfield",request="Create a short link",criteria=["Can resolve the link"])
        self.files = {"pom.xml":"demo","src/main/java/Example.java":"demo"}
        self.workers = {**agents.WORKERS,
            "inspect_project": lambda c,i: {"changes":self.files,"checkpoint":sha(c["baseline"]),
                "tasks":{"application":{"depends_on":[],"files":list(self.files)}}},
            "maven_verify": lambda c,i: {"candidate":sha(i["implementation"]["files"]), "counts":{"tests":1}},
            "security_scan": lambda c,i: {"candidate":sha(i["implementation"]["files"]), "findings":[]},
            "render_docs": lambda c,i: {k:"test" for k in ("README.md","OPENAPI.yaml","CHANGELOG.md","ADR.md")}}

    def advance(self,until):
        for _ in range(12):
            s = control.resume(self.store,"demo",self.workers)
            if s["state"]==until or s["gate"]==until:
                return s
            self.assertEqual(s["state"],"awaiting_approval",s)
            control.approve(self.store,"demo",s["digest"],"test harness")
        self.fail("unbounded graph")

    def test_digest_gates_release_and_verified_rollback(self):
        control.create(self.store,"demo",self.spec)
        s = self.advance("plan_approval")
        with self.assertRaisesRegex(ValueError,"does not match"):
            control.approve(self.store,"demo","old","test")
        self.assertFalse((self.root/"urlShortener").exists())
        self.advance("released")
        self.assertEqual(self.files,self.store.get(self.store.product("links")))
        control.intervene(self.store,"demo","rollback","test")
        self.assertFalse((self.root/"urlShortener"/"pom.xml").exists())
        report = export(self.store,"demo",self.root/"evidence")
        self.assertEqual(1,report["metrics"]["rollbacks"])
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.db.execute("DELETE FROM events WHERE run='demo'")

    def test_failed_security_blocks_join_and_replans_with_budget(self):
        def block(c,i):
            raise agents.GateError("open high finding", {"findings":[{"severity":"high"}]})
        self.workers["security_scan"]=block
        control.create(self.store,"demo",self.spec)
        for attempt in range(4):
            s=self.advance("safe_stop")
            self.assertNotIn("documentation",s["done"])
            self.assertEqual({},self.store.get(self.store.product("links")))
            if attempt<3:
                s=control.intervene(self.store,"demo","recover","investigate gate")
                self.assertNotIn("plan_approval",s["done"])
                self.assertEqual(attempt+1,s["repairs"])
        with self.assertRaisesRegex(ValueError,"budget exhausted"):
            control.intervene(self.store,"demo","recover","again")

    def test_durable_clarification_and_stale_result_rejection(self):
        control.create(self.store,"demo",{**self.spec,"kind":"ambiguous"})
        s=control.resume(self.store,"demo")
        self.assertEqual("needs_clarification",s["state"])
        control.intervene(self.store,"demo","revise","human clarification","Create links with stable public codes")
        self.assertEqual("requirements_approval", self.advance("requirements_approval")["gate"])
        self.assertEqual(1,metrics(self.store.history("demo"))["replans"])

    def test_vague_request_cannot_avoid_clarification_by_selecting_greenfield(self):
        control.create(self.store,"demo",{**self.spec,"request":"Make the service better"})
        s=control.resume(self.store,"demo")
        self.assertEqual("needs_clarification",s["state"])
        self.assertNotIn("design",s["done"])

    def test_missing_criteria_resolved_without_losing_original_request(self):
        control.create(self.store,"demo",{**self.spec,"request":"Make links better","criteria":[]})
        self.assertEqual("needs_clarification",control.resume(self.store,"demo")["state"])
        control.intervene(self.store,"demo","revise","owner clarified","Return 404 for an unknown link without counting a visit.")
        s = control.resume(self.store,"demo")
        artifact = self.store.get(s["done"]["requirements"])
        self.assertEqual("requirements_approval",s["gate"])
        self.assertEqual("Make links better",artifact["original"])
        self.assertIn("404",artifact["criteria"]["AC-001"])
        control.intervene(self.store,"demo","revise","owner supplied criteria","Preview links",criteria=["Preview leaves the total unchanged."])
        s = control.resume(self.store,"demo")
        self.assertEqual({"AC-001":"Preview leaves the total unchanged."},self.store.get(s["done"]["requirements"])["criteria"])

    def test_task_assembly_rejects_incomplete_coverage_and_missing_dependencies(self):
        from work_plan import assemble
        with self.assertRaisesRegex(ValueError,"omitted"):
            assemble({},self.files,{"app":{"files":["pom.xml"],"depends_on":[]}})
        with self.assertRaisesRegex(ValueError,"dependency"):
            assemble({},self.files,{"app":{"files":list(self.files),"depends_on":["unknown"]}})

    def test_readiness_independently_rejects_blocking_findings(self):
        self.workers["security_scan"]=lambda c,i: {"candidate":sha(i["implementation"]["files"]), "findings":[{"severity":"high"}]}
        control.create(self.store,"demo",self.spec)
        s=self.advance("safe_stop")
        self.assertEqual("readiness",s["failed_stage"])
        self.assertNotIn("release_approval",s["done"])

    def test_signoff_proof_is_persisted_before_final_decision(self):
        control.create(self.store,"demo",self.spec)
        s=self.advance("release_approval")
        report=self.store.get(s["done"]["readiness"])
        proof=self.store.get(report["review_evidence"])
        self.assertEqual(s["done"]["security"],proof["inputs"]["security"])
        self.assertFalse(self.store.get(proof["metrics_hash"])["released_at_least_once"])
        self.assertIn(proof["trace_head"],{e["hash"] for e in self.store.history("demo")})
        self.assertFalse((self.root/"urlShortener").exists())

    def test_unavailable_model_selects_bounded_fallback_and_protected_diff_denied(self):
        spec={**self.spec,"local_model":{"port":1,"name":"fixture"}}
        cfg=agents.config("links")
        cfg["required_routes"]=["/demo"]
        ctx=dict(scenario=spec,config=cfg,baseline={},policy={"max_files":10,"max_changed_lines":100,"max_file_bytes":5000})
        pack={"openapi.yaml":"openapi: 3.0.3\npaths:\n  /demo:\n    get: {}\n","pom.xml":"<project/>"}
        with patch.object(agents,"read_pack",return_value=pack), patch.object(agents,"local_proposal",side_effect=OSError("down")):
            plan=agents.design(ctx,{"requirements":{"criteria":{"AC-001":"demo"}}})
            self.assertIn("deterministic",plan["fallback"])
            ctx["scenario"]={**self.spec,"proposal":{"../engineering/control.py":"bad"}}
            with self.assertRaisesRegex(ValueError,"Policy denied"):
                agents.design(ctx,{"requirements":{"criteria":{}}})

    def test_policy_denies_worker_without_a_tool_grant(self):
        s=control.create(self.store,"demo",self.spec)
        policy=self.store.get(s["policy"])
        policy["agents"]["Requirements Analyst"]=[]
        s["policy"]=self.store.put(policy)
        self.store.save(s)
        s=control.resume(self.store,"demo")
        self.assertEqual("safe_stop",s["state"])
        self.assertIn("Policy denied tool",s["error"]["reason"])
