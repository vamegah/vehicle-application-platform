package com.autoreliance.releaseassurance;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * Task 1.1 smoke test: the context starts alone (no other context, database, broker, or Vault running) on a real
 * port and its contracted health route returns 200 with the Health body. The application JSON mapper is the
 * Jackson 3 JsonMapper (ADR-006).
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HealthSmokeTest {

    @Value("${local.server.port}")
    int port;

    @Autowired
    JsonMapper jsonMapper;

    @Test
    void contractedHealthRouteReturns200WhenRunningAlone() throws Exception {
        HttpResponse<String> response;
        try (HttpClient client = HttpClient.newHttpClient()) {
            HttpRequest request = HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/api/v1/release-assurance/health")).GET().build();
            response = client.send(request, HttpResponse.BodyHandlers.ofString());
        }
        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.headers().firstValue("Content-Type")).hasValueSatisfying(v -> assertThat(v).startsWith("application/json"));
        JsonNode body = jsonMapper.readTree(response.body());
        assertThat(body.get("status").asString()).isEqualTo("up");
        assertThat(body.get("context").asString()).isEqualTo("release-assurance");
        assertThat(body.size()).isEqualTo(2);
    }

    @Test
    void applicationJsonMapperIsJackson3() {
        assertThat(jsonMapper).isInstanceOf(tools.jackson.databind.json.JsonMapper.class);
    }
}
