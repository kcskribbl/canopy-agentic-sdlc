"""Small durable plan -> review -> isolated validation -> human acceptance workflow."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import time

import canopy_product as project
import checkout
import requirements as analyst

def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def db_open(home):
    home.mkdir(exist_ok=True, parents=True)
    db = sqlite3.connect(home / "ledger.sqlite", timeout=5)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS revisions(id TEXT, rev INTEGER, state TEXT NOT NULL, payload TEXT NOT NULL,
          PRIMARY KEY(id,rev));
        CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY, id TEXT, rev INTEGER, at TEXT, action TEXT, detail TEXT);
        CREATE TABLE IF NOT EXISTS product(slot INTEGER PRIMARY KEY CHECK(slot=1), snapshot TEXT NOT NULL);
        INSERT OR IGNORE INTO product VALUES(1,'{}');
    """)
    return db


def current(db, run):
    row = db.execute("SELECT * FROM revisions WHERE id=? ORDER BY rev DESC LIMIT 1", (run,)).fetchone()
    if not row:
        raise ValueError("Unknown run")
    return row


def snapshot(db):
    return json.loads(db.execute("SELECT snapshot FROM product WHERE slot=1").fetchone()[0])


def event(db, row, action, detail):
    db.execute("INSERT INTO events(id,rev,at,action,detail) VALUES(?,?,?,?,?)",
               (row["id"], row["rev"], datetime.now(timezone.utc).isoformat(), action, encode(detail)))


def transition(db, row, state, detail):
    changed = db.execute("UPDATE revisions SET state=? WHERE id=? AND rev=? AND state=? AND rev="
                         "(SELECT MAX(rev) FROM revisions WHERE id=?)",
                         (state, row["id"], row["rev"], row["state"], row["id"])).rowcount
    if changed != 1:
        raise ValueError("Stale revision or concurrent transition; inspect current status")
    event(db, row, state, detail)


def plan(db, run, request, supplied=None, revise=False):
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,48}", run) or not request.strip() or len(request) > 4000:
        raise ValueError("Expected a portable run ID and nonempty bounded requirement")
    with db:
        db.execute("BEGIN IMMEDIATE")
        prev = db.execute("SELECT max(rev) FROM revisions WHERE id=?", (run,)).fetchone()[0]
        if bool(prev) != revise:
            raise ValueError("Use plan for a new run or revise for an existing run")
        if prev and current(db, run)["state"] in {"validating", "accepted", "rolled_back"}:
            raise ValueError("Cannot revise an active validation or closed run")
        if prev and current(db, run)["state"] == "safe_stop":
            repairs = db.execute("SELECT COUNT(*) FROM events WHERE id=? AND action='repair_requested'", (run,)).fetchone()[0]
            if repairs:
                raise ValueError("Repair budget exhausted; keep evidence for human investigation")
            event(db, current(db, run), "repair_requested", {"limit": 1})
        rev = (prev or 0) + 1
        feature, goal = project.interpret(request)
        base = snapshot(db)
        data = {"request": request, "goal": goal, "feature": feature, "baseline_digest": digest(base)}
        original = json.loads(db.execute("SELECT payload FROM revisions WHERE id=? AND rev=1", (run,)).fetchone()[0])["request"] if prev else request
        text = analyst.intent(run, rev, original, request, feature, goal)
        data.update(documents={"INTENT.md": text}, digest=digest(text), supplied=supplied)
        state = "awaiting_intent_approval" if feature else "needs_clarification"
        db.execute("INSERT INTO revisions VALUES(?,?,?,?)", (run, rev, state, encode(data)))
        event(db, current(db, run), state, {"goal": goal, "supersedes": prev, "digest": data["digest"]})
    return status(db, run)


