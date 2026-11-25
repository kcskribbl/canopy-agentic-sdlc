package dev.canopy.links;

import static org.assertj.core.api.Assertions.assertThat;

import java.sql.DriverManager;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;

class UpgradeTest {
    @Test
    void baselinesAndPreservesLegacyRowsWithoutResettingCounts() throws Exception {
        String url = "jdbc:h2:mem:upgrade";
        try (var db = DriverManager.getConnection(url, "sa", ""); var sql = db.createStatement()) {
            sql.execute("""
                    CREATE TABLE links (code VARCHAR(12) PRIMARY KEY, destination VARCHAR(4096) NOT NULL,
                    redirects BIGINT NOT NULL DEFAULT 0 CHECK (redirects >= 0))
                    """);
            sql.executeUpdate("INSERT INTO links VALUES ('original', 'https://example.invalid', 27)");
            var flyway = Flyway.configure().dataSource(url, "sa", "").baselineOnMigrate(true).load();
            assertThat(flyway.migrate().migrationsExecuted).isEqualTo(1);
            assertThat(flyway.migrate().migrationsExecuted).isZero();
            try (var rows = sql.executeQuery("SELECT * FROM links WHERE code = 'original'")) {
                assertThat(rows.next()).isTrue();
                assertThat(rows.getString("destination")).isEqualTo("https://example.invalid");
                assertThat(rows.getLong("redirects")).isEqualTo(27);
                assertThat(rows.getObject("created_at")).isNotNull();
                assertThat(rows.getObject("expires_at")).isNull();
            }
        }
    }
}
