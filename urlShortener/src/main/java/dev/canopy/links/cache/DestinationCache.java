package dev.canopy.links.cache;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import java.time.Duration;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicLong;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class DestinationCache {
    private static final Logger LOG = LoggerFactory.getLogger(DestinationCache.class);
    private final StringRedisTemplate redis;
    private final Cache<String, String> local;
    private final boolean shared;
    private final Duration ttl;
    private final String prefix;
    private final AtomicLong retryAt = new AtomicLong();

    public DestinationCache(StringRedisTemplate redis, @Value("${links.cache.shared}") boolean shared,
            @Value("${links.cache.namespace}") String namespace, @Value("${links.cache.seconds}") int seconds,
            @Value("${links.cache.capacity}") int capacity) {
        if (seconds < 1 || capacity < 1 || namespace.isBlank()) throw new IllegalArgumentException("Invalid cache settings");
        this.redis = redis;
        this.shared = shared;
        this.ttl = Duration.ofSeconds(seconds);
        this.prefix = namespace + ":destination:";
        this.local = Caffeine.newBuilder().maximumSize(capacity).expireAfterWrite(ttl).build();
    }

    public Optional<String> get(String code) {
        String value = local.getIfPresent(code);
        if (value == null && ready()) {
            try {
                value = redis.opsForValue().get(prefix + code);
                if (value != null) local.put(code, value);
            } catch (DataAccessException failure) {
                backOff();
            }
        }
        return Optional.ofNullable(value);
    }

    public void put(String code, String url) {
        local.put(code, url);
        if (ready()) {
            try {
                redis.opsForValue().set(prefix + code, url, ttl);
            } catch (DataAccessException failure) {
                backOff();
            }
        }
    }

    private boolean ready() {
        return shared && System.currentTimeMillis() >= retryAt.get();
    }

    private void backOff() {
        long now = System.currentTimeMillis();
        if (retryAt.getAndSet(now + 5000) <= now) LOG.warn("Redis unavailable; using local destination cache");
    }
}
