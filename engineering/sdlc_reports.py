"""Derive evidence exclusively from the persisted graph, checked artifacts and event chain."""
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
from statistics import mean

from sdlc_store import sha


def metrics(events):
    latency = defaultdict(list)
    failures = {}
    recovery = []
    counts = Counter()
    stage_counts = defaultdict(Counter)
    clock = lambda e: datetime.fromisoformat(e["timestamp"])
    for e in events:
        action, stage = e["action"], e["stage"]
        counts[action] += 1
        if action in {"passed", "failed"}:
            stage_counts[stage][action] += 1
            if "duration_seconds" in e["details"]:
                latency[stage].append(e["details"]["duration_seconds"])
            if action == "failed":
                failures.setdefault(stage, clock(e))
            elif stage in failures:
                recovery.append((clock(e)-failures.pop(stage)).total_seconds())
    return {"released_at_least_once": bool(counts["released"]), "attempts": dict(counts),
            "stage_success_rates": {k: v["passed"]/v.total() for k,v in stage_counts.items()},
            "stage_latency_seconds": {k: {"total":sum(v),"mean":mean(v),"attempts":len(v)} for k,v in latency.items()},
            "elapsed_seconds": (clock(events[-1])-clock(events[0])).total_seconds(),
            "retries": counts["repair_authorized"], "rollbacks":counts["rollback"], "replans":counts["invalidated"],
            "human_interventions":sum(1 for e in events if e["agent"]=="Human" and e["action"]!="approval_requested"),
            "mttr_seconds": mean(recovery) if recovery else None, "recovery_durations_seconds": recovery,
            "unrecovered_gates":sorted(failures)}


def emit(path, value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=True)+"\n",encoding="utf-8")


def export(store,run,folder):
    s = store.load(run)
    events = store.history(run)
    m = metrics(events)
    folder.mkdir(parents=True,exist_ok=False)
    emit(folder/"metrics.json",m)
    emit(folder/"trace.json",events)
    artifacts = {}
    for e in events:
        key = e["details"].get("output")
        if key:
            value = store.get(key)
            if e["stage"]=="implementation" and "files" in value:
                value = {"files":{p:sha(v) for p,v in value["files"].items()}, "checkpoint": value["checkpoint"]}
            if e["stage"]=="design" and "changes" in value:
                value = {**value,"changes":{p:sha(v) for p,v in value["changes"].items()}}
            artifacts[key] = value
    emit(folder/"artifacts.json",artifacts)
    lines = [f"# Agent trace: {run}", "", "Local operator assertions are not authenticated identities. Demo approvals, if present, are fixture decisions.", ""]
    for e in events:
        lines.append(f"- {e['timestamp']} r{e['revision']} **{e['stage']} / {e['agent']}** `{e['action']}` "
                     f"{json.dumps(e['details'],ensure_ascii=True)}")
    (folder/"AGENT_TRACE.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    (folder/"METRICS.md").write_text(f"# Metrics: {run}\n\n```json\n{json.dumps(m,indent=2)}\n```\n",encoding="utf-8")
    (folder/"OUTCOME.md").write_text(f"# {run}\n\nState: `{s['state']}`. Revision: {s['revision']}. "
                                     f"Trace head: `{events[-1]['hash']}`. No hosted deployment.\n",encoding="utf-8")
    for stage in ("documentation","readiness"):
        if stage in s["done"]:
            value = store.get(s["done"][stage])
            if stage=="readiness":
                emit(folder/"release-readiness.json",value)
                if "review_evidence" in value:
                    proof = store.get(value["review_evidence"])
                    emit(folder/"pre-signoff-evidence.json",proof)
                    emit(folder/"pre-signoff-metrics.json",store.get(proof["metrics_hash"]))
            else:
                docs = folder/"generated"
                docs.mkdir()
                for name in ("README.md","OPENAPI.yaml","CHANGELOG.md","ADR.md"):
                    (docs/name).write_text(value[name],encoding="utf-8")
    return {"run":run,"state":s["state"],"folder":str(folder),"metrics":m}


def aggregate(store,path):
    runs = {run:metrics(store.history(run)) for (run,) in store.db.execute("SELECT id FROM runs ORDER BY id")}
    report = summarize(runs)
    with Path(path).open("x",encoding="utf-8") as out:
        json.dump(report,out,indent=2)
    return {"metrics":str(path),"runs":len(runs)}


def summarize(runs):
    durations = [v for m in runs.values() for v in m["recovery_durations_seconds"]]
    n = len(runs)
    stage_attempts = Counter()
    stage_passes = Counter()
    stage_times = Counter()
    for m in runs.values():
        for stage,time in m["stage_latency_seconds"].items():
            stage_attempts[stage] += time["attempts"]
            stage_times[stage] += time["total"]
            stage_passes[stage] += round(time["attempts"]*m["stage_success_rates"][stage])
    return {"runs":runs,"count":n,"release_rate":sum(m["released_at_least_once"] for m in runs.values())/n if n else None,
              "mean_retries_per_run":mean(m["retries"] for m in runs.values()) if n else None,
              "mean_rollbacks_per_run":mean(m["rollbacks"] for m in runs.values()) if n else None,
              "mean_end_to_end_seconds":mean(m["elapsed_seconds"] for m in runs.values()) if n else None,
              "stage_success_rates":{s:stage_passes[s]/a for s,a in stage_attempts.items()},
              "stage_mean_seconds":{s:stage_times[s]/a for s,a in stage_attempts.items()},
              "total_human_interventions":sum(m["human_interventions"] for m in runs.values()),
              "total_replans":sum(m["replans"] for m in runs.values()),"mttr_seconds":mean(durations) if durations else None}
