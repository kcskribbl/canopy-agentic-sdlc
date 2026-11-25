package dev.canopy.inventory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class Inventory {
    public static void main(String[] args) {
        SpringApplication.run(Inventory.class, args);
    }
}

@RestController
class Reservations {
    record Stock(int available) {}

    private int available = 10;

    @GetMapping("/stock")
    public synchronized Stock stock() {
        return new Stock(available);
    }

    @PostMapping("/reservations")
    public synchronized ResponseEntity<Stock> reserve(@RequestParam("units") int units) {
        if (units <= 0) return ResponseEntity.badRequest().build();
        if (units > available) return ResponseEntity.status(409).build();
        available -= units;
        return ResponseEntity.status(201).body(stock());
    }
}
