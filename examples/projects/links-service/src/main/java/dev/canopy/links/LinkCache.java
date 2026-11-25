package dev.canopy.links;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
class LinkCache {
    record Target(String url, Instant expiresAt) {}
    private record Entry(Target target, Instant until) {}
    private final LinkedHashMap<String, Entry> local = new LinkedHashMap<>(16, .75f, true);
    private final StringRedisTemplate redis;
    private final ObjectMapper json;
    private final boolean enabled;
    private final String prefix;
    private final int seconds;
    private final int capacity;
    private volatile long retryAfter;

    LinkCache(StringRedisTemplate redis, ObjectMapper json, @Value("${links.redis.enabled}") boolean enabled,
              @Value("${links.cache.namespace}") String namespace, @Value("${links.cache.seconds}") int seconds,
              @Value("${links.cache.capacity}") int capacity) {
        if (seconds < 1 || capacity < 1 || namespace.isBlank()) throw new IllegalArgumentException("Invalid cache settings");
        this.redis = redis;
        this.json = json;
        this.enabled = enabled;
        this.prefix = namespace + ":target:";
        this.seconds = seconds;
        this.capacity = capacity;
    }

    Target get(String code) {
        if (remoteReady()) {
            try {
                String raw = redis.opsForValue().get(prefix + code);
                if (raw != null) {
                    Target target = json.readValue(raw, Target.class);
                    if (target != null && target.url() != null) {
                        remember(code, target);
                        return target;
                    }
                }
            } catch (DataAccessException | JsonProcessingException ex) {
                backOff();
            }
        }
        synchronized (local) {
            Entry entry = local.get(code);
            if (entry == null) return null;
            if (Instant.now().isBefore(entry.until())) return entry.target();
            local.remove(code);
            return null;
        }
    }

    void put(String code, Target target) {
        remember(code, target);
        if (remoteReady()) {
            try {
                Duration ttl = Duration.ofSeconds(seconds);
                if (target.expiresAt() != null) {
                    Duration life = Duration.between(Instant.now(), target.expiresAt());
                    if (life.compareTo(ttl) < 0) ttl = life;
                }
                if (ttl.toMillis() > 0) redis.opsForValue().set(prefix + code, json.writeValueAsString(target), ttl);
            } catch (DataAccessException | JsonProcessingException ex) {
                backOff();
            }
        }
    }

    private void remember(String code, Target target) {
        synchronized (local) {
            local.put(code, new Entry(target, Instant.now().plusSeconds(seconds)));
            if (local.size() > capacity) local.pollFirstEntry();
        }
    }

    private boolean remoteReady() {
        return enabled && System.currentTimeMillis() >= retryAfter;
    }

    private void backOff() {
        retryAfter = System.currentTimeMillis() + 5000;
    }
}
