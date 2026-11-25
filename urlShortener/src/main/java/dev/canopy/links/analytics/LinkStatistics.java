package dev.canopy.links.analytics;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class LinkStatistics {
    private final JdbcTemplate db;

    public LinkStatistics(JdbcTemplate db) {
        this.db = db;
    }

    public record Totals(long totalLinks, long totalRedirects) {}

    public Totals totals() {
        return db.queryForObject("SELECT COUNT(*), COALESCE(SUM(redirects), 0) FROM links",
                (rs, row) -> new Totals(rs.getLong(1), rs.getLong(2)));
    }
}
