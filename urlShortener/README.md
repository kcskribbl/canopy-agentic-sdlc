# URL Shortener

This standalone Java 21 / Spring Boot service creates short links, previews their destinations, redirects visitors, and reports aggregate usage. **Previewing is read-only; following a short link counts a visit.** Links and counters survive restarts in a local H2 database. You do not need to start Canopy's agent system to run it.

## Run and try it

From **this `urlShortener` directory** in PowerShell, with JDK 21 on `PATH`:

```powershell
..\mvnw.cmd clean verify
java -jar .\target\links-1.0.0.jar
```

The Maven wrapper downloads dependencies on the first build. No separate database server, Docker, or API key is required. Leave the service running and use a second terminal:

```powershell
$base = 'http://127.0.0.1:8080'
$link = '{"url":"https://example.org/docs"}' | curl.exe -fsS -H 'Content-Type: application/json' --data-binary '@-' "$base/api/links" | ConvertFrom-Json
curl.exe -i "$base/api/links/$($link.code)"  # Preview: 200, no visit
curl.exe -i "$base$($link.shortUrl)"         # Redirect: 302 + Location, one visit
curl.exe -i "$base/api/stats"               # Fresh database: {"totalLinks":1,"totalRedirects":1}
```

The second command that uses `curl.exe -i` deliberately omits `-L`: it shows the redirect response without contacting the destination. The counter records redirects issued, not successful page loads at the destination.

## API contract

[`openapi.yaml`](openapi.yaml) is the OpenAPI 3.0.3 specification for **this module**. Read it directly or import it into an OpenAPI viewer. This app does not serve Swagger UI, `/docs/openapi.yaml`, or the enhanced `/api/v1` routes. Those belong to the separate [enhanced service and Swagger scenario](../scenarios/observability-api-docs/scenario.json).

| Method and path | Input | Successful response |
|---|---|---|
| `POST /api/links` | JSON `{"url":"https://example.org/docs"}`. Required: absolute HTTP(S) URI with a host, up to 4,096 characters. | `201 Created`, relative `Location: /r/{code}`, and `{"code":"…","shortUrl":"/r/…"}`. |
| `GET /api/links/{code}` | Code returned by creation. | `200`, `{"url":"https://example.org/docs"}`. No redirect, outbound fetch, or counter update. |
| `GET /r/{code}` | Code returned by creation. | `302 Found` with the stored destination in `Location` and `Cache-Control: no-store`. |
| `GET /api/stats` | None. | `200`, `{"totalLinks":1,"totalRedirects":1}`. Totals cover **all** stored links, not one code. |

Malformed create requests return `400`; unknown codes return `404` on preview and redirect. Storage or transaction failures return `503`, as does exhausting the code-allocation retry limit. URL validation checks syntax and scheme, not reachability or destination safety. This module has no custom aliases, expiry, authentication, rate limiting, or per-link statistics endpoint.

## Request flow and core logic

```mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant D as H2
    C->>A: POST /api/links
    A->>D: Insert code and destination
    A-->>C: 201 + shortUrl
    C->>A: GET /api/links/{code}
    A->>D: Read destination only
    A-->>C: 200 + URL
    C->>A: GET /r/{code}
    A->>D: Increment and read in one transaction
    A-->>C: 302 + Location
    C->>A: GET /api/stats
    A->>D: Count links and sum redirects
    A-->>C: 200 + totals
```

| Where to look | What it owns |
|---|---|
| [LinksController](src/main/java/dev/canopy/links/LinksController.java) | Validates the input URI, returns a relative short URL on creation, and builds the redirect response. Its controller advice maps database and transaction exceptions to `503`. |
| [LinkStore](src/main/java/dev/canopy/links/LinkStore.java) and [schema.sql](src/main/resources/schema.sql) | Generates 12 hexadecimal characters from a random UUID. The `links.code` primary key prevents overwrites; only a duplicate-key collision is retried, up to five insert attempts total. Redirects use a parameterized SQL increment and destination lookup in one transaction, avoiding a read-modify-write race. |
| [PreviewController](src/main/java/dev/canopy/links/PreviewController.java) and [StatsController](src/main/java/dev/canopy/links/StatsController.java) | Preview performs a parameterized lookup without updating the row. Stats delegates to a database-wide count and sum; an empty table returns zero totals. |
| [Java tests](src/test/java/dev/canopy/links) and [HTTP contract scenarios](src/test/resources/dev/canopy/links/preview.feature) | Cover invalid URLs, collisions, concurrent redirect counts, aggregate totals, and the difference between previewing and following a link. `clean verify` runs them against in-memory test databases. |

## Configuration and logging

Defaults come from [application.properties](src/main/resources/application.properties) and Spring Boot. Standard Spring environment variables can override them before startup:

| Parameter | Default | Why it matters |
|---|---|---|
| `SERVER_ADDRESS` / `SERVER_PORT` | `127.0.0.1` / `8080` | Loopback-only by default. Change the port if it is occupied, and update `$base` accordingly. |
| `SPRING_DATASOURCE_URL` | `jdbc:h2:file:./data/canopy` | The path is relative to the **process working directory**, not the JAR. Start from the same directory to reuse links. |
| `spring.sql.init.mode` / `spring.h2.console.enabled` | `always` / `false` | Initializes the table if absent at startup; the H2 web console is disabled. |
| `LOGGING_LEVEL_ROOT` | Spring Boot default (`INFO`) | Controls framework console verbosity. For example, set `$env:LOGGING_LEVEL_ROOT='WARN'` before `java -jar` for quieter startup. |

**Logging scope:** there is no custom per-request logger, structured JSON event, or correlation-ID filter in this module. Use HTTP status and `Location` to inspect an individual response, and `/api/stats` to verify counts. The [brownfield telemetry example](../scenarios/observability-api-docs/) demonstrates structured request logging on the enhanced workload, not this standalone app.
