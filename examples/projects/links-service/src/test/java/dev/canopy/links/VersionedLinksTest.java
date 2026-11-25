package dev.canopy.links;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.head;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Duration;
import org.awaitility.Awaitility;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;

@SpringBootTest(properties = "spring.datasource.url=jdbc:h2:mem:versioned")
@AutoConfigureMockMvc
class VersionedLinksTest {
    @Autowired MockMvc mvc;

    private ResultActions shorten(String json) throws Exception {
        return mvc.perform(post("/api/v1/shorten").contentType("application/json").content(json));
    }

    @Test
    void aliasRedirectsToNormalizedDestinationAndStatsOnlyCountGet() throws Exception {
        String body = """
                {"url":" HTTPS://ExAmple.invalid:443/Case?q=a%2Fb#Section ","alias":"Case-1"}
                """;
        String url = "https://example.invalid/Case?q=a%2Fb#Section";
        shorten(body).andExpect(status().isCreated()).andExpect(header().string("Location", "/Case-1"));
        shorten(body).andExpect(status().isConflict());
        mvc.perform(head("/Case-1")).andExpect(status().isFound()).andExpect(header().string("Location", url));
        mvc.perform(get("/Case-1")).andExpect(status().isFound()).andExpect(header().string("Location", url));
        mvc.perform(get("/api/v1/stats/Case-1")).andExpect(status().isOk())
                .andExpect(jsonPath("$.url").value(url)).andExpect(jsonPath("$.createdAt").isString())
                .andExpect(jsonPath("$.redirects").value(1));
        mvc.perform(get("/api/v1/stats/unknown")).andExpect(status().isNotFound());
    }

    @Test
    void warmCachedLinkExpiresAndRemainsReserved() throws Exception {
        String body = """
                {"url":"https://example.invalid","alias":"short-lived","ttlSeconds":1}
                """;
        shorten(body).andExpect(status().isCreated());
        mvc.perform(head("/short-lived")).andExpect(status().isFound());
        Awaitility.await().atMost(Duration.ofSeconds(5)).untilAsserted(() ->
                mvc.perform(head("/short-lived")).andExpect(status().isGone()));
        mvc.perform(get("/short-lived")).andExpect(status().isGone());
        mvc.perform(get("/r/short-lived")).andExpect(status().isGone());
        mvc.perform(get("/api/links/short-lived")).andExpect(status().isGone());
        mvc.perform(get("/api/v1/stats/short-lived")).andExpect(jsonPath("$.redirects").value(0));
        shorten(body).andExpect(status().isConflict());
    }

    @Test
    void acceptsSnakeCaseAliases() throws Exception {
        shorten("{\"long_url\":\"https://Example.invalid\",\"custom_alias\":\"snake\",\"ttl_seconds\":60}")
                .andExpect(status().isCreated()).andExpect(header().string("Location", "/snake"));
        mvc.perform(get("/api/v1/stats/snake")).andExpect(jsonPath("$.expiresAt").isString())
                .andExpect(jsonPath("$.url").value("https://example.invalid/"));
    }

    @ParameterizedTest
    @ValueSource(strings = {"http://localhost", "http://localhost.", "http://127.0.0.1", "http://192.168.1.1",
            "http://10.1.2.3", "http://172.31.0.1", "http://169.254.1.1", "http://[::1]",
            "http://[fd00::1]", "http://printer.local", "http://service.internal"})
    void rejectsNonPublicDestinationsOnBothContracts(String url) throws Exception {
        String body = "{\"url\":\"" + url + "\"}";
        shorten(body).andExpect(status().isBadRequest());
        mvc.perform(post("/api/links").contentType("application/json").content(body)).andExpect(status().isBadRequest());
    }

    @Test
    void generatedCodesAreDistinctAndDatabaseSequenceBacked() throws Exception {
        String body = "{\"url\":\"http://example.invalid:80\"}";
        String first = shorten(body).andExpect(status().isCreated()).andReturn().getResponse().getHeader("Location");
        String second = shorten(body).andExpect(status().isCreated()).andReturn().getResponse().getHeader("Location");
        assertThat(first).matches("/[A-Za-z0-9]+").isNotEqualTo(second);
        mvc.perform(get(first)).andExpect(header().string("Location", "http://example.invalid/"));
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "{}", "{\"url\":\"mailto:hi@example.invalid\"}", "{\"url\":\"https:///articles\"}",
            "{\"url\":\"https://example.invalid\",\"alias\":\"Health\"}", "{\"url\":\"https://example.invalid\",\"alias\":\"a b\"}",
            "{\"url\":\"https://example.invalid\",\"ttlSeconds\":0}", "{\"url\":\"https://example.invalid\",\"ttlSeconds\":1.5}"
    })
    void invalidRequestsAreRejected(String body) throws Exception {
        shorten(body).andExpect(status().isBadRequest());
    }
}
