"""Offline requirements analyst for Canopy's bounded product vocabulary."""
from hashlib import sha256


def section(title, text):
    return f"## {title}\n\n{text}\n\n"


def intent(run, rev, original, request, feature, goal):
    creation = feature in {"create-redirect", "full-product"}
    analytics = feature in {"analytics", "full-product"}
    scope = []
    if creation:
        scope.append("Create shareable short links and redirect visitors to their stored destinations.")
    if analytics:
        scope.append("Give the operator aggregate totals for created links and committed redirects.")
    # Blockquote every line so embedded headings cannot become analyst-authored sections.
    quote = lambda value: "\n".join("> " + line for line in value.split("\n"))
    text = f"# Canopy product intent\n\nRun `{run}`, revision {rev}. Source SHA-256: `{sha256(original.encode()).hexdigest()}`.\n\n"
    text += section("Original requirement", quote(original))
    if request != original:
        text += section("Current clarification or revision", quote(request))
    if feature == "expansion-contract":
        sections = [
            ("Problem statement", "People cannot inspect where a short link leads without initiating a counted redirect."),
            ("Business context", "The accepted service already creates links, redirects visitors, and reports aggregate totals."),
            ("Product vision", "Let a reader make an informed choice before following a link."),
            ("Target users and stakeholders", "Readers preview destinations; operators rely on accurate totals; maintainers review contract evidence."),
            ("Business objectives", "Expose the saved destination without turning previews into traffic."),
            ("Expected outcomes", "Known codes return the exact saved URL as JSON. Unknown codes return not found."),
            ("Scope", "Add read-only link expansion and Karate scenarios for successful and missing previews, counter invariants, and compatibility with actual redirects."),
            ("Out of scope", "Expiry, per-link analytics, schema migration, deployment and changes to existing routes."),
            ("Constraints", "Never fetch destinations. Run HTTP tests against an isolated loopback service and disposable data."),
            ("Assumptions", "A caller who has the code may preview it. No authentication change is proposed."),
            ("Known ambiguities", "Preview is a lookup, not a destination safety or availability check."),
            ("Open questions", "Confirm that returning the exact stored URL to code holders is acceptable."),
            ("Success measures", "Repeated and missing previews add zero redirects; following the same link adds one. Karate verifies these outcomes over HTTP."),
        ]
        return text + "".join(section(title, body) for title, body in sections)
    sections = [
        ("Problem statement", goal if feature else "The requested outcome is not yet specific enough to plan."),
        ("Business context", "Canopy's first product supports sharing links. No customer research, revenue target or adoption baseline was supplied."),
        ("Product vision", "A publisher can share a short reference and a visitor can reliably reach its destination."
         if creation else "Give the operator useful aggregate feedback without identifying visitors." if analytics else "Pending clarification."),
        ("Target users and stakeholders", "Link publishers, visitors and the product owner; the operator reviews aggregate behavior."),
        ("Business objectives", "Reduce friction in sharing destinations." if creation and not analytics else
         "Make link usage visible without visitor-level tracking." if analytics and not creation else
         "Enable link sharing and aggregate usage reporting." if feature else "Confirm the business objective with the owner."),
        ("Expected outcomes", "\n".join("- " + s for s in scope) or "No implementation outcome authorized."),
        ("Scope", goal if feature else "Discovery only."),
        ("Out of scope", "Hosted deployment, individual visitor profiles, authentication and performance guarantees are not inferred from this request."),
        ("Constraints", "Local prototype; human ownership of scope and final quality. Do not fetch destinations or collect visitor identifiers."),
        ("Assumptions", "The first project is the Canopy URL shortener. The interpretation above is proposed, not a quotation or approval."),
        ("Known ambiguities", "No additional supported behavior inferred; confirm the proposed scope matches the source."
         if feature else goal),
        ("Open questions", "Does the owner accept these boundaries, or should the request be revised?" if feature else goal),
        ("Success measures", ("A valid link returns the exact destination; invalid or unknown inputs do not redirect. " if creation else "") +
         ("Two successful redirects add two to the aggregate; reading totals does not change them." if analytics else "")
         if feature else "Owner specifies an observable outcome and acceptance measure."),
    ]
    return text + "".join(section(title, body) for title, body in sections)


# IDs are stable product-wide; repeated PRDs refer to the same capability.
# id, priority, prerequisites, requirement, acceptance
CREATE = [
    ("FR-001", "Must", "-", "A publisher can create a short link.", "Submitting a valid HTTPS destination returns a new short reference."),
    ("FR-002", "Must", "FR-001", "A visitor can follow a known link.", "The redirect points to the exact stored destination; an unknown reference returns not found."),
    ("NFR-001", "Must", "FR-001", "Links survive a service restart.", "After restarting with the same store, a previously issued link still redirects."),
    ("BR-001", "Must", "FR-001", "A new reference never replaces an existing link.", "A collision does not overwrite the original destination."),
    ("SEC-001", "Must", "FR-001", "Only absolute HTTP(S) destinations with a host are accepted.", "A relative path or non-web scheme is rejected without creating a link."),
]
STATS = [
    ("FR-003", "Must", "Baseline create/redirect", "An operator can read aggregate link and redirect totals.", "After creating one link and following it twice, totals increase by one link and two redirects."),
    ("NFR-002", "Must", "FR-003", "Concurrent redirects do not lose increments.", "N successful concurrent redirects increase the total by N."),
    ("BR-002", "Must", "FR-003", "Only committed redirect decisions count.", "Unknown codes and reads of totals leave the count unchanged."),
    ("SEC-002", "Must", "FR-003", "Analytics does not expose visitor identity or destinations.", "The aggregate response contains counts only."),
]


