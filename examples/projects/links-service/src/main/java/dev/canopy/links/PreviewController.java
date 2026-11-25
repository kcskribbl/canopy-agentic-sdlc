package dev.canopy.links;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PreviewController {
    private final LinkStore store;

    PreviewController(LinkStore store) {
        this.store = store;
    }

    record Preview(String url) {}

    @GetMapping("/api/links/{code}")
    ResponseEntity<Preview> preview(@PathVariable String code) {
        return ResponseEntity.of(store.destination(code).map(Preview::new));
    }
}
