"""Deterministic engineering workers and a bounded handoff for externally authored code."""
import difflib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import yaml

from sdlc_store import sha
import work_plan
import reviewed_patch

ROOT = Path(__file__).resolve().parents[1]


class GateError(ValueError):
    def __init__(self, message, evidence=None):
        super().__init__(message)
        self.evidence = evidence or {}


def require(condition, message):
    if not condition:
        raise GateError(message)


def safe_key(key):
    p = PurePosixPath(key)
    return (not p.is_absolute() and p.as_posix() == key and not any(
        x in {"", ".", ".."} or x.startswith(".git") or not re.fullmatch(r"[a-zA-Z0-9._-]+", x) for x in p.parts))


def read_pack(rel, cfg, policy):
    folder = (ROOT / rel).resolve()
    require(folder.is_relative_to(ROOT / "examples" / "projects") and folder.is_dir(), "Project input pack unavailable")
    files = {}
    for path in folder.rglob("*"):
        key = path.relative_to(folder).as_posix()
        if "target" in path.relative_to(folder).parts or not path.is_file():
            continue
        if key != "pom.xml" and not key.startswith("src/") and key not in cfg["extra_files"]:
            continue
        require(safe_key(key) and path.resolve() == path and path.stat().st_size <= policy["max_file_bytes"],
                "Unapproved or oversized pack file: " + key)
        files[key] = path.read_text(encoding="utf-8")
    require(files, "Project pack has no deliverable inputs")
    return files


def config(project):
    require(re.fullmatch(r"[a-z][a-z0-9-]{0,40}", project), "Invalid project identifier")
    path = ROOT / "projects" / (project + ".json")
    require(path.is_file(), "No registered project: " + project)
    cfg = json.loads(path.read_text(encoding="utf-8"))
    require(re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", cfg["checkout"]) and cfg["build"] == "maven",
            "Unsupported checkout or build adapter")
    return cfg


def normalize(ctx, inputs):
    spec = ctx["scenario"]
    request = spec["request"].strip()
    criteria = spec.get("criteria", [])
    require(request and isinstance(criteria, list) and all(isinstance(s, str) and s.strip() for s in criteria),
            "Expected a requirement and a list of acceptance criteria")
    vague = re.search(r"\b(better|safer|faster|improve|optimize|enhance)\b",request,re.I)
    observable = re.search(r"\b(return|reject|count|create|redirect|limit|inspect|report|record|prevent|fix)\w*\b",
                           request,re.I)
    source = "scenario or operator"
    if not criteria:
        # Keep the operator's wording. Do not invent acceptance thresholds from vague intent.
        criteria = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", request) if
                    re.search(r"\b(return|respond|reject|redirect|limit)\w*\b",s,re.I) and
                    re.search(r"\b(?:[1-5]\d{2}|\d+\s+(?:requests?|seconds?|visits?))\b",s,re.I)]
        source = "proposed from observable request clauses" if criteria else "unresolved"
    unclear = not criteria or (vague and not observable) or (spec["kind"] == "ambiguous" and ctx["revision"] == 1)
    return {"original": spec.get("original", request), "intent": request, "questions":
            ["Which behavior, boundary and measurable outcome should the implementation target?"] if unclear else [],
            "assumptions": ["Local verification only; release sign-off does not deploy the application."],
            "criteria_source":source, "criteria": {f"AC-{i:03d}": s for i, s in enumerate(criteria, 1)}}


def local_proposal(config, spec, sources):
    """Local OpenAI-compatible inference only. No shell, tools, credentials or remote URLs."""
    messages = [{"role":"system","content":
        "You are Canopy's coding agent. Return one JSON object mapping changed src/main/java or new src/test/java "
        "paths to full Java source. Preserve existing behavior and trusted tests. No shell, tools, dependencies, "
        "secrets or configuration edits. Return {} if the proposed implementation already meets the criteria."},
        {"role":"user","content":json.dumps({"intent":spec["request"],"criteria":spec["criteria"],
                                            "candidate_sources":sources},ensure_ascii=True)}]
    conn = http.client.HTTPConnection("127.0.0.1",config["port"],timeout=45)
    try:
        conn.request("POST","/v1/chat/completions",json.dumps({"model":config["name"],"messages":messages,
                     "temperature":0,"max_tokens":4096}),{"Content-Type":"application/json"})
        response = conn.getresponse()
        require(response.status == 200,"Local inference server returned HTTP "+str(response.status))
        body = response.read(150001)
        require(len(body)<=150000,"Model response exceeds limit")
        value = json.loads(json.loads(body)["choices"][0]["message"]["content"])
        require(isinstance(value,dict),"Invalid coding agent response")
        return value
    finally:
        conn.close()


