"""Canopy control plane. Local releases are source snapshots, never deployments."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
from pathlib import Path
import re
import sys
import time

import checkout
import reviewer
from sdlc_agents import ROOT, WORKERS, GateError, config, require
from sdlc_graph import GRAPH, ready
from sdlc_store import Store, sha
from sdlc_reports import metrics


def create(store, run, spec):
    require(re.fullmatch(r"[a-zA-Z0-9_-]{1,60}", run), "Invalid run identifier")
    require(isinstance(spec, dict) and spec.get("kind") in {"greenfield", "brownfield", "ambiguous"}
            and isinstance(spec.get("request"), str) and 0 < len(spec["request"]) <= 8000, "Invalid scenario")
    cfg = config(spec["project"])
    policy = json.loads((ROOT / "policies" / "control.json").read_text())
    with store.tx():
        require(not store.db.execute("SELECT 1 FROM runs WHERE id=?", (run,)).fetchone(), "Run already exists")
        s = dict(run=run, project=spec["project"], scenario=store.put(spec), revision=1, config=store.put(cfg),
                 policy=store.put(policy), baseline=store.product(spec["project"]), done={}, repairs=0,
                 state="pending", gate=None, digest=None)
        store.log(s, "intake", "Control Plane", "created", input=s["scenario"], baseline=s["baseline"], policy=s["policy"])
        store.save(s)
    return s


def decision_hash(s, n):
    return sha([s["run"], s["revision"], s["baseline"], s["policy"], s["config"], n.id,
                {p:s["done"][p] for p in n.inputs}])


def snapshot_change(store, s, new, undo):
    cfg = store.get(s["config"])
    old = store.product(s["project"])
    checkout.publish(store.root / cfg["checkout"], store.get(old), store.get(new), undo, cfg["extra_files"])
    store.db.execute("INSERT OR REPLACE INTO products VALUES(?,?)", (s["project"], new))


def approve(store, run, digest, reason, actor="local operator", reject=False, signature=None):
    require(reason.strip(), "Decision rationale required")
    with ExitStack() as undo:
        with store.tx():
            s = store.load(run)
            require(s["state"] == "awaiting_approval" and digest == s["digest"] and
                    decision_hash(s, GRAPH[s["gate"]]) == digest, "Decision does not match pending revision and artifact")
            require(store.product(s["project"]) == s["baseline"], "Baseline changed; re-plan before approval")
            gate = s["gate"]
            verified=reviewer.authenticate(store,s,"reject" if reject else "approve",reason,signature)
            proof={}
            if verified:
                actor="ssh:"+verified["principal"]
                proof={"signed_decision":store.put(verified)}
            if gate == "release_approval" and not reject:
                report = store.get(s["done"]["readiness"])
                proof = store.get(report["review_evidence"])
                history = store.history(run)
                require(proof["trace_head"] in {e["hash"] for e in history}
                        and proof["metrics_hash"] == sha(store.get(proof["metrics_hash"])),
                        "Release evidence no longer matches the verified trace and metrics")
            store.log(s, gate, "Human", "rejected" if reject else "approved", subject=digest, reason=reason, actor=actor, **proof)
            if reject:
                s["state"] = "rejected"
            else:
                s["done"][gate] = store.put(dict(subject=digest, reason=reason, actor=actor, **proof))
                s["state"] = "pending"
                if gate == "release_approval":
                    target = store.put(store.get(s["done"]["implementation"])["files"])
                    require(target == store.get(s["done"]["readiness"])["candidate"], "Readiness artifact mismatch")
                    snapshot_change(store, s, target, undo)
                    s.update(state="released", accepted=target)
                    store.log(s, gate, "Control Plane", "released", checkpoint=target, rollback=s["baseline"])
            s.update(gate=None, digest=None)
            store.save(s)
        undo.pop_all()
    return s


def intervene(store, run, action, reason, request=None, proposal=None, criteria=None):
    require(reason.strip(), "Reason required")
    with ExitStack() as undo:
        with store.tx():
            s = store.load(run)
            prev = s["state"]
            if action == "rollback":
                require(prev == "released" and store.product(s["project"]) == s["accepted"], "Rollback checkpoint is no longer current")
                snapshot_change(store, s, s["baseline"], undo)
                s["state"] = "rolled_back"
            elif action == "stop":
                require(prev in {"pending", "executing", "awaiting_approval"}, "Cannot stop a closed run")
                s.update(state="safe_stop", failed_stage=s.get("gate") or "operator_stop")
            elif action == "recover":
                require(prev == "safe_stop", "No safe-stop to recover")
                charge_repair(store, s)
                if s.get("failed_stage") in {"implementation","qa","security","design"}:
                    old = s["done"]
                    s["done"] = {k:v for k,v in old.items() if k in {"requirements","requirements_approval"}}
                    store.log(s,"design","Architect","invalidated",dependent_artifacts={k:v for k,v in old.items() if k not in s["done"]},
                              reason="Re-plan after failed gate; new plan and execution approvals required")
                    s["revision"] += 1
                s.update(state="pending", gate=None, digest=None)
            elif action == "revise":
                require(prev in {"safe_stop","pending","awaiting_approval","needs_clarification","rejected"} and request.strip(),
                        "Revision requires open or stopped run and clarification")
                if prev == "safe_stop":
                    charge_repair(store, s)
                spec = store.get(s["scenario"])
                spec.setdefault("original", spec["request"])
                spec["request"] = request
                if criteria is not None:
                    require(isinstance(criteria,list) and 0<len(criteria)<=100 and
                            all(isinstance(c,str) and 0<len(c.strip())<=2000 for c in criteria),
                            "Expected bounded nonempty acceptance criteria")
                    spec["criteria"] = criteria
                    # Previously mapped tests described the old criteria; never attest them as a new mapping.
                    spec.pop("acceptance_tests",None)
                if proposal is not None:
                    require(isinstance(proposal,dict), "Expected scoped repair proposal")
                    spec.pop("local_model",None)
                    spec["proposal"] = proposal
                store.log(s, "planner", "Architect", "invalidated", upstream=s["scenario"], dependent_artifacts=s["done"])
                s.update(state="pending", done={}, gate=None, digest=None, revision=s["revision"]+1,
                         scenario=store.put(spec), baseline=store.product(s["project"]))
            else:
                raise ValueError("Unsupported intervention")
            store.log(s, "control", "Human", action, reason=reason, previous_state=prev, checkpoint=s["baseline"])
            store.save(s)
        undo.pop_all()
    return s


def charge_repair(store, s):
    require(s["repairs"] < store.get(s["policy"])["max_repairs"], "Retry budget exhausted; keep checkpoint and start a reviewed successor")
    s["repairs"] += 1
    store.log(s,"recovery","Control Plane","repair_authorized",attempt=s["repairs"],checkpoint=s["baseline"])


def review_evidence(store,s):
    history = store.history(s["run"])
    for stage,key in s["done"].items():
        value = store.get(key)
        if GRAPH[stage].owner=="Human":
            require(any(e["stage"]==stage and e["action"]=="approved" and
                        e["details"]["subject"]==value["subject"] and
                        e["details"]["reason"]==value["reason"] for e in history),
                    "Missing prior approval evidence: "+stage)
        else:
            require(any(e["stage"]==stage and e["action"]=="passed" and
                        e["details"].get("output")==key for e in history), "Missing gate evidence: "+stage)
    return store.put({"trace_head":history[-1]["hash"],"metrics_hash":store.put(metrics(history)),
                      "through":"documentation","inputs":dict(s["done"]),"checkpoint":s["baseline"]})


def resume(store, run, workers=None):
    workers = WORKERS if workers is None else workers
    while True:
        with store.tx():
            s = store.load(run)
            if s["state"] != "pending":
                return s
            batch = ready(s["done"])
            require(batch, "Graph cannot advance")
            if store.product(s["project"]) != s["baseline"]:
                s.update(state="safe_stop", failed_stage="baseline")
                store.log(s, "planner", "Control Plane", "failed", reason="Baseline changed; revise")
                store.save(s)
                return s
            n = batch[0]
            if n.owner == "Human":
                s.update(state="awaiting_approval", gate=n.id, digest=decision_hash(s,n))
                store.log(s, n.id, n.owner, "approval_requested", digest=s["digest"], inputs={p:s["done"][p] for p in n.inputs})
                store.save(s)
                return s
            batch = [n for n in batch if n.owner != "Human"]
            ctx = {k: store.get(s[k]) for k in ("scenario","config","policy","baseline")}
            ctx["revision"] = s["revision"]
            ctx["feedback"] = s.get("error")
            done = {p:store.get(key) for p,key in s["done"].items()}
            if any(n.id=="readiness" for n in batch):
                try:
                    ctx["review_evidence"] = review_evidence(store,s)
                except ValueError as err:
                    s.update(state="safe_stop",failed_stage="readiness",error={"reason":str(err)})
                    store.log(s,"readiness","Control Plane","failed",reason=str(err))
                    store.save(s)
                    return s
            s.update(state="executing", attempt=s.get("attempt",0)+1)
            for n in batch:
                store.log(s,n.id,n.owner,"tool_requested",tool=n.tool,
                          inputs={p:s["done"][p] for p in n.inputs}, scenario=s["scenario"], attempt=s["attempt"])
            store.save(s)

        def execute(n):
            start = time.monotonic()
            try:
                require(n.tool in ctx["policy"]["agents"].get(n.owner, []) and n.tool in workers,
                        "Policy denied tool: " + n.tool)
                value = workers[n.tool](ctx, {p:done[p] for p in n.inputs})
                return True, value, time.monotonic()-start
            except Exception as err:
                # Worker faults are gate failures, not successful fallbacks.
                return False, {"reason": str(err), "type": type(err).__name__, **getattr(err,"evidence",{})}, time.monotonic()-start
        with ThreadPoolExecutor(max_workers=len(batch)) as pool:
            results = list(pool.map(execute,batch))
        with store.tx():
            cur = store.load(run)
            require(cur["state"] == "executing" and cur["attempt"] == s["attempt"] and cur["revision"] == s["revision"],
                    "Run was interrupted; discarded late worker results")
            s = cur
            s["state"] = "pending"
            for n,(ok,value,elapsed) in zip(batch,results):
                artifact = store.put(value)
                store.log(s,n.id,n.owner,"passed" if ok else "failed", output=artifact, tool=n.tool,
                          duration_seconds=round(elapsed,4), **({} if ok else {"reason":value["reason"]}))
                if ok:
                    s["done"][n.id] = artifact
                    if n.id == "design" and value.get("fallback"):
                        store.log(s,n.id,"Coder","fallback",reason=value["fallback"])
                    if n.id == "requirements" and value["questions"]:
                        s.update(state="needs_clarification",gate=n.id)
                        store.log(s,n.id,n.owner,"clarification_requested",questions=value["questions"])
                else:
                    s.update(state="safe_stop",failed_stage=n.id,error=value)
                    store.log(s,n.id,"Control Plane","safe_stop", checkpoint=s["baseline"], repairs=s["repairs"])
            store.save(s)
            if s["state"] != "pending":
                return s


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    sub = parser.add_subparsers(dest="action",required=True)
    p=sub.add_parser("enroll-reviewer",help="Pin ONE reviewer public key before starting any runs")
    p.add_argument("principal")
    p.add_argument("public_key",type=Path)
    p=sub.add_parser("challenge",help="Write exact bytes to inspect and sign with OpenSSH")
    p.add_argument("run")
    p.add_argument("decision",choices=("approve","reject"))
    p.add_argument("reason")
    p.add_argument("output",type=Path)
    for action in ("run","resume","status","approve","reject","revise","stop","recover","rollback","export","inspect","interactive","policy","metrics"):
        p = sub.add_parser(action)
        if action != "metrics":
            p.add_argument("run")
        if action in {"run","policy","export","metrics"}:
            p.add_argument("path",type=Path)
        if action == "run":
            p.add_argument("--local-model",help="Authorize inference on loopback only; syntax PORT:MODEL")
        if action == "inspect":
            p.add_argument("stage",choices=GRAPH)
        if action in {"approve","reject"}:
            p.add_argument("digest")
            p.add_argument("--signature",type=Path)
        if action == "revise":
            p.add_argument("request")
            p.add_argument("--criterion",action="append",help="Replace acceptance criteria; repeat for each observable outcome")
            p.add_argument("--proposal-file",type=Path,help="Reviewed path-to-source JSON from a repair agent")
        if action in {"approve","reject","stop","recover","rollback","revise"}:
            p.add_argument("reason")
    a = parser.parse_args(argv)
    store = Store(a.workspace)
    try:
        if a.action=="enroll-reviewer":
            return reviewer.enroll(store,a.principal,a.public_key.read_text(encoding="utf-8"))
        if a.action=="challenge":
            data=reviewer.payload(store,store.load(a.run),a.decision,a.reason)
            with a.output.open("xb") as f:
                f.write(data)
            return {"challenge":str(a.output),"namespace":reviewer.NAMESPACE}
        if a.action == "metrics":
            from sdlc_reports import aggregate
            return aggregate(store,a.path)
        if a.action == "run":
            spec = json.loads(a.path.read_text(encoding="utf-8-sig"))
            require("local_model" not in spec, "Local model access requires explicit command-line authorization")
            if a.local_model:
                port, sep, name = a.local_model.partition(":")
                require(sep and port.isdigit() and 0<int(port)<65536 and re.fullmatch(r"[a-zA-Z0-9._:/-]{1,100}", name),
                        "Expected PORT:MODEL")
                spec["local_model"]={"port":int(port),"name":name}
            create(store,a.run,spec)
            s = resume(store,a.run)
        elif a.action in {"resume","status"}:
            s = resume(store,a.run) if a.action == "resume" else store.load(a.run)
        elif a.action in {"approve","reject"}:
            s = approve(store,a.run,a.digest,a.reason,reject=a.action=="reject",signature=a.signature.read_bytes() if a.signature else None)
        elif a.action in {"revise","rollback","stop","recover"}:
            proposal_file = getattr(a,"proposal_file",None)
            s = intervene(store,a.run,a.action,a.reason,getattr(a,"request",None),
                          json.loads(proposal_file.read_text(encoding="utf-8-sig")) if proposal_file else None,getattr(a,"criterion",None))
        elif a.action == "inspect":
            s = store.load(a.run)
            require(a.stage in s["done"], "No completed artifact for stage")
            return store.get(s["done"][a.stage])
        elif a.action == "export":
            from sdlc_reports import export
            return export(store,a.run,a.path)
        else:
            s = store.load(a.run)
            require(s["state"]=="awaiting_approval", "No approval pending")
            if a.action == "policy":
                rules = json.loads(a.path.read_text(encoding="utf-8-sig"))["decisions"]
                matches = [r for r in rules if (r.get("run"),r.get("gate"),r.get("digest"))==(a.run,s["gate"],s["digest"])]
                require(len(matches)==1 and matches[0].get("decision") in {"approve","reject"}, "No unique digest-bound policy decision; waiting for human")
                rule = matches[0]
                s = approve(store,a.run,s["digest"],rule["reason"],"operator policy "+sha(rules),rule["decision"]=="reject")
            else:
                print(f"{s['gate']} {s['digest']} — type approve or reject:", file=sys.stderr)
                decision = input().strip()
                require(decision in {"approve","reject"}, "No explicit decision")
                print("Decision rationale:",file=sys.stderr)
                s = approve(store,a.run,s["digest"],input(),"interactive operator",decision=="reject")
        return {k:v for k,v in s.items() if k not in {"config","policy"}}
    finally:
        store.db.close()


if __name__=="__main__":
    try:
        print(json.dumps(main(),indent=2))
    except (ValueError, OSError, KeyError) as err:
        sys.exit(str(err))
