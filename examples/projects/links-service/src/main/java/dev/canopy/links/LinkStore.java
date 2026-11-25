package dev.canopy.links;

import java.util.Optional;
import java.net.URI;
import java.util.UUID;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.sql.ResultSet;
import java.sql.SQLException;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.dao.TransientDataAccessResourceException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
class LinkStore {
    private static final int MAX_CODE_ATTEMPTS = 5;
    private final JdbcTemplate db;
    private final LinkCache cache;

    LinkStore(JdbcTemplate db) {
        this(db, null);
    }

    @Autowired
    LinkStore(JdbcTemplate db, LinkCache cache) {
        this.db = db;
        this.cache = cache;
    }

    String create(String destination) {
        for (int attempt = 0; attempt < MAX_CODE_ATTEMPTS; attempt++) {
            String code = UUID.randomUUID().toString().replace("-", "").substring(0, 12);
            try {
                db.update("INSERT INTO links (code, destination) VALUES (?, ?)", code, destination);
                return code;
            } catch (DuplicateKeyException collision) {
                // Retry with a fresh code rather than replacing an existing link.
            }
        }
        throw new TransientDataAccessResourceException("Could not allocate a unique short code");
    }

    String create(String destination, String alias, Long ttlSeconds) {
        OffsetDateTime expires = ttlSeconds == null ? null : OffsetDateTime.now(ZoneOffset.UTC).plusSeconds(ttlSeconds);
        for (int attempt = 0; attempt < MAX_CODE_ATTEMPTS; attempt++) {
            String code = alias == null ? base62(db.queryForObject("SELECT nextval('link_id_seq')", Long.class)) : alias;
            try {
                db.update("INSERT INTO links(code, destination, expires_at) VALUES (?, ?, ?)", code, destination, expires);
                return code;
            } catch (DuplicateKeyException collision) {
                if (alias != null) throw new ResponseStatusException(HttpStatus.CONFLICT, "Alias already in use");
            }
        }
        throw new TransientDataAccessResourceException("Could not allocate a unique short code");
    }

    private static String base62(long id) {
        String alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";
        StringBuilder out = new StringBuilder();
        do {
            out.append(alphabet.charAt((int) (id % 62)));
            id /= 62;
        } while (id != 0);
        return out.reverse().toString();
    }

    Optional<String> destination(String code) {
        LinkCache.Target target = cache.get(code);
        if (target == null) {
            target = db.query("SELECT destination, expires_at FROM links WHERE code = ?",
                    (rs, row) -> new LinkCache.Target(rs.getString(1), instant(rs, "expires_at")), code)
                    .stream().findFirst().orElse(null);
            if (target == null) return Optional.empty();
            cache.put(code, target);
        }
        if ((target.expiresAt() != null && !Instant.now().isBefore(target.expiresAt()))
                || !DestinationPolicy.allowed(URI.create(target.url()))) {
            throw new ResponseStatusException(HttpStatus.GONE);
        }
        return Optional.of(target.url());
    }

    Optional<String> visit(String code) {
        Optional<String> result = destination(code);
        if (result.isPresent() && db.update("""
                UPDATE links SET redirects = redirects + 1
                WHERE code = ? AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                """, code) == 0) {
            if (stats(code).isEmpty()) return Optional.empty();
            throw new ResponseStatusException(HttpStatus.GONE);
        }
        return result;
    }

    record Stats(String code, String url, long redirects, Instant createdAt, Instant expiresAt) {}

    Optional<Stats> stats(String code) {
        return db.query("SELECT code, destination, redirects, created_at, expires_at FROM links WHERE code = ?",
                (rs, row) -> new Stats(rs.getString(1), rs.getString(2), rs.getLong(3),
                        instant(rs, "created_at"), instant(rs, "expires_at")), code).stream().findFirst();
    }

    private static Instant instant(ResultSet rs, String column) throws SQLException {
        OffsetDateTime value = rs.getObject(column, OffsetDateTime.class);
        return value == null ? null : value.toInstant();
    }

    void checkDatabase() {
        db.queryForObject("SELECT 1", Integer.class);
    }

    record Totals(long totalLinks, long totalRedirects) {}

    Totals totals() {
        return db.queryForObject("SELECT COUNT(*), COALESCE(SUM(redirects), 0) FROM links",
                (rs, row) -> new Totals(rs.getLong(1), rs.getLong(2)));
    }
}
