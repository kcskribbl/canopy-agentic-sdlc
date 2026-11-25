# Control-plane architecture

The boundary is between **creating a candidate**, **verifying it**, and **authorizing its publication**. Neither an AI response nor a successful Maven command is a release decision. A run can be resumed from local state without asking the model to reconstruct what happened.

| Component | Owns | Does not own |
|---|---|---|
| CLI / operator | Scenario selection, decisions, explicit recovery | Worker implementation or interpretation of test success |
| Scheduler | Eligibility, fork/join, durable transitions, revision invalidation | Java behavior, domain vocabulary, Maven plugin decisions |
| Workers | Artifact production and bounded tool invocation | Approval, checkout publication, mutable shared files |
| Store | Artifact identity, versioned decisions, checkpoints, append-only events | Reviewer identity, secrets management, hosting |
| Project registration | Build adapter, contract expectations, editable paths, trusted inputs | Policy exceptions, gate bypasses |
| Checkout publisher | Write accepted managed files and restore source checkpoints | Database migration rollback, deployment rollback |

### Extension contract

1. Register a project under `projects/` with an operator-controlled checkout name, pack locations, contract path, expected operations, editable path prefixes and allowed auxiliary files. The links manifest is a worked example, not scheduler configuration.
2. Provide deterministic inputs under `examples/projects/` and an acceptance scenario. Use an externally authored proposal or explicit loopback model for non-fixture code generation. Pin build dependencies and define executable tests tied to acceptance IDs.
3. Use the existing Maven verify/scan adapter if the project implements its evidence contract (Surefire XML, JaCoCo XML, Checkstyle XML, SpotBugs XML). For another stack, implement a bounded adapter: fixed command, timeout, allowed environment and structured evidence. Register its tool grant and add gate-failure tests; do not allow arbitrary commands in project data.
4. To extend the graph, declare a node with meaningful prerequisites, one owning worker, a named tool and measurable success criteria. Add independent branches only when their artifacts cannot interfere. A downstream node should require **both** branches if both attest its outcome.
5. Test stale decisions, failure, re-plan, exhaustion and rollback as well as a passing path. Demonstration approvals must be marked as simulation; real workspaces default to waiting for a human.

### Concrete lineage

There are two distinct dependency structures. The **lifecycle graph** schedules agents and approval gates. The **work plan** inside a design artifact groups the actual changed files into contract, persistence, configuration, application and test packages as applicable. It records prerequisites and assembles packages in topological order against the reviewed checkpoint. An omitted or duplicate file is an assembly failure. For brownfield review the design compares old/new OpenAPI operations and records references from affected classes to other application sources; these are aids to engineering review, not dynamic analysis.

Before asking for release sign-off, the control plane verifies the event chain, reads immutable artifacts, checks prior operator decisions and successful gate outputs, and stores the metrics **through documentation**. Readiness binds that evidence to the candidate, security findings and rollback checkpoint. Export writes the pre-signoff artifacts separately from the end-of-run metrics, which may include the release or a later rollback. See [REL-001](product/current/PRD.md) and the [operator guide](../README.md).

For a release, traverse `release_approval -> readiness -> qa/security -> implementation -> design -> requirements` via each `tool_requested.inputs` map and gate output hash. Read the recorded rationale for each `approved` event. Both quality reports carry the same candidate hash, and readiness names the parent checkpoint. `artifacts.json` includes test mappings, gate results and compact file hash manifests; full source content remains in the workspace object store. The trace's `previous` hash provides ordering and detects inconsistent edits during normal verification; it is not an external timestamp authority.
