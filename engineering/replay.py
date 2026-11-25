"""Exercise the real Canopy CLI with explicitly authorized, isolated fixture decisions."""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from sdlc_reports import summarize


ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "scenarios"
FIXTURE = "DEMO FIXTURE / SIMULATION (not a human decision): "


class Replay:
    def __init__(self, directory, seconds):
        self.directory = directory
        self.deadline = time.monotonic() + seconds
        self.calls = 0
        scratch = directory / "tool-scratch"
        scratch.mkdir()
        self.env = {**os.environ, "TEMP": str(scratch), "TMP": str(scratch), "TMPDIR": str(scratch)}

    def call(self, workspace, verb, run, *args):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("Replay deadline expired")
        self.calls += 1
        stem = self.directory / f"{self.calls:03}-{run}-{verb}"
        cmd = [sys.executable, "-B", str(ROOT / "engineering" / "control.py"),
               "--workspace", str(workspace), verb, run, *map(str, args)]
        print(f"{run}: {verb}", flush=True)
        with stem.with_suffix(".json").open("wb") as out, stem.with_suffix(".err").open("wb") as err:
            result = subprocess.run(cmd, cwd=ROOT, env=self.env, stdin=subprocess.DEVNULL, stdout=out,
                                    stderr=err, timeout=remaining, check=False)
        if result.returncode:
            detail = (stem.with_suffix(".err").read_text(encoding="utf-8", errors="replace") or
                      stem.with_suffix(".json").read_text(encoding="utf-8", errors="replace"))
            raise RuntimeError(f"{run}/{verb} exited {result.returncode}: {detail[-2000:]}")
        if verb == "export":
            return
        value = json.loads(stem.with_suffix(".json").read_bytes())
        if not isinstance(value, dict) or value.get("run") != run or not value.get("state"):
            raise ValueError(f"{run}/{verb}: unexpected CLI status")
        return value

    def release(self, workspace, run):
        path = SCENARIOS / run / "scenario.json"
        fixture = json.loads(path.read_bytes())
        status = self.call(workspace, "run", run, path)
        clarified = interrupted = False
        for _ in range(64):
            state = status["state"]
            if state == "released":
                if run == "ambiguous" and not (clarified and interrupted):
                    raise ValueError("Released without the required clarification and recovery")
                return
            if state == "needs_clarification" and run == "ambiguous" and not clarified:
                status = self.call(workspace, "revise", run, fixture["clarification"],
                                   FIXTURE + "select the bounded link-service scope",
                                   *(arg for c in fixture["clarified_criteria"] for arg in ("--criterion",c)))
                clarified = True
            elif state == "safe_stop" and clarified and not interrupted:
                if status.get("failed_stage") != "design" or "Policy denied proposal path" not in status.get("error",{}).get("reason",""):
                    raise ValueError(f"Unexpected stop; not authorized to repair: {status.get('error')}")
                repair = self.directory / "scoped-repair.json"
                repair.write_text("{}",encoding="utf-8")
                status = self.call(workspace, "revise", run, fixture["clarification"],
                                   FIXTURE + "remove denied change; retain policy and review a new plan",
                                   "--proposal-file", repair)
                interrupted = True
            elif state == "pending":
                status = self.call(workspace, "resume", run)
            elif state == "awaiting_approval":
                if not status.get("gate") or not status.get("digest"):
                    raise ValueError("Approval requested without a gate and digest")
                gate = status["gate"]
                status = self.call(workspace, "approve", run, status["digest"],
                                   FIXTURE + f"acknowledge {gate} in isolated replay only")
                if status["state"] == "released" and gate == "release_approval":
                    status = self.call(workspace, "resume", run)
                elif status["state"] != "pending":
                    raise ValueError("Unexpected state after gate acknowledgement")
            else:
                raise ValueError(f"{run} stopped at {state}: {str(status)[-1500:]}")
        raise RuntimeError(f"{run}: transition budget exhausted")

    def export(self, workspace, run, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.call(workspace, "export", run, destination)
        for name in ("AGENT_TRACE.md", "metrics.json", "OUTCOME.md", "METRICS.md"):
            if not (destination / name).is_file() or not (destination / name).stat().st_size:
                raise ValueError(f"Incomplete export for {run}: missing or empty {name}")
        metrics = json.loads((destination / "metrics.json").read_bytes())
        if not isinstance(metrics, dict) or not metrics:
            raise ValueError(f"No exported metrics for {run}")


def product_hash(workspace):
    """Verify the durable accepted product, not a run's proposal or approval digest."""
    db = (workspace / ".canopy" / "control.sqlite").as_uri() + "?mode=ro"
    conn = sqlite3.connect(db, uri=True)
    try:
        row = conn.execute("SELECT p.hash,o.body FROM products p JOIN objects o ON o.hash=p.hash "
                           "WHERE p.project='links'").fetchone()
    finally:
        conn.close()
    if not row or not json.loads(row[1]) or hashlib.sha256(row[1].encode()).hexdigest() != row[0]:
        raise ValueError("No verifiable accepted links snapshot")
    checkout = workspace / json.loads((ROOT / "projects" / "links.json").read_bytes())["checkout"]
    expected = json.loads(row[1])
    actual = {p.relative_to(checkout).as_posix(): p for p in checkout.rglob("*") if p.is_file()}
    if actual.keys() != expected.keys() or any(actual[k].read_bytes() != v.encode() for k, v in expected.items()):
        raise ValueError("Published checkout does not match the complete accepted links snapshot")
    return row[0]


def exercise(replay):
    workspace = replay.directory / "shared-workspace"
    stage = replay.directory / "exports"
    run = "greenfield"
    workspace.mkdir()
    try:
        replay.release(workspace, run)
        baseline = product_hash(workspace)
        replay.export(workspace, run, stage / run)
        run = "brownfield"
        replay.release(workspace, run)
        changed = product_hash(workspace)
        if changed == baseline:
            raise ValueError("Brownfield did not change the accepted snapshot")
        replay.export(workspace, run, stage / run / "before-rollback")
        status = replay.call(workspace, "rollback", run, FIXTURE + "exercise restoration of greenfield")
        restored = product_hash(workspace)
        if status["state"] != "rolled_back" or restored != baseline:
            raise ValueError("Failed to restore the accepted greenfield snapshot")
        replay.export(workspace, run, stage / "after-rollback")
        for file in (stage / "after-rollback").iterdir():
            file.rename(stage / run / file.name)
        (stage / run / "RESTORATION.md").write_text(
            "# Accepted product snapshot check\n\nMeasured in the shared isolated demo workspace.\n\n"
            f"- Greenfield: `{baseline}`\n- Brownfield: `{changed}`\n- After rollback: `{restored}`\n",
            encoding="utf-8")
        run = "ambiguous"
        workspace = replay.directory / "clarification-workspace"
        workspace.mkdir()
        replay.release(workspace, run)
        replay.export(workspace, run, stage / run)
    except Exception:
        try:
            replay.export(workspace, run, replay.directory / f"partial-{run}")
        except Exception as error:
            print(f"Partial export unavailable: {error}", file=sys.stderr)
        raise

    for kind in ("greenfield", "brownfield", "ambiguous"):
        destination = SCENARIOS / kind / "evidence"
        if destination.exists():
            destination.rename(replay.directory / f"previous-{kind}")
        (stage / kind).rename(destination)
    runs = {kind:json.loads((SCENARIOS / kind / "evidence" / "metrics.json").read_bytes())
            for kind in ("greenfield", "brownfield", "ambiguous")}
    (SCENARIOS / "metrics.json").write_text(json.dumps(summarize(runs),indent=2)+"\n",encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--authorize-demo", required=True, action="store_true",
                        help="simulate gate decisions; never represents human sign-off")
    parser.add_argument("--deadline-seconds", type=int, default=1800, help="total replay time budget")
    args = parser.parse_args()
    if args.deadline_seconds <= 0:
        parser.error("--deadline-seconds must be positive")
    directory = Path(tempfile.mkdtemp(prefix=".replay-", dir=SCENARIOS))
    print(f"Isolated replay directory: {directory}", flush=True)
    try:
        exercise(Replay(directory, args.deadline_seconds))
    except (Exception, KeyboardInterrupt) as error:
        print(f"Replay incomplete: {error}\nRetained workspace and partial evidence: {directory}",
              file=sys.stderr)
        return 1
    shutil.rmtree(directory)
    print("Completed fixture replay; see scenarios/<kind>/evidence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
