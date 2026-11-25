package dev.canopy.links.cache;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;

class DestinationCacheTest {
    @Test
    void cannotReachRedisButCanStillCacheTheDatabaseResult() {
        var redis = mock(StringRedisTemplate.class);
        when(redis.opsForValue()).thenThrow(new RedisConnectionFailureException("offline"));
        var cache = new DestinationCache(redis, true, "test", 60, 16);
        assertThat(cache.get("abc")).isEmpty();
        cache.put("abc", "https://example.org");
        assertThat(cache.get("abc")).contains("https://example.org");
        verify(redis).opsForValue();
    }

    @Test
    @SuppressWarnings("unchecked")
    void remoteHitAvoidsASecondRemoteLookup() {
        var redis = mock(StringRedisTemplate.class);
        ValueOperations<String, String> ops = mock(ValueOperations.class);
        when(redis.opsForValue()).thenReturn(ops);
        when(ops.get("test:destination:abc")).thenReturn("https://example.org");
        var cache = new DestinationCache(redis, true, "test", 60, 16);
        assertThat(cache.get("abc")).contains("https://example.org");
        assertThat(cache.get("abc")).contains("https://example.org");
        verify(ops).get("test:destination:abc");
    }
}
