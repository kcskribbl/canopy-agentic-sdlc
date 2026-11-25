package dev.canopy.links;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class StatsController {
    private final LinkStore store;

    StatsController(LinkStore store) {
        this.store = store;
    }

    @GetMapping("/api/stats")
    LinkStore.Totals stats() {
        return store.totals();
    }
}