def design(ctx, inputs):
    spec, cfg, policy, base = (ctx[k] for k in ("scenario", "config", "policy", "baseline"))
    brown = spec["kind"] == "brownfield"
    require(bool(base) == brown, "Scenario baseline mismatch; select empty workspace or its accepted project")
    patch = spec.get("reviewed_patch")
    if patch is not None:
        require(brown and isinstance(patch,str) and patch in cfg.get("reviewed_patches",{})
                and "proposal" not in spec and "local_model" not in spec,
                "Unregistered or ambiguous reviewed patch")
        changes = reviewed_patch.load(ROOT,cfg["reviewed_patches"][patch],base,policy["max_file_bytes"])
    else:
        changes = read_pack(cfg["improvement" if brown else "blueprint"], cfg, policy)
    proposal = spec.get("proposal", {})
    mode, fallback = ("pinned external engineering change: "+patch if patch else "deterministic"), None
    if "local_model" in spec:
        cfg_model = spec["local_model"]
        require("proposal" not in spec, "Cannot mix model and supplied proposal")
        try:
            proposal = local_proposal(cfg_model,{**spec,"request":spec["request"] + (
                "\nQuality gate feedback: "+json.dumps(ctx["feedback"]) if ctx.get("feedback") else "")},{p:v for p,v in {**base,**changes}.items()
                                                     if p.startswith("src/main/java/")})
            mode = "local inference"
        except (OSError, http.client.HTTPException, ValueError, IndexError, KeyError) as err:
            fallback = f"{type(err).__name__}: inference unavailable or invalid; selected reviewed deterministic inputs"
    elif proposal:
        mode = "external proposal"
    require(isinstance(proposal, dict), "Expected a path-to-source proposal object")
    for path, content in proposal.items():
        require(safe_key(path) and path.startswith(tuple(cfg["editable_prefixes"])) and isinstance(content, str)
                and len(content.encode()) <= policy["max_file_bytes"], "Policy denied proposal path or size: " + path)
        require(not (path.startswith("src/test/") and path in (base.keys() | changes.keys())),
                "Policy denied modification of trusted regression suite: " + path)
        changes[path] = content
    files = {**base, **changes}
    delta = {p: text for p, text in changes.items() if base.get(p) != text}
    require(0 < len(delta) <= policy["max_files"], "No changes or file budget exceeded")
    changed = sum(1 for p, s in delta.items() for line in difflib.ndiff(base.get(p, "").splitlines(), s.splitlines())
                  if line.startswith(("+ ", "- ")))
    require(changed <= policy["max_changed_lines"], "Changed-line budget exceeded")
    contract = yaml.safe_load(files[cfg["contract"]])
    require(isinstance(contract, dict) and str(contract.get("openapi", "")).startswith("3.")
            and all(isinstance(contract.get("paths", {}).get(p), dict) for p in cfg["required_routes"]),
            "OpenAPI version or required operation paths missing")
    routes = {route: sorted(op for op in verbs if op in {"get", "post", "put", "patch", "delete", "head"})
              for route, verbs in contract["paths"].items()}
    require(all(routes[p] for p in cfg["required_routes"]), "Empty required OpenAPI path")
    tasks, impact = work_plan.build(files,base,delta,cfg["contract"],inputs["requirements"]["criteria"])
    return {"checkpoint": sha(base), "changes": delta, "lines": changed, "routes": routes,
            "schema": sorted(p for p in files if p.endswith(".sql")), "requirement_ids": list(inputs["requirements"]["criteria"]),
            "impact": impact,
            "source": mode, "fallback": fallback, "repair_feedback":ctx.get("feedback"),
            "tasks": tasks}


def compose(ctx, inputs):
    plan = inputs["design"]
    require(sha(ctx["baseline"]) == plan["checkpoint"], "Design checkpoint mismatch")
    return {"files": work_plan.assemble(ctx["baseline"],plan["changes"],plan["tasks"]), "checkpoint": plan["checkpoint"]}


def maven(work, goals):
    wrapper = ROOT / ("mvnw.cmd" if os.name == "nt" else "mvnw")
    cmd = [str(wrapper), "-B", "-ntp", "-f", str(work / "pom.xml"), *goals]
    keep = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "JAVA_HOME", "USERPROFILE", "HOME", "TEMP",
            "TMP", "HOMEDRIVE", "HOMEPATH", "LOCALAPPDATA", "APPDATA", "PROGRAMFILES", "PROGRAMDATA", "SYSTEMDRIVE",
            "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS"}
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    result = subprocess.run(cmd, cwd=work, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, errors="replace", timeout=600)
    if result.returncode:
        errors = [s for s in result.stdout.splitlines() if "[ERROR]" in s or "[WARNING]" in s]
        raise GateError("Maven gate failed", {"exit": result.returncode, "goals": goals,
                                             "diagnostic": "\n".join(errors[-22:])[-5000:]})
    return {"exit": 0, "goals": goals, "output_hash": sha(result.stdout)}


