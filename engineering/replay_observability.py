"""Reproduce the external-agent experiment in a fresh workspace using labeled fixture decisions."""
import argparse
import json
from pathlib import Path
import tempfile

from replay import Replay, product_hash


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorize-demo",action="store_true",required=True)
    parser.add_argument("--evidence",required=True,type=Path,help="New output directory, never overwritten")
    args=parser.parse_args()
    if args.evidence.exists():
        parser.error("Evidence directory already exists")
    with tempfile.TemporaryDirectory(prefix="canopy-obs-") as tmp:
        root=Path(tmp).resolve()
        r=Replay(root,1200)
        workspace=root/"workspace"
        workspace.mkdir()
        r.release(workspace,"greenfield")
        base=product_hash(workspace)
        run="observability-api-docs"
        r.release(workspace,run)
        candidate=product_hash(workspace)
        if base==candidate:
            raise ValueError("No brownfield change applied")
        r.export(workspace,run,args.evidence)
        ready=json.loads((args.evidence/"release-readiness.json").read_bytes())
        if ready["candidate"]!=candidate or ready["rollback_to"]!=base:
            raise ValueError("Readiness does not match the published checkout")
        print(f"Simulated release only: {base} -> {candidate}")


if __name__=="__main__":
    main()
