package dev.canopy.links.api;

import dev.canopy.links.analytics.LinkStatistics;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class StatsController {
    private final LinkStatistics store;

    StatsController(LinkStatistics store) {
        this.store = store;
    }

    @GetMapping("/api/stats")
    LinkStatistics.Totals stats() {
        return store.totals();
    }
}
