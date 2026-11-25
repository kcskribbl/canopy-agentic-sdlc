package dev.canopy.links;

import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PreviewController {
    private final JdbcTemplate db;

    PreviewController(JdbcTemplate db) {
        this.db = db;
    }

    record Preview(String url) {}

    @GetMapping("/api/links/{code}")
    ResponseEntity<Preview> preview(@PathVariable String code) {
        return ResponseEntity.of(db.query("SELECT destination FROM links WHERE code = ?",
                (rs, row) -> new Preview(rs.getString(1)), code).stream().findFirst());
    }
}
