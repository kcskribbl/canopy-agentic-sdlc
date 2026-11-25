package dev.canopy.links.api;

import dev.canopy.links.service.LinkService;
import java.net.URI;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class LinksController {
    private final LinkService store;

    public LinksController(LinkService store) {
        this.store = store;
    }
    record NewLink(String url) {}
    record CreatedLink(String code, String shortUrl) {}

    @PostMapping("/api/links")
    ResponseEntity<CreatedLink> create(@RequestBody NewLink input) {
        String url = input.url();
        if (url == null || url.length() > 4096) {
            throw invalidUrl();
        }
        URI target;
        try {
            target = URI.create(url);
        } catch (IllegalArgumentException ex) {
            throw invalidUrl();
        }
        if (target.getHost() == null || !("http".equalsIgnoreCase(target.getScheme())
                || "https".equalsIgnoreCase(target.getScheme()))) {
            throw invalidUrl();
        }
        String code = store.create(url);
        String path = "/r/" + code;
        return ResponseEntity.created(URI.create(path)).body(new CreatedLink(code, path));
    }

    private static ResponseStatusException invalidUrl() {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, "Expected an absolute HTTP(S) URL");
    }

    @GetMapping("/r/{code}")
    ResponseEntity<Void> redirect(@PathVariable String code) {
        String destination = store.visit(code).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        return ResponseEntity.status(HttpStatus.FOUND).cacheControl(CacheControl.noStore())
                .location(URI.create(destination)).build();
    }
}
