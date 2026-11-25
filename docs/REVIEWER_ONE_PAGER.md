# Canopy | Engineering reviewer brief

**Canopy** is the fictional name of the agentic software engineering platform. **The URL Shortener is the first product built and verified through Canopy.** The platform turns a requirement into a reviewable software change: it decides what may run, what evidence is sufficient, and when a person must decide.

**Why “Canopy”?** The name gives reviewers a way to distinguish the platform from the products built with it. Think of one canopy over several projects: the URL Shortener and inventory service have different business rules, but both use the same approval, verification and recovery mechanisms. A redirect is a URL Shortener feature; stopping a release because QA failed is a Canopy feature.

Development used AI and API tooling with **GPT-6.2**. The reproducible local demonstrations do not require a model API key: they assemble reviewed inputs and run real builds, tests and scans.

## Requirements engineering: from intent to release

The URL Shortener is the target application; **Canopy's primary engineering challenge is deciding whether a proposed change satisfies the need that prompted it**. Canopy preserves the original request, records questions and measurable acceptance criteria, and asks the reviewer to approve that interpretation before planning.

**Example: checking a link is not the same as clicking it.** Suppose a short link has five recorded visits. An automated link checker uses the HTTP verb `HEAD` to ask, “Where would this link send me?” The service returns a redirect and its destination address, but the count should stay at **five**. Later, a reader clicks the link. The browser uses the HTTP verb `GET`, receives the same redirect, and the count should rise to **six**. Counting both requests would make an automated check look like reader traffic.

**How Canopy verifies the rule:** In the brownfield URL Shortener candidate, [acceptance criterion AC-002](../scenarios/brownfield/scenario.json) names a [regression test](../examples/projects/links-improvement/src/test/java/dev/canopy/links/ImprovementTest.java) that checks the redirect response and the count. The [QA report](../scenarios/brownfield/evidence/artifacts.json) lists that test as passed. This result applies to the brownfield candidate, not the standalone app. If an operator later revises what counts as a visit, Canopy keeps the original request for comparison and requires fresh approval of the revised criteria; the old passing test is not proof of the new rule.

The lifecycle has seven parts. The first three are documented product and engineering artifacts, not three separate agents: **(1) [Product intent](product/current/INTENT.md)** defines why the platform exists; **(2) [product requirements](product/current/PRD.md)** define observable outcomes; **(3) the [technical specification](../SPEC.md)** defines the run and review contract. For each workload, **(4) [architecture and planning](../engineering/work_plan.py)** turn approved criteria into dependent tasks; **(5) [governed agentic execution](../engineering/control.py)** assembles and authorizes a candidate; **(6) validation and quality assurance** test and scan that same candidate; and **(7) [release readiness](../scenarios/greenfield/evidence/release-readiness.json)** puts the results, documentation and rollback target before the final reviewer.

## Engineering goal and scope assumptions

**The goal is production-grade engineering work, not a claim of production readiness.** The review should assess design fundamentals, lifecycle orchestration, ownership of the resulting code and evidence, and whether decisions can be defended. Agents execute within defined autonomy boundaries; **humans own oversight, approvals and final quality**.

| Area | In scope | Outside this evaluation |
|---|---|---|
| Access and traffic | Canopy controls which tools agents can use and which changes require approval. | Service-user authentication and authorization, gateway policy, and production rate limiting or distributed quotas. A limiter in the enhanced workload is not a platform-wide guarantee. |
| Logging and telemetry | Local execution traces, gate metrics and the enhanced service's structured request-log example. | Fleet-wide log collectors, ingestion into tools such as Splunk, retention policies, dashboards and on-call alerting. |
| Build and delivery | Reproducible local builds, test and security gates, Docker Compose, and sign-off on a source snapshot. | Hosted CI/CD pipelines, cloud provisioning, production deployment, rollout monitoring and deployed-service rollback. |
| Reliability and durability | The URL Shortener's service-level needs: database-backed links and counters, transactional updates, and cache fallback. Canopy verifies recovery of managed source files. | End-to-end distributed-system guarantees: replication, regional failover, disaster recovery, backup/restore targets and availability under load. A source rollback does not restore a production database. |

## What was built and where it lives

- **Control plane** — [`engineering/`](../engineering/) contains a Python CLI, an explicit dependency graph, seven specialized workers and a SQLite store for versioned artifacts and decisions. [Project manifests](../projects/) define each workload; [policy](../policies/control.json) defines tool grants and change limits.
- **URL Shortener** — [`urlShortener/`](../urlShortener/README.md) is one Java 21 / Spring Boot JAR with API, service, persistence, analytics and cache packages. It creates, previews and redirects links and reports aggregate usage. A preview never counts as a visit; a redirect increments SQL even on a cache hit. The [OpenAPI contract](../urlShortener/openapi.yaml) describes its four endpoints.
- **Scenarios and documentation** — [`scenarios/`](../scenarios/) holds requirements, traces, metrics and outcomes. [`examples/projects/`](../examples/projects/) holds inputs for isolated builds, not live deployments. The [product intent and PRD](product/current/), [architecture](architecture.md) and [engineering summary](FINAL_ENGINEERING_SUMMARY.md) explain scope, decisions and limitations.

## Important diagrams

