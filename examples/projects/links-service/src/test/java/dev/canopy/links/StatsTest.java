package dev.canopy.links;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = "spring.datasource.url=jdbc:h2:mem:stats-test")
@AutoConfigureMockMvc
class StatsTest {
    @Autowired MockMvc mvc;

    @Test
    void totalsIncludeAllLinksAndOnlySuccessfulRedirects() throws Exception {
        assertTotals(0, 0);
        for (int i = 1; i <= 2; i++) {
            String path = mvc.perform(post("/api/links").contentType("application/json")
                            .content("{\"url\":\"http://example.invalid\"}"))
                    .andExpect(status().isCreated()).andReturn().getResponse().getHeader("Location");
            for (int visit = 0; visit < i; visit++) {
                mvc.perform(get(path)).andExpect(status().isFound());
            }
        }
        mvc.perform(get("/r/missing")).andExpect(status().isNotFound());
        assertTotals(2, 3);
    }

    private void assertTotals(int links, int redirects) throws Exception {
        mvc.perform(get("/api/stats")).andExpect(status().isOk())
                .andExpect(jsonPath("$.totalLinks").value(links))
                .andExpect(jsonPath("$.totalRedirects").value(redirects));
    }
}
