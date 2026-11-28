package com.autoreliance.deployables.integrationconfig;

import static org.assertj.core.api.Assertions.assertThat;

import com.autoreliance.configurationassurance.ConfigurationAssurancePersistence;
import com.autoreliance.integrationintelligence.IntegrationIntelligencePersistence;
import com.zaxxer.hikari.HikariDataSource;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * Task 1.6 health-group test (ADR-005 rule 5): when one context in integration-config loses its database, its own
 * health group and contracted health route report unavailable, and the other context still reports healthy.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@DirtiesContext
class HealthGroupIsolationTest {

    @DynamicPropertySource
    static void databases(DynamicPropertyRegistry registry) {
        IntegrationConfigPackagingTest.register(registry, IntegrationIntelligencePersistence.SCHEMA);
        IntegrationConfigPackagingTest.register(registry, ConfigurationAssurancePersistence.SCHEMA);
    }

    @Value("${local.server.port}")
    int port;

    @Autowired
    JsonMapper jsonMapper;

    @Autowired
    @Qualifier(IntegrationIntelligencePersistence.DATA_SOURCE)
    HikariDataSource integration;

    HttpResponse<String> get(String path) throws Exception {
        try (HttpClient client = HttpClient.newHttpClient()) {
            return client.send(HttpRequest.newBuilder(URI.create("http://localhost:" + port + path)).GET().build(),
                    HttpResponse.BodyHandlers.ofString());
        }
    }

    @Test
    void aContextWithoutItsDatabaseReportsUnavailableWhileTheOtherStaysHealthy() throws Exception {
        assertThat(get("/api/v1/integration-intelligence/health").statusCode()).isEqualTo(200);

        integration.close(); // the integration context loses its database; the configuration context keeps its own

        HttpResponse<String> down = get("/api/v1/integration-intelligence/health");
        assertThat(down.statusCode()).isEqualTo(503);
        assertThat(down.headers().firstValue("Content-Type")).hasValueSatisfying(v -> assertThat(v).startsWith("application/problem+json"));
        JsonNode problem = jsonMapper.readTree(down.body());
        for (String member : new String[] {"type", "title", "status", "correlationId"}) {
            assertThat(problem.has(member)).as("Problem member %s", member).isTrue();
        }
        assertThat(problem.get("status").asInt()).isEqualTo(503);
        assertThat(get("/actuator/health/integration-intelligence").statusCode()).isEqualTo(503);

        HttpResponse<String> up = get("/api/v1/configuration-assurance/health");
        assertThat(up.statusCode()).isEqualTo(200);
        assertThat(jsonMapper.readTree(up.body()).get("context").asString()).isEqualTo("configuration-assurance");
        HttpResponse<String> group = get("/actuator/health/configuration-assurance");
        assertThat(group.statusCode()).isEqualTo(200);
        assertThat(jsonMapper.readTree(group.body()).get("status").asString()).isEqualTo("UP");
    }
}
