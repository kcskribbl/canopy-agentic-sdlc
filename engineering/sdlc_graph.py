"""The reusable execution graph. Dependencies refer to successful artifact producers."""
from dataclasses import dataclass
from graphlib import TopologicalSorter


@dataclass(frozen=True)
class Node:
    id: str
    inputs: tuple
    owner: str
    tool: str
    output: str
    exit_gate: str


def human(name, upstream, decision):
    return Node(name, (upstream,), "Human", "", "approval", decision)


NODES = [
    Node("requirements", (), "Requirements Analyst", "normalize", "requirements", "Explicit criteria and no unresolved ambiguity"),
    human("requirements_approval", "requirements", "Approve requirements and assumptions"),
    Node("design", ("requirements", "requirements_approval"), "Architect", "inspect_project", "design", "Contract, schema, risks and candidate diff reviewed"),
    human("plan_approval", "design", "Authorize scoped implementation against checkpoint"),
    Node("implementation", ("design", "plan_approval"), "Coder", "compose_candidate", "candidate", "Only the reviewed change set"),
    human("execution_approval", "implementation", "Authorize local tools on exact candidate"),
    Node("qa", ("implementation", "execution_approval"), "QA", "maven_verify", "verification", "Tests, coverage and style gates pass"),
    Node("security", ("implementation", "execution_approval"), "Security and Compliance", "security_scan", "findings", "No blocking findings; scanner succeeds"),
    Node("documentation", ("requirements", "design", "implementation", "qa", "security"), "Technical Writer", "render_docs", "documentation", "Generate evidence-linked release notes, contract and ADR"),
    Node("readiness", ("documentation", "qa", "security", "implementation"), "Release Reviewer", "release_checklist", "readiness", "Independent gates attest the same candidate; recovery checkpoint exists"),
    human("release_approval", "readiness", "Human signs off on release readiness"),
]
GRAPH = {n.id: n for n in NODES}
TopologicalSorter({n.id: n.inputs for n in NODES}).prepare()


def ready(done):
    return [n for n in NODES if n.id not in done and set(n.inputs) <= done.keys()]
