package dev.canopy.inventory;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class InventoryTest {
    private final MockMvc api = MockMvcBuilders.standaloneSetup(new Reservations()).build();

    @Test
    void reservesAvailableStock() throws Exception {
        stockIs(10);
        api.perform(post("/reservations").param("units", "3")).andExpect(status().isCreated())
                .andExpect(jsonPath("$.available").value(7));
        stockIs(7);
    }

    @Test
    void rejectionPreservesStock() throws Exception {
        api.perform(post("/reservations").param("units", "11")).andExpect(status().isConflict());
        stockIs(10);
    }

    @Test
    void nonpositiveQuantityIsRejected() throws Exception {
        for (String units : new String[]{"0", "-1"}) {
            api.perform(post("/reservations").param("units", units)).andExpect(status().isBadRequest());
            stockIs(10);
        }
    }

    private void stockIs(int expected) throws Exception {
        api.perform(get("/stock")).andExpect(status().isOk()).andExpect(jsonPath("$.available").value(expected));
    }
}
