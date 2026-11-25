package dev.canopy.links.service;

import dev.canopy.links.cache.DestinationCache;
import dev.canopy.links.persistence.LinkStore;
import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LinkService {
    private final LinkStore store;
    private final DestinationCache cache;

    public LinkService(LinkStore store, DestinationCache cache) {
        this.store = store;
        this.cache = cache;
    }

    public String create(String destination) {
        return store.create(destination);
    }

    public Optional<String> preview(String code) {
        return cache.get(code).or(() -> {
            var value = store.destination(code);
            value.ifPresent(url -> cache.put(code, url));
            return value;
        });
    }

    @Transactional
    public Optional<String> visit(String code) {
        return store.recordVisit(code) ? preview(code) : Optional.empty();
    }
}