- **Canopy:** [Execution graph and approval gates](../README.md#execution-graph) · [Recovery loop](../README.md#state-recovery-and-evidence)
- **URL Shortener:** [Component architecture](../urlShortener/README.md#architecture-at-a-glance) · [Request sequence](../urlShortener/README.md#request-flow-and-core-logic)

## Three required demonstrations

Each run uses the same graph: **decompose** the approved requirement into dependent work packages, **orchestrate** their execution through approval gates, then **validate** the candidate against the acceptance criteria. What changes is the starting point: no accepted code, an existing product, or an intent too unclear to authorize work.

- **Greenfield / well-defined requirements:** Starting from an empty managed checkout, the [greenfield run](../scenarios/greenfield/evidence/artifacts.json) maps explicit acceptance criteria to tasks, files and tests. The candidate must demonstrate, for example, that a live link redirects, an unknown link returns `404`, and an expired link returns `410`. All 36 tests passed. This proves governed assembly and verification from reviewed inputs, not autonomous invention from prose.
- **Brownfield / enhancements, refactors and fixes:** The [planner](../engineering/work_plan.py) compares a proposed change with the accepted baseline: affected APIs, files, source dependencies and regression risk. The [recorded scenario](../scenarios/brownfield/scenario.json) prevents caching per-link statistics and fixes `HEAD` requests counting as visits. [Rollback evidence](../scenarios/brownfield/evidence/RESTORATION.md) shows exact restoration. Separately, the [standalone package layout](../urlShortener/README.md#project-layout) illustrates a refactor that retains the four-endpoint contract; it is not presented as that scenario's output.
- **Ambiguous requirements:** In the [ambiguous trace](../scenarios/ambiguous/evidence/AGENT_TRACE.md), an unclear request pauses for clarification. A later proposal touches a protected policy file and stops. A narrower revision returns through planning and approval; the run records **two re-plans and one authorized repair**, not an exception to policy.

**Additional brownfield evidence — tests and documentation:** In the Swagger/telemetry change, [two new tests failed on the baseline](../scenarios/observability-api-docs/evidence/red.txt). The [governed result](../scenarios/observability-api-docs/evidence/governed/) passed 38 tests, including serving the canonical OpenAPI document and emitting typed completion logs. The documentation stage exports the README, contract, changelog and decision record from the verified candidate.

## Developer and operational practices

- **Fast local loop:** From the repository root, `.\mvnw.cmd -f urlShortener\pom.xml clean verify` builds and tests without containers. H2 and a bounded Caffeine cache are the defaults. [Docker Compose](../urlShortener/compose.yaml) runs the same JAR with PostgreSQL and Redis. JUnit and Karate cover behavior through the HTTP boundary.
- **Application telemetry:** The enhanced Swagger workload logs correlation ID, numeric HTTP status and duration without raw request data. This is distinct from the standalone app's framework logs and from the platform's decision audit trail.

---

## Workflow orchestration: who decides what can happen next?

The [dependency graph](../engineering/sdlc_graph.py), not an individual agent, owns execution order. Each node declares its owner, required upstream artifacts, permitted tool, output and exit condition. The [scheduler](../engineering/control.py) persists progress in SQLite. Sequential approvals, a parallel branch with a required join, and feedback after failure make this more than a task list.

**[Execution graph table](https://github.com/kcskribbl/canopy-agentic-sdlc/blob/15434d6f985793f49154eb4e6bedfc43824c9dcf/README.md?plain=1#L218-L230)** — all 11 stages, with each entry gate, enforced exit condition and recorded example.

| Human checkpoint | What the reviewer must judge | What approval permits |
|---|---|---|
| Requirements | Is the intent clear? Are assumptions acceptable and outcomes measurable? | Plan against this interpretation. If not, clarify and revise. |
| Architecture and plan | Is the API/schema change necessary? Are dependencies, affected files, risk and rollback scope understood? | Assemble the reviewed diff against the named baseline; do not publish it. |
| Execution | Is this exact candidate safe to build and test in the chosen environment? | Run **QA and security in parallel**. A pass in one branch cannot override a failure in the other. |
| Release readiness | Did both branches verify the same candidate? Are the docs, approvals, metrics and rollback target present? | Publish the local snapshot, or reject it. This is not a production deployment. |

### Quality gates, feedback loops and controls

- **Evidence, not self-attestation:** QA reads Maven test results, criterion-to-test mappings, JaCoCo coverage and Checkstyle output. Security checks source policy and SpotBugs/FindSecBugs results; a blocking high/critical finding cannot be waived at sign-off. Only after both branches pass may documentation run. Missing or blank review files block readiness.
- **Controlled recovery:** If optional local model inference fails, the planner records a fallback to reviewed deterministic inputs; it does not skip review. A failed gate safe-stops the run and preserves its checkpoint. An operator can authorize repair, revise the scope or stop. Recovery from failed design, implementation, QA or security invalidates downstream work and requires new plan and execution approvals. Changing the requirement reopens requirements review. The budget is **three repairs per run**; exhaustion requires a reviewed successor.
- **Security, compliance and change control:** Named tools and fixed Maven commands limit agent actions. [Policy](../policies/control.json) blocks selected secret and unsafe logging patterns and limits files, changed lines and input size. A reviewer approves a specific digest and supplies a rationale; [optional signed approvals](signed-review.md) bind that decision to an enrolled key. These are local controls, not compliance certification, enterprise identity or a hardened build sandbox.
- **Traceability and metrics:** The hash-chained event log records the run, revision, stage, actor, tool, upstream hashes, outcome and rationale. The release reviewer can inspect [what was known before sign-off](../scenarios/greenfield/evidence/pre-signoff-evidence.json). [Reliability reports](../scenarios/metrics.json) track stage and run success, retry and rollback frequency, re-plans, interventions, latency and time from gate failure to recovery. Local hash chaining makes changes detectable; it is not external tamper-proof retention.