def verify(ctx, inputs, security):
    files = inputs["implementation"]["files"]
    with tempfile.TemporaryDirectory(prefix="canopy-gate-") as tmp:
        work = Path(tmp)
        for key, text in files.items():
            require(safe_key(key), "Invalid materialization path")
            path = work / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode())
        if security:
            findings = []
            for rule in ctx["policy"].get("blocked_source_patterns",[]):
                for path, text in files.items():
                    if path.startswith("src/main/") and re.search(rule["expression"],text):
                        findings.append({"rule":rule["id"],"severity":rule["severity"],"path":path})
            evidence = maven(work, SECURITY_GOALS)
            report = work / ".canopy" / "security" / "target" / "spotbugsXml.xml"
            require(report.is_file(), "Security scanner emitted no XML")
            xml = ET.parse(report).getroot()
            require(xml.tag == "BugCollection" and xml.find("FindBugsSummary") is not None, "Invalid scanner evidence")
            findings.extend({"rule": b.get("type"), "severity": {"1":"high","2":"medium","3":"low"}.get(b.get("priority"), "high")}
                            for b in xml.iter("BugInstance"))
            if any(f["severity"] in ctx["policy"]["blocked_severities"] for f in findings):
                raise GateError("Security policy blocks release", {"findings": findings})
            evidence.update(findings=findings, scanner_report=sha(report.read_bytes().hex()))
        else:
            evidence = maven(work, ["clean", "verify"])
            counts = {k: 0 for k in ("tests", "errors", "failures", "skipped")}
            passing = set()
            for path in (work / "target" / "surefire-reports").glob("TEST-*.xml"):
                suite = ET.parse(path).getroot()
                for k in counts:
                    counts[k] += int(suite.attrib.get(k, 0))
                passing.update(t.get("classname","").rsplit(".",1)[-1]+"."+t.get("name","").split("(",1)[0].split("[",1)[0]
                               for t in suite.iter("testcase") if not any(t.find(tag) is not None for tag in ("failure","error","skipped")))
            require(counts["tests"] > counts["skipped"] and not counts["failures"] and not counts["errors"], "No passing test evidence")
            coverage = ET.parse(work / "target" / "site" / "jacoco" / "jacoco.xml").getroot()
            line = next((c for c in coverage.findall("counter") if c.get("type") == "LINE"), None)
            require(line is not None, "No line coverage evidence")
            lint = ET.parse(work / "target" / "checkstyle-result.xml").getroot()
            require(lint.tag == "checkstyle" and not list(lint.iter("error")), "Missing or non-clean lint evidence")
            mapping = ctx["scenario"].get("acceptance_tests",{})
            if mapping:
                require(set(mapping) == {f"AC-{i:03d}" for i in range(1,len(ctx["scenario"]["criteria"])+1)}
                        and all(isinstance(tests,list) and tests and set(tests)<=passing for tests in mapping.values()),
                        "A named acceptance test was missing, skipped or failed")
            evidence.update(counts=counts, coverage={k:int(line.get(k)) for k in ("covered","missed")}, lint="clean",
                            passing_tests=sorted(passing), acceptance_tests=mapping)
        return {**evidence, "candidate": sha(files)}


SECURITY_GOALS = ["-Psecurity", "clean", "compile", "com.github.spotbugs:spotbugs-maven-plugin:4.9.4.0:check"]


def document(ctx, inputs):
    plan = inputs["design"]
    files = inputs["implementation"]["files"]
    return {"README.md": f"# {ctx['scenario']['project']}\n\n{inputs['requirements']['intent']}\n\nBuild the approved checkout with the Maven wrapper and `clean verify`.\n",
            "OPENAPI.yaml": files[ctx["config"]["contract"]],
            "ADR.md": f"# Release decision\n\nRetain the accepted checkpoint `{plan['checkpoint']}` until sign-off. "
                      f"Test and scan isolated copies of `{sha(files)}`; failed candidates never replace the checkpoint.\n",
            "CHANGELOG.md": "# Reviewed changes\n\n" + "\n".join("- " + p for p in sorted(plan["changes"])),
            "requirements": list(inputs["requirements"]["criteria"]), "verification": inputs["qa"], "security": inputs["security"]}


def checklist(ctx, inputs):
    target = sha(inputs["implementation"]["files"])
    require(target == inputs["qa"]["candidate"] == inputs["security"]["candidate"], "Independent gates checked different candidates")
    findings = inputs["security"].get("findings")
    require(isinstance(findings,list) and all(f.get("severity") in {"low","medium","high","critical"} and
            f["severity"] not in ctx["policy"]["blocked_severities"] for f in findings), "Missing or blocking security disposition")
    require(ctx.get("review_evidence") and ctx.get("baseline") is not None and
            sha(ctx["baseline"]) == inputs["implementation"]["checkpoint"], "Missing evidence or rollback checkpoint")
    return {"candidate": target, "passed": True, "docs": sha(inputs["documentation"]),
            "review_evidence":ctx["review_evidence"], "security_disposition":{"blocking":0,"reported":len(findings)},
            "rollback_to": inputs["implementation"]["checkpoint"], "deployment": "none",
            "controls": ["requirements and plan approved", "authorized candidate verified and scanned", "documentation generated"],
            "remaining_decision": "Final human release-readiness sign-off"}


WORKERS = {"normalize": normalize, "inspect_project": design, "compose_candidate": compose,
           "maven_verify": lambda c, i: verify(c, i, False), "security_scan": lambda c, i: verify(c, i, True),
           "render_docs": document, "release_checklist": checklist}
