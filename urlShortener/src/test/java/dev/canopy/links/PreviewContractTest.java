package dev.canopy.links;

import com.intuit.karate.Results;
import com.intuit.karate.Runner;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {"server.address=127.0.0.1", "spring.datasource.url=jdbc:h2:mem:previewContract"})
class PreviewContractTest {
    @LocalServerPort int port;

    @Test
    void verifiesPreviewOverHttp() {
        Results result = Runner.path("classpath:dev/canopy/links/preview.feature")
                .systemProperty("canopy.baseUrl", "http://127.0.0.1:" + port).parallel(1);
        assertEquals(0, result.getFailCount(), result.getErrorMessages());
        assertEquals(2, result.getScenariosTotal());
    }
}
