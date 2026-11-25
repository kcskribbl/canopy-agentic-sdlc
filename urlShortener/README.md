# URL Shortener

## What it does

This standalone Java 21 / Spring Boot service creates short links, previews their destinations, redirects visitors, and reports aggregate usage. **Previewing is read-only; following a short link counts a visit.** A relational database owns the links and counters: file-backed H2 for local use, or PostgreSQL for a shared service. A bounded local cache and optional Redis cache accelerate destination lookups without caching visit counts.

## Architecture at a glance

The same JAR runs in both modes. Controllers delegate to `LinkService` for creation and lookup, and to `LinkStatistics` for aggregate totals. Each redirect updates SQL before returning `302`; Redis is never the source of truth for a visit. See the [request sequence](#request-flow-and-core-logic) and [package map](#project-layout).

| Runtime | Link and counter storage | Destination cache |
|---|---|---|
| Local JAR | H2 file, preserved across restarts | Bounded in-process Caffeine cache |
| Docker Compose | PostgreSQL on a named volume | Caffeine, then shared Redis; SQL on a miss |

## Prerequisites

Use JDK 21 and the repository's Maven wrapper. The first build needs network access to download Maven and dependencies. Docker with Compose is needed **only** for the PostgreSQL/Redis stack. Commands below use PowerShell and run from **this `urlShortener` directory**.

## Quick start

Build and run with H2 (no external services or API key):

```powershell
..\mvnw.cmd clean verify
java -jar .\target\links-1.0.0.jar
```

For PostgreSQL instead, build the JAR but skip `java -jar`; follow [Run with PostgreSQL and Redis](#run-with-postgresql-and-redis). Both modes listen at `http://127.0.0.1:8080` by default.

## Try it with curl

With the service running, open a second terminal:

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

### Error cases

```powershell
'{"url":"/relative"}' | curl.exe -i -H 'Content-Type: application/json' --data-binary '@-' "$base/api/links"  # 400
curl.exe -i "$base/r/never-issued"  # 404
```

Storage or transaction failures return `503`, as does exhausting the code-allocation retry limit. URL validation checks syntax and scheme, not reachability or destination safety. This module has no custom aliases, expiry, authentication, rate limiting, or per-link statistics endpoint.

## Request flow and core logic

```mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant K as Destination cache
    participant D as SQL database
    C->>A: POST /api/links
    A->>D: Insert code and destination
    A-->>C: 201 + shortUrl
    C->>A: GET /api/links/{code}
    A->>K: Look up code (local, then Redis if enabled)
    opt Cache miss
        A->>D: Read destination
        A->>K: Cache successful lookup
    end
    A-->>C: 200 + URL
    C->>A: GET /r/{code}
    A->>D: Increment counter for existing code
    A->>K: Resolve destination (SQL on miss)
    A-->>C: 302 + Location
    C->>A: GET /api/stats
    A->>D: Count links and sum redirects
    A-->>C: 200 + totals
```

## Project layout

| Where to look | What it owns |
|---|---|
| [API](src/main/java/dev/canopy/links/api) | Controllers validate requests and map outcomes to HTTP. Advice maps storage and transaction errors to `503`. |
| [LinkService](src/main/java/dev/canopy/links/service/LinkService.java) | Implements cache-aside previews. On redirect it increments the SQL counter atomically before resolving the destination in the same transaction. Even a warm cache cannot replace a failed counter write. |
| [LinkStore](src/main/java/dev/canopy/links/persistence/LinkStore.java) and [schema.sql](src/main/resources/schema.sql) | Parameterized JDBC works with both supported databases. The primary key prevents overwrites; collisions on a random 12-hex-character code are retried up to five insert attempts total. |
| [DestinationCache](src/main/java/dev/canopy/links/cache/DestinationCache.java) | Looks up immutable destinations in Caffeine, then optional Redis. Misses go to SQL; missing links aren't cached. A Redis access failure suppresses remote calls for five seconds while local cache and SQL continue serving requests. |
| [LinkStatistics](src/main/java/dev/canopy/links/analytics/LinkStatistics.java) | Always queries SQL for the link count and sum of redirects. No asynchronous queue or cache can lose or delay an acknowledged counter increment. |
| [Java tests](src/test/java/dev/canopy/links) and [HTTP contract scenarios](src/test/resources/dev/canopy/links/preview.feature) | Cover invalid URLs, collisions, concurrent redirect counts, aggregate totals, and the difference between previewing and following a link. `clean verify` runs them against in-memory test databases. |

## Settings

Defaults come from [application.properties](src/main/resources/application.properties) and Spring Boot. Standard Spring environment variables can override them before startup:

| Parameter | Default | Why it matters |
|---|---|---|
| `SERVER_ADDRESS` / `SERVER_PORT` | `127.0.0.1` / `8080` | Loopback-only by default. Change the port if it is occupied, and update `$base` accordingly. |
| `SPRING_DATASOURCE_URL` | `jdbc:h2:file:./data/canopy` | The path is relative to the **process working directory**, not the JAR. Start from the same directory to reuse links. |
| `spring.sql.init.mode` / `spring.h2.console.enabled` | `always` / `false` | Initializes the table if absent at startup; the H2 web console is disabled. |
| `LOGGING_LEVEL_ROOT` | Spring Boot default (`INFO`) | Controls framework console verbosity. For example, set `$env:LOGGING_LEVEL_ROOT='WARN'` before `java -jar` for quieter startup. |
| `REDIS_ENABLED` / `SPRING_DATA_REDIS_URL` | `false` / unset | Enable Redis and point to a Redis instance, or set `SPRING_DATA_REDIS_HOST` and port. Access timeouts default to 500 ms. |
| `CACHE_CAPACITY` / `CACHE_TTL_SECONDS` | `4096` / `300` | Maximum local entries and destination lifetime. Never cache counts. |
| `CACHE_NAMESPACE` | `canopy-standalone` | Use a separate namespace for each backing database sharing Redis; change it after a database restore. |

### Run with PostgreSQL and Redis

From this directory, build the JAR first as above. Set `DATABASE_PASSWORD` in the environment to a local development password, then run:

```powershell
docker compose up -d
docker compose logs -f app
```

Use the same curl examples at `http://127.0.0.1:8080` (or set `APP_PORT` before startup). [Compose](compose.yaml) publishes only the application on loopback. PostgreSQL uses a named volume and both backends are private to the Compose network. `docker compose down` stops the stack without deleting the database. For an existing PostgreSQL database outside Compose, set `SPRING_DATASOURCE_URL`, `SPRING_DATASOURCE_USERNAME`, and `SPRING_DATASOURCE_PASSWORD`; the database user must be able to initialize the schema. Redis is optional in either mode.

**Verify both backends.** Press `Ctrl+C` to stop following the logs (the stack stays up), then use the same terminal so `DATABASE_PASSWORD` is still set. Create a fresh link and preview it once. These checks use the default cache namespace and port:

```powershell
$base = 'http://127.0.0.1:8080'
$link = Invoke-RestMethod -Method Post "$base/api/links" -ContentType 'application/json' -Body '{"url":"https://example.org/cache-check"}'
$code = $link.code
Invoke-RestMethod "$base/api/links/$code"
docker compose exec -T cache redis-cli GET "canopy-standalone:destination:$code"
docker compose exec -T db psql -U links -d links -Atc "SELECT redirects FROM links WHERE code = '$code'"
curl.exe -sS -D - -o NUL "$base$($link.shortUrl)"
docker compose exec -T db psql -U links -d links -Atc "SELECT redirects FROM links WHERE code = '$code'"
```

Redis should return `https://example.org/cache-check`. PostgreSQL should report `0` after the preview and `1` after the `302` redirect. This checks the newly created link rather than relying on database-wide totals from a potentially reused volume.

## Reading the logs and checking readiness

The JAR writes Spring Boot logs to the terminal; use `docker compose logs -f app` for the container. A Redis access failure logs a warning before falling back to the local cache and SQL. This module has no custom per-request logger or correlation-ID header.

Run `curl.exe -fsS "$base/api/stats"` to check that the HTTP service can read its database. Success does **not** establish Redis health; use the [backend checks](#run-with-postgresql-and-redis) for that. There is no dedicated health or metrics endpoint. `totalRedirects` is an application counter, not a count of successful page loads at the destination.

## Running the tests

From this directory, `..\mvnw.cmd clean verify` runs the Java tests and Karate HTTP scenarios. No Compose stack is needed. The tests cover URL validation, code collisions, concurrent redirect counts, and cache fallback. The [Karate scenarios](src/test/resources/dev/canopy/links/preview.feature) exercise the running HTTP API: two previews leave the counters unchanged, and one redirect increases the count by one. For a live PostgreSQL/Redis integration check, use the commands in [Run with PostgreSQL and Redis](#run-with-postgresql-and-redis).

## Screenshots and further reading

See the [captured API responses](../docs/images/02-api-responses.png) and [preview versus redirect counts](../docs/images/03-click-metrics.png). The [OpenAPI contract](openapi.yaml) lists all supported operations. The [platform README](../README.md) explains how Canopy governs service changes.

## Troubleshooting

| Symptom | What to check |
|---|---|
| The JAR starts with H2 instead of PostgreSQL | `SPRING_DATASOURCE_URL` selects the database. Compose sets it to PostgreSQL inside the app container. `spring.h2.console.enabled=false` only disables the H2 browser console. |
| Compose reports a missing password or JAR | Set `DATABASE_PASSWORD` in the same terminal as `docker compose`, and run `..\mvnw.cmd clean verify` before starting the stack. |
| Port 8080 is already in use | Set `SERVER_PORT` for the local JAR or `APP_PORT` for Compose, then update `$base` in the examples. |
| Local links appear to disappear after a restart | Launch the JAR from the same directory: the default H2 file path is relative to the process working directory. |
