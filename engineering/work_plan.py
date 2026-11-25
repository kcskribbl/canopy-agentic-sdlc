"""Derive reviewable work packages and source-level impact from a frozen Maven change."""
from graphlib import TopologicalSorter
from pathlib import PurePosixPath
import re
import xml.etree.ElementTree as ET

import yaml


def build(files, baseline, delta, contract_path, requirements):
    groups = {}
    for path in sorted(delta):
        group = ("tests" if path.startswith("src/test/") else
                 "application" if path.startswith("src/main/java/") else
                 "contract" if path == contract_path else
                 "persistence" if path.endswith(".sql") else "configuration")
        groups.setdefault(group, []).append(path)
    deps = {"configuration": [], "persistence": ["configuration"], "contract": [],
            "application": ["configuration", "persistence", "contract"], "tests": ["application", "contract", "persistence", "configuration"]}
    goals = {"configuration": "Prepare build, runtime and operational inputs", "contract": "Define observable HTTP behavior",
             "persistence": "Apply versioned schema design", "application": "Implement the reviewed service changes",
             "tests": "Exercise acceptance criteria and unchanged behavior"}
    tasks = {g: {"goal":goals[g], "depends_on":[p for p in deps[g] if p in groups],
                 "files":paths, "requirements":list(requirements)} for g,paths in groups.items()}
    # Compare complete operation objects: changing headers matters even if a route name stays the same.
    def operations(snapshot):
        if contract_path not in snapshot:
            return {}
        spec = yaml.safe_load(snapshot[contract_path])
        return {f"{verb.upper()} {route}":op for route,methods in spec["paths"].items()
                for verb,op in methods.items() if verb in {"get","post","put","delete","patch","head","options","trace"}}
    old, new = operations(baseline), operations(files)
    api_changes = sorted(k for k in old.keys() | new.keys() if old.get(k)!=new.get(k))
    sources = {PurePosixPath(p).stem:p for p in files if p.startswith("src/main/java/") and p.endswith(".java")}
    edges = {}
    for path in groups.get("application", []):
        edges[path] = sorted({sources[name] for name in re.findall(r"\b[A-Z][A-Za-z0-9_]*\b", files[path])
                              if name in sources and sources[name]!=path})
    pom = ET.fromstring(files["pom.xml"])
    module = pom.findtext("{*}artifactId")
    return tasks, {"module":module, "changed_http_operations":api_changes,
                   "source_dependencies":edges, "changed_schema":groups.get("persistence", []),
                   "existing_files_modified":sorted(delta.keys() & baseline.keys()), "new_files":sorted(delta.keys()-baseline.keys()),
                   "regression_risk":"Re-run the unchanged baseline tests alongside new scenarios. "
                                     "Source dependencies are static references, not proof of runtime calls."}


def assemble(baseline, changes, tasks):
    if not tasks or any(p not in tasks for t in tasks.values() for p in t["depends_on"]):
        raise ValueError("Invalid work package dependency")
    applied = []
    files = dict(baseline)
    for task in TopologicalSorter({k:t["depends_on"] for k,t in tasks.items()}).static_order():
        for path in tasks[task]["files"]:
            if path not in changes or path in applied:
                raise ValueError("Unplanned or duplicate work package output: "+path)
            files[path] = changes[path]
            applied.append(path)
    if set(applied)!=set(changes):
        raise ValueError("Implementation omitted reviewed work package outputs")
    return files
