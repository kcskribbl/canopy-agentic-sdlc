package dev.canopy.links;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
class RequestPolicy extends OncePerRequestFilter {
    private static final Logger LOG = LoggerFactory.getLogger(RequestPolicy.class);
    private final int createLimit;
    private final int readLimit;
    private static final long MINUTE = TimeUnit.MINUTES.toNanos(1);
    private final LinkedHashMap<String, Budget> clients = new LinkedHashMap<>(16, .75f, true);

    private static final class Budget {
        final double[] tokens;
        long lastSeen;

        Budget(int writes, int reads, long now) {
            tokens = new double[]{writes, reads};
            lastSeen = now;
        }
    }

    RequestPolicy(@Value("${links.limit.create}") int createLimit, @Value("${links.limit.read}") int readLimit) {
        if (createLimit < 1 || readLimit < 1) throw new IllegalArgumentException("Invalid rate limits");
        this.createLimit = createLimit;
        this.readLimit = readLimit;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String id = request.getHeader("X-Correlation-ID");
        if (id == null || !id.matches("[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")) {
            id = UUID.randomUUID().toString();
        }
        long start = System.nanoTime();
        boolean create = "POST".equals(request.getMethod());
        boolean health = "/health".equals(request.getRequestURI());
        response.setHeader("X-Correlation-ID", id);
        boolean completed = false;
        try (var ignored = MDC.putCloseable("correlationId", id)) {
            int retry = health ? 0 : retryAfter(request.getRemoteAddr(), create, start);
            if (retry > 0) {
                response.setHeader("Retry-After", Integer.toString(retry));
                response.setStatus(429);
            } else {
                chain.doFilter(request, response);
            }
            completed = true;
        } finally {
            // Before the container handles an escaping error, an uncommitted response can still say 200.
            int status = completed || response.isCommitted() ? response.getStatus() : 500;
            LOG.atInfo().addKeyValue("event", "request_completed")
                    .addKeyValue("correlationId", id)
                    .addKeyValue("operation", health ? "health" : create ? "write" : "read")
                    .addKeyValue("status", status)
                    .addKeyValue("durationMs", TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - start))
                    .log("Request completed");
        }
    }

    synchronized int retryAfter(String client, boolean create, long now) {
        while (!clients.isEmpty() && now - clients.firstEntry().getValue().lastSeen >= MINUTE) clients.pollFirstEntry();
        Budget budget = clients.get(client);
        if (budget == null) {
            if (clients.size() >= 16384) return 60;
            budget = new Budget(createLimit, readLimit, now);
            clients.put(client, budget);
        }
        double minutes = Math.max(0, now - budget.lastSeen) / (double) MINUTE;
        budget.tokens[0] = Math.min(createLimit, budget.tokens[0] + minutes * createLimit);
        budget.tokens[1] = Math.min(readLimit, budget.tokens[1] + minutes * readLimit);
        budget.lastSeen = Math.max(now, budget.lastSeen);
        int index = create ? 0 : 1;
        if (budget.tokens[index] < 1) {
            double seconds = (1 - budget.tokens[index]) * 60 / (create ? createLimit : readLimit);
            return Math.max(1, (int) Math.ceil(seconds));
        }
        budget.tokens[index]--;
        return 0;
    }
}
