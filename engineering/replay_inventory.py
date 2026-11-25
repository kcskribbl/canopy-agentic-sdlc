"""Exercise a real failed QA gate, reviewed repair and rollback using only the public CLI."""
import argparse
import json
from pathlib import Path
import tempfile

from replay import FIXTURE, ROOT, Replay
from sdlc_store import sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorize-demo", required=True, action="store_true")
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    if args.evidence.exists():
        parser.error("Choose a new evidence directory")
    scenario = json.loads((ROOT / "scenarios/inventory/scenario.json").read_bytes())
    pack = ROOT / "examples/projects/inventory"
    key = "src/main/java/dev/canopy/inventory/Inventory.java"
    repaired = (pack / key).read_text(encoding="utf-8")
    guard = "if (units > available) return ResponseEntity.status(409).build();\n        available -= units;"
    if repaired.count(guard) != 1:
        raise ValueError("Fault-injection fixture no longer matches the implementation")
    broken = repaired.replace(guard, "available -= units;\n        if (available < 0) return ResponseEntity.status(409).build();")
    with tempfile.TemporaryDirectory(prefix="canopy-inventory-") as tmp:
        root = Path(tmp).resolve()
        workspace = root / "workspace"
        workspace.mkdir()
        runner = Replay(root, 1200)

        def call(action, *params):
            return runner.call(workspace, action, "inventory", *params)

        def advance(state):
            for _ in range(16):
                if state["state"] == "awaiting_approval":
                    state = call("approve", state["digest"], FIXTURE + "review " + state["gate"])
                elif state["state"] == "pending":
                    state = call("resume")
                else:
                    return state
            raise RuntimeError("Transition budget exhausted")

        seed = root / "seed.json"
        seed.write_text(json.dumps({**scenario, "proposal": {key: broken}}), encoding="utf-8")
        failed = advance(call("run", seed))
        diagnostic = failed.get("error", {}).get("diagnostic", "")
        if (failed["state"] != "safe_stop" or failed.get("failed_stage") != "qa"
                or "InventoryTest.rejectionPreservesStock" not in diagnostic):
            raise RuntimeError(f"Expected stock-preservation failure, got {failed}")
        checkout = workspace / "inventory"
        if checkout.exists():
            raise RuntimeError("Failed candidate published before sign-off")
        fix = root / "repair.json"
        fix.write_text(json.dumps({key: repaired}), encoding="utf-8")
        passed = advance(call("revise", scenario["request"], FIXTURE + "check available stock before decrement",
                              "--proposal-file", fix))
        if passed["state"] != "released":
            raise RuntimeError(f"Repaired candidate not released: {passed}")
        files = {f.relative_to(checkout).as_posix(): f.read_bytes().decode("utf-8")
                 for f in checkout.rglob("*") if f.is_file()}
        if sha(files) != passed["accepted"] or files[key] != repaired:
            raise RuntimeError("Released files do not match the reviewed snapshot")
        result = call("rollback", FIXTURE + "restore the original empty managed checkout")
        if (result["state"] != "rolled_back" or result["baseline"] != sha({})
                or any(f.is_file() for f in checkout.rglob("*"))):
            raise RuntimeError("Rollback failed to restore empty baseline")
        runner.export(workspace, "inventory", args.evidence.resolve())
        print("Verified failed QA, reviewed repair, release and rollback:", passed["accepted"])


if __name__ == "__main__":
    main()
