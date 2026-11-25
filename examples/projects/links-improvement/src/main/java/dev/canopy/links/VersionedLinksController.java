package dev.canopy.links;

import com.fasterxml.jackson.annotation.JsonAlias;
import java.net.URI;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
class VersionedLinksController {
    private static final Set<String> RESERVED = Set.of("api", "r", "health", "error", "actuator", "favicon");
    private final LinkStore store;

    VersionedLinksController(LinkStore store) {
        this.store = store;
    }

    record Shorten(@JsonAlias({"originalUrl", "long_url"}) String url, @JsonAlias({"customAlias", "custom_alias"}) String alias,
                   @JsonAlias("ttl_seconds") Long ttlSeconds) {}

    @PostMapping("/api/v1/shorten")
    ResponseEntity<LinksController.CreatedLink> shorten(@RequestBody Shorten request) {
        String alias = request.alias();
        if (alias != null && (!alias.matches("[A-Za-z0-9_-]{1,32}") || RESERVED.contains(alias.toLowerCase(Locale.ROOT)))) {
            throw invalid();
        }
        Long ttl = request.ttlSeconds();
        if (ttl != null && (ttl < 1 || ttl > 31536000)) throw invalid();
        String code = store.create(normalize(request.url()), alias, ttl);
        String path = "/" + code;
        return ResponseEntity.created(URI.create(path)).body(new LinksController.CreatedLink(code, path));
    }

    private static String normalize(String value) {
        if (value == null || value.length() > 4096) throw invalid();
        try {
            URI uri = URI.create(value.strip());
            String scheme = uri.getScheme();
            if (!DestinationPolicy.allowed(uri) || uri.getRawUserInfo() != null || uri.getPort() > 65535) throw invalid();
            scheme = scheme.toLowerCase(Locale.ROOT);
            int port = uri.getPort();
            boolean explicit = port != -1 && !(port == 80 && scheme.equals("http")) && !(port == 443 && scheme.equals("https"));
            String normalized = scheme + "://" + uri.getHost().toLowerCase(Locale.ROOT) + (explicit ? ":" + port : "")
                    + (uri.getRawPath().isEmpty() ? "/" : uri.getRawPath())
                    + (uri.getRawQuery() == null ? "" : "?" + uri.getRawQuery())
                    + (uri.getRawFragment() == null ? "" : "#" + uri.getRawFragment());
            String ascii = URI.create(normalized).toASCIIString();
            if (ascii.length() > 4096) throw invalid();
            return ascii;
        } catch (IllegalArgumentException ex) {
            throw invalid();
        }
    }

    private static ResponseStatusException invalid() {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid destination, alias or lifetime");
    }

    @GetMapping("/{code:[A-Za-z0-9_-]{1,32}}")
    ResponseEntity<Void> redirect(@PathVariable String code) {
        return redirectTo(store.visit(code).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND)));
    }

    @RequestMapping(path = "/{code:[A-Za-z0-9_-]{1,32}}", method = RequestMethod.HEAD)
    ResponseEntity<Void> head(@PathVariable String code) {
        return redirectTo(store.destination(code).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND)));
    }

    static ResponseEntity<Void> redirectTo(String url) {
        return ResponseEntity.status(HttpStatus.FOUND).cacheControl(CacheControl.noStore()).location(URI.create(url)).build();
    }

    @GetMapping("/api/v1/stats/{code}")
    ResponseEntity<LinkStore.Stats> stats(@PathVariable String code) {
        return store.stats(code)
                .map(stats -> ResponseEntity.ok().cacheControl(CacheControl.noStore().cachePrivate()).body(stats))
                .orElseGet(() -> ResponseEntity.notFound().cacheControl(CacheControl.noStore().cachePrivate()).build());
    }

    @GetMapping("/health")
    Map<String, String> health() {
        store.checkDatabase();
        return Map.of("status", "UP");
    }
}
