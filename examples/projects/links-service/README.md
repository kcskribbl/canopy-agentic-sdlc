# Links service

From `canopy-agentic-sdlc`, run `.\mvnw.cmd -f examples\projects\links-service\pom.xml clean verify` with Java 21. From the project directory start `java -jar target\links-service-1.0.0.jar`. No external services are required: the default binds loopback and persists H2 at `./data/canopy`. See `openapi.yaml` for the HTTP contract.

For optional local containers, first build the JAR, then set `DATABASE_PASSWORD` in your shell and run `docker compose up --build` from this project directory. Only the application port is published, on loopback. `docker compose down` stops the services without deleting the database volume.

| Environment | Purpose / default |
|---|---|
| `BIND_ADDRESS`, `PORT` | `127.0.0.1`, `8080` |
| `DATABASE_URL`, `DATABASE_USER`, `DATABASE_PASSWORD` | JDBC URL, user and password. Default file H2, user `sa`, empty password. For multiple replicas, use the same PostgreSQL database and credentials from the environment. |
| `REDIS_ENABLED`, `REDIS_URL` | `false`, `redis://localhost:6379`. Use authenticated TLS Redis for a remote cache. |
| `CACHE_NAMESPACE`, `CACHE_SECONDS`, `CACHE_CAPACITY` | `canopy:links:v1`, 60 seconds, 4096 local entries. Share a namespace only between replicas using the same database. Rotate it when restoring database snapshots. |
| `CREATE_RATE_PER_MINUTE`, `READ_RATE_PER_MINUTE` | Separate per-peer token buckets, initially 60 writes and 600 reads; replenish continuously by the configured number per minute. Requests behind a proxy share its budget. Do not rely on these as cluster-wide quotas. |

Both creation routes reject localhost, internal hostnames and non-public address literals using local parsing only. The service never fetches a destination or performs DNS checks. As a result it makes no guarantees about where a public hostname resolves. A previously stored link to a now-disallowed destination returns 410 without counting. Versioned create also accepts `long_url`, `custom_alias` and `ttl_seconds` instead of `url`, `alias` and `ttlSeconds`.

Flyway baselines an existing **seed v1** nonempty schema at version 1; V2 widens codes and adds timestamps plus a shared allocation sequence without recreating rows. Existing records receive migration time as their creation timestamp. Back up files/databases before upgrading. An empty database applies both migrations.

Each versioned generated code encodes a database sequence number in Base62. Multiple writers use the same sequence, and the primary key arbitrates races with custom aliases. Codes are public identifiers, not access secrets. Expired aliases stay reserved. The Redis-first destination cache falls back to bounded process-local storage and then JDBC. Counts and stats always use JDBC; a failed write returns 503 rather than silently dropping a count. Only opaque correlation UUIDs, operation category, status and elapsed time are logged by the request filter.