def approve_document(db, run, action, approved, reason):
    if not reason.strip():
        raise ValueError("Provide the review rationale")
    with db:
        db.execute("BEGIN IMMEDIATE")
        row = current(db, run)
        data = json.loads(row["payload"])
        expected = {"approve-intent": "awaiting_intent_approval", "approve-prd": "awaiting_prd_approval"}
        if expected.get(action) != row["state"] or approved != data["digest"]:
            raise ValueError("Approval requires the current document state and digest")
        docs = data["documents"]
        if action == "approve-intent":
            text = analyst.prd(run, row["rev"], data["feature"], data["goal"], approved)
            docs["PRD.md"] = text
            data["digest"] = digest(text)
            state = "awaiting_prd_approval"
        else:
            base = snapshot(db)
            if digest(base) != data["baseline_digest"]:
                raise ValueError("Baseline changed; revise and review the new intent")
            sources = {p: s for p, s in base.items() if p.startswith(project.JAVA)}
            supplied = data.pop("supplied")
            preview = data["feature"] == "expansion-contract"
            if preview:
                creates, scaffold, impact = project.prepare_preview(base, supplied)
            else:
                creates, scaffold, impact = project.prepare(data["feature"], sources, supplied)
            graph = {"interpret": [], "intent_approval": ["interpret"], "prd": ["intent_approval"],
                     "prd_approval": ["prd"], "inspect": ["prd_approval"], "design": ["inspect"],
                     "propose": ["design"], "authorize": ["propose"], "test": ["authorize"],
                     "document": ["authorize"], "join": ["test", "document"], "accept": ["join"]}
            if not base:
                del graph["inspect"]
                graph["design"] = ["prd_approval"]
            docs["SPEC.md"] = (f"# Implementation specification\n\nApproved [PRD](PRD.md): `{approved}`.\n\n"
                               + ("Add GET /api/links/{code} using a parameterized SELECT, with no visit update or network fetch. "
                                  "Preserve the accepted snapshot and add an isolated Karate HTTP gate to Maven verification.\n\n"
                                  if preview else "Use Java 21, Spring Boot JDBC and H2. Apply only the listed Java creates; retain trusted build and tests.\n\n")
                               + "\n".join(f"- `{p}`" for p in sorted(creates)) +
                               "\n\nJoin the Maven verification and documentation tasks before human acceptance.\n")
            data.update(graph=graph, impact=impact, creates=creates, baseline=base,
                        candidate={**scaffold, **sources, **creates},
                        author="bundled AI-authored example" if supplied is None else "external proposal")
            data["digest"] = digest([run, row["rev"], data])
            state = "awaiting_validation_approval"
        db.execute("UPDATE revisions SET payload=? WHERE id=? AND rev=?", (encode(data), run, row["rev"]))
        event(db, row, action, {"approved_digest": approved, "reason": reason, "operator": "local CLI"})
        transition(db, row, state, {"digest": data["digest"]})
    return status(db, run)


def status(db, run):
    row = current(db, run)
    data = json.loads(row["payload"])
    return {"run": run, "revision": row["rev"], "state": row["state"],
            **{k: v for k, v in data.items() if k not in {"candidate", "baseline", "creates", "documents", "supplied"}},
            "documents": list(data.get("documents", {})),
            "proposed_files": sorted(data.get("creates", {})),
            "history": [dict(x) for x in db.execute("SELECT rev,at,action,detail FROM events WHERE id=? ORDER BY seq", (run,))]}


def materialize(files, root):
    for key, source in files.items():
        path = root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as out:
            out.write(source)


def test_product(root):
    wrapper = project.ROOT / ("mvnw.cmd" if os.name == "nt" else "mvnw")
    cmd = [str(wrapper), "-B", "-ntp", "-f", str(root / "pom.xml"), "-DfailIfNoTests=true", "verify"]
    result = subprocess.run(cmd, cwd=project.ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, errors="replace", timeout=240)
    return result.returncode == 0, result.stdout[-8000:]


def document(data):
    lines = [data["goal"], "Changed files:", *sorted(data["creates"]), "HTTP mappings in candidate:"]
    for path, text in data["candidate"].items():
        if path.startswith(project.JAVA):
            lines.extend(match.strip() for match in re.findall(r'@(?:Post|Get)Mapping\("[^"]+"\)', text))
    return "\n".join(lines)


def run_checks(graph, completed, workers):
    remaining = dict(workers)
    results = {}
    with ThreadPoolExecutor(max_workers=len(workers)) as pool:
        while remaining:
            ready = [n for n in remaining if set(graph[n]) <= completed]
            if not ready:
                raise ValueError("Invalid task dependencies: no runnable validation node")
            futures = {n: pool.submit(remaining.pop(n)) for n in ready}
            for n, future in futures.items():
                results[n] = future.result()
                completed.add(n)
    if not set(graph["join"]) <= results.keys():
        raise ValueError("Missing validation evidence at join")
    return results


def validate(db, run, approved, checker=test_product):
    with db:
        db.execute("BEGIN IMMEDIATE")
        row = current(db, run)
        data = json.loads(row["payload"])
        if row["state"] != "awaiting_validation_approval" or approved != data["digest"]:
            raise ValueError("Validation requires approval for the current candidate digest")
        if digest(snapshot(db)) != data["baseline_digest"]:
            raise ValueError("Baseline changed; revise and review the new plan")
        transition(db, row, "validating", {"operator": "local CLI", "digest": approved})
    start = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="canopy-verify-") as temp:
            root = Path(temp)
            materialize(data["candidate"], root)
            results = run_checks(data["graph"], {"authorize"},
                                 {"test": lambda: checker(root), "document": lambda: document(data)})
            ok, evidence = results["test"]
            notes = results["document"]
    except (OSError, subprocess.SubprocessError) as err:
        ok, evidence, notes = False, str(err), "Validation interrupted"
    with db:
        active = current(db, run)
        if active["state"] != "validating" or active["rev"] != row["rev"]:
            raise ValueError("Validation superseded or stopped; result cannot authorize acceptance")
        transition(db, active, "awaiting_acceptance" if ok else "safe_stop",
                   {"test_passed": ok, "test_output": evidence, "documentation": notes,
                    "duration_seconds": round(time.monotonic()-start, 3), "candidate": approved})
    return status(db, run)


