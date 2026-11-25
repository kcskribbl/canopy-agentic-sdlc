package dev.canopy.inventory;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        useMainMethod = SpringBootTest.UseMainMethod.ALWAYS, properties = "server.address=127.0.0.1")
class InventoryHttpTest {
    @Autowired TestRestTemplate http;

    @Test
    void runningServiceCanSellOutWithoutOverselling() {
        var sold = http.postForEntity("/reservations?units=10", null, Reservations.Stock.class);
        assertThat(sold.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        assertThat(sold.getBody()).isEqualTo(new Reservations.Stock(0));
        var refused = http.postForEntity("/reservations?units=1", null, String.class);
        assertThat(refused.getStatusCode()).isEqualTo(HttpStatus.CONFLICT);
        assertThat(http.getForObject("/stock", Reservations.Stock.class)).isEqualTo(new Reservations.Stock(0));
    }
}
