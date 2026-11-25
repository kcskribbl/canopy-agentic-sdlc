package dev.canopy.links;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {"spring.datasource.url=jdbc:h2:mem:policy", "links.limit.create=1", "links.limit.read=1"})
@AutoConfigureMockMvc
class PolicyTest {
    @Autowired MockMvc mvc;

    @Test
    void tokenBucketRefillsGraduallyAcrossMinuteBoundaries() {
        RequestPolicy policy = new RequestPolicy(2, 1);
        long start = TimeUnit.SECONDS.toNanos(59);
        assertThat(policy.retryAfter("peer", true, start)).isZero();
        assertThat(policy.retryAfter("peer", true, start)).isZero();
        assertThat(policy.retryAfter("peer", true, start)).isEqualTo(30);
        assertThat(policy.retryAfter("peer", true, start + TimeUnit.SECONDS.toNanos(1))).isEqualTo(29);
        assertThat(policy.retryAfter("peer", true, start + TimeUnit.SECONDS.toNanos(30))).isZero();
        assertThat(policy.retryAfter("peer", false, start + TimeUnit.SECONDS.toNanos(30))).isZero();
        assertThat(policy.retryAfter("peer", true, start + TimeUnit.SECONDS.toNanos(100))).isZero();
    }

    @Test
    void limitsAreIndependentAndHealthChecksAreExempt() throws Exception {
        var request = post("/api/v1/shorten").contentType("application/json").content("{\"url\":\"https://example.invalid\"}");
        String correlation = "07133631-4858-41cd-a876-8a83112a1d08";
        mvc.perform(request.header("X-Correlation-ID", correlation)).andExpect(status().isCreated())
                .andExpect(header().string("X-Correlation-ID", correlation));
        mvc.perform(request).andExpect(status().isTooManyRequests()).andExpect(header().exists("Retry-After"));
        mvc.perform(get("/api/stats")).andExpect(status().isOk());
        mvc.perform(get("/api/stats")).andExpect(status().isTooManyRequests());
        String id = mvc.perform(get("/health").header("X-Correlation-ID", "untrusted")).andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP")).andReturn().getResponse().getHeader("X-Correlation-ID");
        assertThat(id).isNotEqualTo("untrusted").matches("[a-f0-9-]{36}");
    }
}
