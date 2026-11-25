package dev.canopy.links;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import dev.canopy.links.api.LinksController;
import dev.canopy.links.api.StorageErrorHandler;
import dev.canopy.links.cache.DestinationCache;
import dev.canopy.links.persistence.LinkStore;
import dev.canopy.links.service.LinkService;
import java.util.ArrayList;
import java.util.Map;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

@SpringBootTest(properties = "spring.datasource.url=jdbc:h2:mem:links-test")
@AutoConfigureMockMvc
class LinksTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired JdbcTemplate db;

    @Test
    void simultaneousRedirectsPreserveDestinationAndCount() throws Exception {
        String url = "https://example.invalid/path?q=a%20b#part";
        var response = mvc.perform(post("/api/links").contentType("application/json")
                        .content(json.writeValueAsBytes(Map.of("url", url))))
                .andExpect(status().isCreated()).andReturn().getResponse();
        var body = json.readTree(response.getContentAsByteArray());
        String code = body.required("code").asText();
        String path = "/r/" + code;
        assertThat(body.required("shortUrl").asText()).isEqualTo(path);
        assertThat(response.getHeader("Location")).isEqualTo(path);

        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            var start = new CountDownLatch(1);
            var visits = new ArrayList<Future<Void>>();
            for (int i = 0; i < 12; i++) {
                visits.add(pool.submit(() -> {
                    start.await();
                    mvc.perform(get(path)).andExpect(status().isFound()).andExpect(header().string("Location", url));
                    return null;
                }));
            }
            start.countDown();
            for (var visit : visits) {
                visit.get(10, TimeUnit.SECONDS);
            }
        } finally {
            pool.shutdownNow();
        }
        assertThat(db.queryForObject("SELECT redirects FROM links WHERE code = ?", Long.class, code)).isEqualTo(12L);
    }

    @ParameterizedTest
    @ValueSource(strings = {"", "/relative", "https:///missing-host", "ftp://example.invalid", "https://bad host"})
    void rejectsInvalidDestination(String url) throws Exception {
        mvc.perform(post("/api/links").contentType("application/json")
                        .content(json.writeValueAsBytes(Map.of("url", url))))
                .andExpect(status().isBadRequest());
    }

    @Test
    void unknownCodeIsNotFound() throws Exception {
        mvc.perform(get("/r/not-a-code")).andExpect(status().isNotFound());
    }

    @Test
    void collisionsHaveAFiniteBudgetAndStorageOutagesAreNotRetried() throws Exception {
        JdbcTemplate failingDb = mock(JdbcTemplate.class);
        MockMvc api = MockMvcBuilders.standaloneSetup(new LinksController(
                        new LinkService(new LinkStore(failingDb), mock(DestinationCache.class))))
                .setControllerAdvice(new StorageErrorHandler()).build();
        var collision = new DuplicateKeyException("collision");
        when(failingDb.update(anyString(), anyString(), anyString()))
                .thenThrow(collision, collision, collision, collision, collision)
                .thenThrow(new AssertionError("Exceeded retry budget"));
        var request = post("/api/links").contentType("application/json").content("{\"url\":\"http://example.invalid\"}");
        api.perform(request).andExpect(status().isServiceUnavailable());
        verify(failingDb, times(5)).update(anyString(), anyString(), anyString());

        reset(failingDb);
        when(failingDb.update(anyString(), anyString(), anyString()))
                .thenThrow(new DataAccessResourceFailureException("database unavailable"));
        api.perform(request).andExpect(status().isServiceUnavailable());
        verify(failingDb).update(anyString(), anyString(), anyString());
    }
}
