# Canopy control plane: local acceptance specification

Canopy drives a project adapter from a request to a reviewable local release. A **release** means changing the workspace's accepted product snapshot. It does not mean deploying a web service. A run's approval digest identifies the material under review; it is not proof of reviewer identity or the digest of the accepted product.

## Run and review contract

Start a run with `python engineering/control.py --workspace <directory> run <id> <scenario-json-file>`. Inputs name a project, kind and request. Acceptance criteria can start empty; missing measurable outcomes must not authorize design. The link-service fixtures use `project: "links"`. The ambiguous fixture holds the **future simulated reply** in `clarification` and `clarified_criteria`; the analyst must not use those fields to bypass the first pause. The replay supplies the criteria only at revision time through repeated `--criterion` arguments. See the [product intent](docs/product/current/INTENT.md) and [PRD](docs/product/current/PRD.md) for the product-level requirements.

The requirements analyst captures intent and requirements; the architect inspects the baseline and plans the change; the coder prepares the candidate. QA and security must evaluate the candidate before release readiness. Documentation and readiness review consume that evidence. Requirements, plan, execution and release decisions belong to explicit review gates. A gate acknowledgement is not itself a command to execute the next stage.

| Reported state | Permitted action in the replay |
|---|---|
| `pending` | `resume <id>` |
| `awaiting_approval` | Inspect the current gate and digest. Only in authorized simulation, `approve <id> <digest> <fixture reason>`, then resume. |
| `needs_clarification` | `revise <id> <clarified request> <reason>` exactly once in the ambiguous fixture |
| `safe_stop` | Recover only the expected protected-path denial: remove that proposed change, revise with explicit rationale, review the new plan and resume. All unexpected stops fail the replay. |
| `released` | Export evidence; the brownfield run additionally requests `rollback <id> <reason>`. |
| `rolled_back` | Verify restoration and export the final brownfield history. |
| `rejected` | Stop and report the failure. |

Use `status <id>` for inspection. The normal control CLI does not grant default approvals. Reviewers should inspect the actual artifacts and authorize only the displayed digest. Fixture decisions are not evidence of human review, production readiness, or deployment.

`inspect <id> design` must show work packages, their prerequisites, and file ownership. Readiness must bind the QA and security evidence to the same candidate and generate a pre-signoff metrics artifact and verified trace reference. A post-run metrics export is not a substitute for that pre-decision evidence.

## Executable acceptance cases

| Input | Starting point | Expected observations |
|---|---|---|
| [Greenfield](scenarios/greenfield/scenario.json) | Empty workspace | Release a link service with create, redirect, expiry, statistics and health behavior; record its accepted product hash. |
| [Brownfield](scenarios/brownfield/scenario.json) | Same workspace, greenfield accepted | Protect per-link statistics against caching; fix legacy HEAD counting a visit. Release changes the accepted product hash. Rollback restores the exact greenfield hash in the accepted-product store and the original files byte-for-byte in the checkout. |
| [Ambiguous](scenarios/ambiguous/scenario.json) | Separate empty workspace | Pause for clarification. After requirements approval, the architect must deny the proposed change to a protected policy file. Revise to remove it, approve again, and resume to release without modifying policy. |

From the project root:

```powershell
python -B engineering\replay.py --authorize-demo
```

Only the replay simulates decisions; each reason marks itself as a fixture, not a human decision. It allocates fresh workspaces under `scenarios/.replay-*`, never selects an existing accepted workspace, and invokes the real control CLI. Set `--deadline-seconds N` to change the total time budget (default: 1800 seconds). An unexpected state, exhausted time or transition budget, unsuccessful command, incomplete export, or baseline mismatch fails the run.

After a successful replay, each `scenarios/<kind>/evidence/` contains the CLI-exported `AGENT_TRACE.md`, `OUTCOME.md`, `metrics.json`, and `METRICS.md`. In these exports, “human interventions” counts events assigned to the human gate role; fixture acknowledgements are **not human decisions**. Brownfield also retains its release-time export in `before-rollback/` and measured hashes in `RESTORATION.md`. A failed run exits nonzero and prints the retained workspace, command transcripts, and partial export location. Existing evidence is not refreshed by an incomplete scenario. These are acceptance conditions and output locations, not claims that a run has passed.
