# Canopy engineering summary

## Engineering decision

The deliverable is a **Python control plane for software engineering** and a Java/Spring project registration, not a Java-only reactor. Python is the deliberate stack exception. The scheduler does not import a controller, know an HTTP route, or implement a project feature. Project manifests and versioned inputs identify the checkout, build adapter, contract and permitted changes. Maven is the first supported build adapter; another build ecosystem needs its own trusted tool integration.

The local model interface is optional. Deterministic workers, reviewed example packs, and external path-to-source proposals use identical approval and execution gates. Unlike a free-running chat agent, the model cannot choose commands, decide the release state, or change its own permissions.

## Artifacts and rationale

| Decision | Artifact / effect | Trade-off |
|---|---|---|
| Explicit graph, not prompt sequencing | [`sdlc_graph.py`](../engineering/sdlc_graph.py) declares dependencies, owners, tools, inputs and exit conditions. Only completed upstream artifacts enable work. | Adding an agent requires a registered tool and a deliberate graph/policy change. |
| Split working state from evidence | [`sdlc_store.py`](../engineering/sdlc_store.py) persists versioned state, content hashes, immutable artifacts and hash-chained events. | The operator owns the local filesystem; a hash chain is not independent notarization or authentication. |
| Verify before changing the checkout | Requirements, plan, executable candidate and release each require a digest-bound decision. QA and Security use independent temporary copies. | Tests and static analysis require Java/Maven; the first build downloads dependencies. |
| Protect known-good work | [`checkout.py`](../engineering/checkout.py) checks managed paths and conflicting edits. A late worker result cannot advance a stopped run. | Source rollback is not rollback of production traffic, schema or data. |
| Fail closed | Gate failures retain diagnostics and the current checkpoint. A recovery that follows QA or Security failure invalidates downstream work and needs a new plan approval. | Repeating a failed gate without fixing its cause will exhaust the retry budget. |
| Keep human and simulated decisions distinct | [`replay.py`](../engineering/replay.py) requires explicit demo authorization and confines decisions to isolated workspaces. | Passing a demonstration is not human approval to replace the previously accepted application. |

## Scenarios and validation

All three scenarios call the same CLI and workers. Greenfield starts empty. Brownfield uses the accepted greenfield snapshot, changes response caching and legacy HEAD semantics, then rolls back and compares the resulting checkout and stored hash. Ambiguous pauses for clarification, invalidates the first interpretation, then submits a protected-path change. The policy denial safe-stops the run; an explicit scoped repair triggers another plan and review. These are **simulated approval decisions**, not production approvals.

The persisted results are under [greenfield](../scenarios/greenfield/evidence/), [brownfield](../scenarios/brownfield/evidence/), and [ambiguous](../scenarios/ambiguous/evidence/). Each export includes trace, metrics, outcome, artifact summaries and, when released, generated documentation and the readiness decision. `qa` reports actual Surefire counts, JaCoCo covered/missed lines, and Checkstyle evidence. `security` reports the scanner invocation, report hash and reported findings. The static scan blocks its configured high-priority findings; it is not a claim that the service is free of vulnerabilities.

The Python regression suite exercises immutable audit events, stale approvals, graph joins, scoped tool denial, protected files, model fallback, retry exhaustion, re-planning, publishing and rollback without overwriting local edits. No model server is needed to reproduce these tests.

### Observed local results

| Run | Maven tests | JaCoCo line coverage | Outcome |
|---|---:|---:|---|
| Greenfield | 36 passed | 93.59% | Demo release from an empty checkpoint |
| Brownfield | 38 passed | 93.70% | Demo release, then exact byte-for-byte restoration of the greenfield checkpoint |
| Ambiguous | 36 passed | 93.59% | Two re-plans, one policy safe-stop and one authorized repair; demo release |

No Maven tests failed or skipped in these runs. Checkstyle passed and the configured static security gate reported zero blocking findings in each. [Current replay metrics](../scenarios/metrics.json) record the actual recovery interval under **simulated review**, not production incident recovery time. The platform suite also exercises clarification without prewritten criteria, work-package integrity, detection of open findings at readiness, and persistence of pre-signoff metrics. The historical application's root build remains available; use the `enhanced` reactor profile and `-pl :links-service` to verify the enhanced service.

## Application and operational boundaries

The enhanced [service input](../examples/projects/links-service/) uses Java 21, Spring Boot, versioned HTTP routes, durable allocation, token buckets, correlation IDs, Flyway migrations, optional Redis and a bounded process-local fallback. Redirects and stats retain database-backed accounting. [The service README](../examples/projects/links-service/README.md) describes the environment variables and optional Compose topology. H2 is the default tested local database. A source checkpoint is cheap to restore; a PostgreSQL upgrade requires separate backup, migration rehearsal and restore testing.

The [historical accepted checkout](../urlShortener/) is intentionally distinct. Its four documentation images show its own HTTP responses and tests, not the enhanced candidate's results. The legacy ledger and its approvals were not migrated or rewritten.

## Risks and follow-up

- **Isolation:** fixed commands, path checks and restricted environment variables limit the agent API, not what arbitrary compiled Java or Maven plugins can do. For untrusted proposals, supply ephemeral workers with resource, identity, network and filesystem isolation.
- **Trust:** risk acceptance is not a mechanism for bypassing a high/critical gate. [Signed workspaces](signed-review.md) verify possession of an explicitly enrolled review key. Separation of duties, enterprise identity, revocation, worker isolation and remote tamper-resistant retention remain operator responsibilities.
- **Coverage:** 80% line coverage is a floor, not proof of correct behavior. HTTP contract tests, database upgrade tests and fallback tests supplement it. The bundled replay does not run load, chaos, or live PostgreSQL/Redis acceptance tests.
- **Reproducibility:** dependency versions, wrapper checksum, fixture requests, control transitions and candidate content are inspectable. Timestamps, HTTP ports, measured durations, and generated IDs vary. A live model can vary too; the reviewed candidate hash, not the model's narrative, is authoritative.
- **Recovery:** regular exceptions unwind checkout writes. Hard process loss mid-publication is not an OS-level atomic directory transaction; retry or reconcile the exact checkpoint before continuing. Revision history and source rollback do not recover lost external data.
- **Service policy:** private literal IP and local-name filtering without DNS avoids sending network requests during shortening. It is not a DNS-rebinding defense for a separate crawler. Rate limits are per application instance. Distributed quotas, private-network deployment policy and external security review remain operational work.
