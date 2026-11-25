package dev.canopy.links.api;

import dev.canopy.links.service.LinkService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PreviewController {
    private final LinkService links;

    PreviewController(LinkService links) {
        this.links = links;
    }

    record Preview(String url) {}

    @GetMapping("/api/links/{code}")
    ResponseEntity<Preview> preview(@PathVariable String code) {
        return ResponseEntity.of(links.preview(code).map(Preview::new));
    }
}
