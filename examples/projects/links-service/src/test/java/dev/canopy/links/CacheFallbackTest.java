package dev.canopy.links;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;

class CacheFallbackTest {
    @Test
    @SuppressWarnings("unchecked")
    void sharedValuesWinAndLocalFallbackSurvivesRedisDisconnect() throws Exception {
        StringRedisTemplate redis = mock(StringRedisTemplate.class);
        ValueOperations<String, String> values = mock(ValueOperations.class);
        when(redis.opsForValue()).thenReturn(values);
        ObjectMapper json = new ObjectMapper().findAndRegisterModules();
        LinkCache cache = new LinkCache(redis, json, true, "test", 60, 1);
        var target = new LinkCache.Target("https://example.invalid/cached", null);
        String key = "test:target:code";
        when(values.get(key)).thenReturn(json.writeValueAsString(target))
                .thenThrow(new RedisConnectionFailureException("test outage"));
        assertThat(cache.get("code")).isEqualTo(target);
        cache.put("code", target);
        verify(values).set(eq(key), eq(json.writeValueAsString(target)), any(Duration.class));
        assertThat(cache.get("code")).isEqualTo(target);
        cache.put("new", target);
        assertThat(cache.get("code")).isNull();
        assertThat(cache.get("new")).isEqualTo(target);
    }
}
