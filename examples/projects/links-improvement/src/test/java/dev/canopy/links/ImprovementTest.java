package dev.canopy.links;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.head;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = "spring.datasource.url=jdbc:h2:mem:improvement")
@AutoConfigureMockMvc
class ImprovementTest {
    @Autowired MockMvc mvc;

    @Test
    void legacyHeadChecksTheLinkWithoutRecordingAVisit() throws Exception {
        String path = mvc.perform(post("/api/links").contentType("application/json")
                .content("{\"url\":\"https://example.invalid/articles\"}")).andExpect(status().isCreated())
                .andReturn().getResponse().getHeader("Location");
        mvc.perform(head(path)).andExpect(status().isFound()).andExpect(header().string("Location", "https://example.invalid/articles"));
        mvc.perform(head("/r/unassigned")).andExpect(status().isNotFound());
        mvc.perform(get("/api/v1/stats/" + path.substring(3))).andExpect(jsonPath("$.redirects").value(0));
        mvc.perform(get(path)).andExpect(status().isFound());
        mvc.perform(get("/api/v1/stats/" + path.substring(3))).andExpect(jsonPath("$.redirects").value(1));
    }

    @Test
    void bothSuccessfulAndMissingStatsHavePrivateNoStorePolicy() throws Exception {
        mvc.perform(post("/api/v1/shorten").contentType("application/json")
                .content("{\"url\":\"https://example.invalid\",\"alias\":\"stats-demo\"}")).andExpect(status().isCreated());
        mvc.perform(get("/api/v1/stats/stats-demo")).andExpect(status().isOk())
                .andExpect(header().string("Cache-Control", containsString("private")))
                .andExpect(header().string("Cache-Control", containsString("no-store")));
        mvc.perform(get("/api/v1/stats/not-issued")).andExpect(status().isNotFound())
                .andExpect(header().string("Cache-Control", containsString("private")))
                .andExpect(header().string("Cache-Control", containsString("no-store")));
    }
}
