package dev.canopy.links;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.yaml.snakeyaml.Yaml;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {"docs.enabled=true", "server.address=127.0.0.1", "spring.datasource.url=jdbc:h2:mem:docs"})
class SwaggerDocsTest {
    @LocalServerPort int port;
    private final HttpClient http = HttpClient.newHttpClient();

    private byte[] fetch(URI uri) throws Exception {
        assertThat(uri.getHost()).isEqualTo("127.0.0.1");
        assertThat(uri.getPort()).isEqualTo(port);
        var result = http.send(HttpRequest.newBuilder(uri).GET().build(), HttpResponse.BodyHandlers.ofByteArray());
        assertThat(result.statusCode()).as("GET %s", uri.getPath()).isEqualTo(200);
        return result.body();
    }

    @Test
    void servesLocalUiForCanonicalOperations() throws Exception {
        var page = URI.create("http://127.0.0.1:" + port + "/docs/index.html");
        String html = new String(fetch(page), StandardCharsets.UTF_8);
        assertThat(html).contains("SwaggerUIBundle(", "id=\"swagger-ui\"");
        var assets = Pattern.compile("(?:src|href)=\"([^\"]+)\"").matcher(html);
        int count = 0;
        while (assets.find()) {
            assertThat(fetch(page.resolve(assets.group(1))).length).isGreaterThan(1000);
            count++;
        }
        assertThat(count).isGreaterThanOrEqualTo(2);
        var url = Pattern.compile("\\burl:\\s*\"([^\"]+)\"").matcher(html);
        assertThat(url.find()).as("Swagger UI document URL").isTrue();
        byte[] yaml = fetch(page.resolve(url.group(1)));
        assertThat(yaml).isEqualTo(Files.readAllBytes(Path.of("openapi.yaml")));
        Map<String, Object> doc = new Yaml().load(new String(yaml, StandardCharsets.UTF_8));
        Map<?, ?> paths = (Map<?, ?>) doc.get("paths");
        for (var entry : Map.of("/api/v1/shorten", "post", "/api/links/{code}", "get",
                "/{code}", "get", "/api/v1/stats/{code}", "get").entrySet()) {
            assertThat(((Map<?, ?>) paths.get(entry.getKey())).get(entry.getValue())).isNotNull();
        }
    }
}
