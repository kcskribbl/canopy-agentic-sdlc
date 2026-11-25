package dev.canopy.links;

import java.net.URI;
import org.springframework.dao.DataAccessException;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.transaction.TransactionException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

@RestController
class LinksController {
    private final LinkStore store;

    LinksController(LinkStore store) {
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
        if (!DestinationPolicy.allowed(target)) {
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

    @RequestMapping(path = "/r/{code}", method = RequestMethod.HEAD)
    ResponseEntity<Void> head(@PathVariable String code) {
        return VersionedLinksController.redirectTo(store.destination(code)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND)));
    }
}

@RestControllerAdvice
class StorageErrorHandler {
    @ExceptionHandler({DataAccessException.class, TransactionException.class})
    ResponseEntity<Void> storageUnavailable() {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
    }
}