def decide(db, run, action, approved, reason, application=None):
    if not reason.strip():
        raise ValueError("A human decision needs a rationale")
    with ExitStack() as undo:
        result = _decide(db, run, action, approved, reason, application, undo)
        undo.pop_all()
        return result


def _decide(db, run, action, approved, reason, application, undo):
    with db:
        db.execute("BEGIN IMMEDIATE")
        row = current(db, run)
        data = json.loads(row["payload"])
        if approved != data["digest"]:
            raise ValueError("Stale decision digest")
        if action == "accept" and row["state"] == "awaiting_acceptance" and digest(snapshot(db)) == data["baseline_digest"]:
            new, state = data["candidate"], "accepted"
        elif action == "rollback" and row["state"] == "accepted" and snapshot(db) == data["candidate"]:
            new, state = data["baseline"], "rolled_back"
        elif action == "stop" and row["state"] == "validating":
            transition(db, row, "safe_stop", {"reason": reason})
            return status(db, run)
        else:
            raise ValueError("Decision not authorized for this state or product revision")
        if application is not None:
            checkout.publish(application, snapshot(db), new, undo)
        db.execute("UPDATE product SET snapshot=? WHERE slot=1", (encode(new),))
        transition(db, row, state, {"reason": reason, "snapshot": digest(new)})
    return status(db, run)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=project.ROOT,
                        help="Directory containing .canopy and the accepted urlShortener application")
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("plan", "revise", "approve-intent", "approve-prd", "status", "report", "inspect", "validate", "accept", "rollback", "stop", "export"):
        p = sub.add_parser(name)
        if name != "export":
            p.add_argument("run")
        if name in {"plan", "revise"}:
            p.add_argument("requirement")
            p.add_argument("--proposal", type=Path, help="JSON object mapping planned paths to proposed Java source")
        if name in {"validate", "accept", "rollback", "stop", "approve-intent", "approve-prd"}:
            p.add_argument("digest")
        if name in {"accept", "rollback", "stop", "approve-intent", "approve-prd"}:
            p.add_argument("reason")
        if name == "export":
            p.add_argument("directory", type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    home = workspace / ".canopy"
    db = db_open(home)
    try:
        if args.action in {"plan", "revise"}:
            supplied = json.loads(args.proposal.read_text(encoding="utf-8")) if args.proposal else None
            result = plan(db, args.run, args.requirement, supplied, args.action == "revise")
        elif args.action in {"approve-intent", "approve-prd"}:
            row = current(db, args.run)
            docs = json.loads(row["payload"]).get("documents", {})
            name = "INTENT.md" if args.action == "approve-intent" else "PRD.md"
            target = home / "requirements" / args.run / f"r{row['rev']}" / name
            if name not in docs or not target.is_file() or target.read_bytes() != docs[name].encode():
                raise ValueError("Missing or edited review copy; use revise to change scope, or status to restore the ledger copy")
            result = approve_document(db, args.run, args.action, args.digest, args.reason)
        elif args.action == "inspect":
            data = json.loads(current(db, args.run)["payload"])
            result = {"digest": data["digest"], "proposed_java": data.get("creates", {})}
        elif args.action == "status":
            result = status(db, args.run)
        elif args.action == "report":
            result = status(db, args.run)
            history = result.pop("history")
            counts = Counter(e["action"] for e in history)
            result.update(decisions=[json.loads(e["detail"]) for e in history if e["action"] in {"approve-intent", "approve-prd", "validating", "accepted", "rolled_back"}],
                          validation=[json.loads(e["detail"]) for e in history if "test_passed" in json.loads(e["detail"])],
                          repairs=counts["repair_requested"], rollbacks=counts["rolled_back"],
                          elapsed_seconds=(datetime.fromisoformat(history[-1]["at"])-datetime.fromisoformat(history[0]["at"])).total_seconds(),
                          limitations="Local source snapshots, not hosted deployments. Operator identity is not authenticated.")
        elif args.action == "validate":
            result = validate(db, args.run, args.digest)
        elif args.action == "export":
            files = snapshot(db)
            if not files:
                raise ValueError("No accepted product")
            args.directory.mkdir(exist_ok=False)
            materialize(files, args.directory)
            result = {"exported": str(args.directory), "snapshot": digest(files)}
        else:
            result = decide(db, args.run, args.action, args.digest, args.reason, workspace / "urlShortener")
        if args.action != "export":
            row = current(db, args.run)
            docs = json.loads(row["payload"]).get("documents", {})
            if docs:
                folder = home / "requirements" / args.run / f"r{row['rev']}"
                folder.mkdir(parents=True, exist_ok=True)
                for name, content in docs.items():
                    target = folder / name
                    if not target.exists() or target.read_bytes() != content.encode():
                        target.write_bytes(content.encode())
                result["document_directory"] = str(folder)
        print(json.dumps(result, indent=2))
        return int(args.action == "validate" and result["state"] != "awaiting_acceptance")
    finally:
        db.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, sqlite3.Error) as error:
        sys.exit(str(error))
