# Product intent: Canopy - Agentic AI

**Status:** Current working intent for review, not a recorded approval. The [historical scope](../history.md) describes the initial link service; its original local records remain unchanged. This document describes the **engineering platform** that builds and verifies a project.

## Original requirement and interpretation

> Build a working prototype that transforms a requirement into a reviewable engineering outcome using an agentic execution model.

The central problem is not how to generate a short URL. It is how an engineering owner can tell **what an agent understood, what it changed, why it was allowed to act, and whether the change is ready to accept**. The URL shortener makes those questions observable through an API contract, data migrations, tests and a recoverable source checkpoint.

## Users, outcomes and boundaries

| Stakeholder | Objective | Observable outcome |
|---|---|---|
| Product owner | Clarify an incomplete request without losing its original wording. | Review proposed acceptance criteria and approve the interpretation, or send it back. |
| Engineer | Evaluate a plan against real code before authorizing execution. | See dependent work packages, exact proposed files, affected endpoints and regression risks. |
| Release reviewer | Decide from evidence rather than an agent's assurance. | Inspect candidate-matched QA and security results, the audit trace, metrics through documentation and the rollback checkpoint before sign-off. |
| Service user | Create and resolve durable short links and understand their usage. | Exercise the versioned create, redirect and stats APIs of the example project. |

**Scope:** Greenfield, brownfield and ambiguous work; implementation, tests and documentation; a persistent Python control plane and a Java/Spring project adapter. Agents may work independently inside policy. Humans own consequential approvals and final quality.

**Out of scope:** Unsupervised production deployment, authenticated enterprise release authority, arbitrary repository modification, and a claim that deterministic fixture assembly is unrestricted code synthesis. A local release changes an accepted source snapshot, not a running service.

## Assumptions, ambiguities and measures

- The platform may start without acceptance criteria. A clearly measurable clause can become a **proposed** criterion; otherwise a reviewer must clarify it. A worker must not silently invent thresholds.
- Architectural impact from the current Maven adapter is static evidence. A class reference is not proof of a runtime call or data flow.
- Success means all three scenarios traverse the same graph with their distinct decisions visible: greenfield creates a checkout; brownfield changes and restores it; ambiguous work stops, is clarified or repaired, and resumes under fresh approval.
- Before using Canopy for hosted releases, ownership must be decided for authenticated approvals, isolated build workers, operational database recovery, and external evidence retention. The local prototype does not resolve those questions.

See the [current PRD](PRD.md) for acceptance measures and the [executable specification](../../../SPEC.md) for the scenario inputs.
