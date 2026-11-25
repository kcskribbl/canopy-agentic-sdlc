package dev.canopy.links;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.ServletException;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

@SpringBootTest(properties = "spring.datasource.url=jdbc:h2:mem:completion")
@ExtendWith(OutputCaptureExtension.class)
class RequestCompletionTest {
    @Test
    void emitsTypedRedactedCompletionEvenWhenChainThrows(CapturedOutput output) throws Exception {
        String id = "32a467c1-a902-43af-9b82-9dfe620f82e8";
        RequestPolicy policy = new RequestPolicy(5, 5);
        for (int status : new int[]{201, 500, 202}) {
            var req = new MockHttpServletRequest("POST", "/private-path-marker");
            req.addHeader("X-Correlation-ID", status == 201 ? id : "private-header-marker");
            req.addHeader("Authorization", "private-auth-marker");
            req.setQueryString("key=private-query-marker");
            req.setRemoteAddr("192.0.2.173");
            req.setContent("https://private-destination-marker.invalid".getBytes(StandardCharsets.UTF_8));
            var res = new MockHttpServletResponse();
            if (status == 201) {
                policy.doFilter(req, res, (request, response) -> res.setStatus(201));
            } else {
                assertThatThrownBy(() -> policy.doFilter(req, res, (request, response) -> {
                    if (status == 202) {
                        res.setStatus(202);
                        res.flushBuffer();
                    }
                    throw new ServletException("private-exception-marker");
                })).isInstanceOf(ServletException.class);
            }
            String header = res.getHeader("X-Correlation-ID");
            if (status == 201) assertThat(header).isEqualTo(id);
            else assertThat(UUID.fromString(header).toString()).isEqualTo(header);
            var events = output.getOut().lines().filter(line -> line.contains(header)).toList();
            assertThat(events).as("one completion per response ID").hasSize(1);
            String raw = events.getFirst();
            assertThat(raw).doesNotContain("private-", "192.0.2.173");
            JsonNode event = new ObjectMapper().readTree(raw);
            assertThat(event.path("event").asText()).as("structured completion event").isEqualTo("request_completed");
            assertThat(event.path("correlationId").asText()).isEqualTo(header);
            assertThat(event.path("operation").asText()).isEqualTo("write");
            assertThat(event.path("status").isIntegralNumber()).isTrue();
            assertThat(event.path("status").intValue()).isEqualTo(status);
            assertThat(event.path("durationMs").isIntegralNumber()).isTrue();
            assertThat(event.path("durationMs").longValue()).isNotNegative();
        }
    }
}
