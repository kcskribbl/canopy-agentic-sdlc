package dev.canopy.links;

import java.util.Optional;
import java.util.UUID;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.dao.TransientDataAccessResourceException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
class LinkStore {
    private static final int MAX_CODE_ATTEMPTS = 5;
    private final JdbcTemplate db;

    LinkStore(JdbcTemplate db) {
        this.db = db;
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

    @Transactional
    public Optional<String> visit(String code) {
        if (db.update("UPDATE links SET redirects = redirects + 1 WHERE code = ?", code) == 0) {
            return Optional.empty();
        }
        return Optional.of(db.queryForObject("SELECT destination FROM links WHERE code = ?", String.class, code));
    }

    record Totals(long totalLinks, long totalRedirects) {}

    Totals totals() {
        return db.queryForObject("SELECT COUNT(*), COALESCE(SUM(redirects), 0) FROM links",
                (rs, row) -> new Totals(rs.getLong(1), rs.getLong(2)));
    }
}