def prd(run, rev, feature, goal, approved_intent):
    if feature == "expansion-contract":
        return (f"# Canopy link preview requirements\n\nSource: approved [INTENT.md](INTENT.md), `{run}` revision {rev}, `{approved_intent}`.\n\n"
                + section("Product overview", goal)
                + section("User personas", "Reader inspecting a short link; operator interpreting totals; maintainer checking compatibility.")
                + section("User journeys", "Create a link, inspect its destination, then decide whether to follow it.")
                + section("Functional requirements", "**FR-004**: A code holder can look up a destination without redirecting. Unknown codes return 404.")
                + section("Non-functional requirements", "**NFR-004**: Independently repeatable Karate scenarios exercise the observable API over loopback HTTP.")
                + section("Business rules", "**BR-003**: Neither successful nor unsuccessful previews count as visits.")
                + section("User stories", "As a reader I can inspect a destination before navigation (FR-004). As an operator I can distinguish visits from previews (BR-003).")
                + section("Security and compliance requirements", "**SEC-003**: Read only the stored URL; never contact the destination or disclose other links.")
                + section("Acceptance criteria", "- FR-004: GET /api/links/{code} returns 200 with only `url` for a known code, or 404 for an unknown code.\n- BR-003: Two previews and a miss leave totals unchanged; one actual redirect adds one.\n- NFR-004: The standard Maven verification executes tagged HTTP scenarios against a fresh service and in-memory database.\n- SEC-003: An unreachable destination is returned verbatim without navigation or Location header.")
                + section("Priority and dependencies", "All Must. FR-004 depends on accepted link creation; BR-003 on FR-004 and aggregate totals; SEC-003 and NFR-004 on FR-004.")
                + section("Failure scenarios", "Unknown code: 404. Storage failure: 503, not a false 404 or redirect.")
                + section("Out-of-scope requirements", "No schema change, expiry, hosted deployment or new analytics.")
                + section("Open questions and assumptions", "Possession of the code permits preview. No change to existing access policy."))
    records = ((CREATE if feature != "analytics" else []) + (STATS if feature != "create-redirect" else [])
               + [("NFR-003", "Must", "-", "A storage failure must not be reported as success.",
                   "If storage is unavailable, the operation returns a failure instead of issuing a link or redirect.")])
    stats = feature != "create-redirect"
    create = feature != "analytics"
    text = f"# Canopy product requirements\n\nSource: approved [INTENT.md](INTENT.md), `{run}` revision {rev}, intent digest `{approved_intent}`.\n\n"
    text += section("Product overview", goal)
    text += section("User personas", ("- Publisher: needs a shareable reference.\n- Visitor: follows a published link.\n" if create else "") +
                    ("- Operator: checks aggregate usage without tracking individuals." if stats else "- Owner: reviews link reliability."))
    text += section("User journeys", ("Submit destination → receive reference → follow link → reach destination.\n" if create else "") +
                    ("Create or reuse a link → follow it → inspect updated totals." if stats else ""))
    for prefix, title in [("FR", "Functional requirements"), ("NFR", "Non-functional requirements"),
                          ("BR", "Business rules"), ("SEC", "Security and compliance requirements")]:
        body = "\n".join(f"- **{rid}**: {desc}" for rid, _, _, desc, _ in records if rid.startswith(prefix))
        if prefix == "SEC":
            body += "\n\nNo regulatory certification or jurisdiction-specific obligation has been established."
        text += section(title, body)
    text += section("User stories", ("- As a publisher I can share a stable reference, so visitors can reach the intended destination (FR-001, FR-002).\n" if create else "") +
                    ("- As an operator I can see aggregate usage without visitor records (FR-003, SEC-002)." if stats else ""))
    text += section("Acceptance criteria", "\n".join(f"- {rid}: {check}" for rid, _, _, _, check in records))
    text += section("Priority and dependencies", "| ID | Priority | Depends on |\n|---|---|---|\n" +
                    "\n".join(f"| {rid} | {priority} | {deps if deps != 'Baseline create/redirect' or not create else 'FR-001, FR-002'} |"
                              for rid, priority, deps, _, _ in records))
    text += section("Failure scenarios", ("- Invalid input: reject the request (SEC-001). Unknown link: no redirect (FR-002).\n" if create else "") +
                    ("- Failed redirects must not inflate totals (BR-002).\n" if stats else "") +
                    "- Store unavailable: surface a failure; do not report a successful operation (NFR-003).")
    text += section("Out-of-scope requirements", "No hosted rollout, per-user analytics, or unapproved functionality.")
    text += section("Open questions and assumptions", "No traffic SLA or retention policy has been supplied. Acceptance criteria describe expected behavior, not proof it has passed.")
    return text
