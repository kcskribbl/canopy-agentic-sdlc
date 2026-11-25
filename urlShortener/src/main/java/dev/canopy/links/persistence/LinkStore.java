package dev.canopy.links.persistence;

import java.util.Optional;
import java.util.UUID;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.dao.TransientDataAccessResourceException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class LinkStore {
    private static final int MAX_CODE_ATTEMPTS = 5;
    private final JdbcTemplate db;

    public LinkStore(JdbcTemplate db) {
        this.db = db;
    }

    public String create(String destination) {
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

    public boolean recordVisit(String code) {
        return db.update("UPDATE links SET redirects = redirects + 1 WHERE code = ?", code) == 1;
    }

    public Optional<String> destination(String code) {
        return db.query("SELECT destination FROM links WHERE code = ?", (rs, row) -> rs.getString(1), code)
                .stream().findFirst();
    }
}
