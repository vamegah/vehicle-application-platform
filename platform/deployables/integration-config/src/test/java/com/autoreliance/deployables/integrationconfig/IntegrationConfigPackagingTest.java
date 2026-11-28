package com.autoreliance.deployables.integrationconfig;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.autoreliance.configurationassurance.ConfigurationAssurancePersistence;
import com.autoreliance.integrationintelligence.IntegrationIntelligencePersistence;
import com.autoreliance.testsupport.postgres.BootstrappedPostgres;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.List;
import java.util.Map;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.BadSqlGrammarException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * Task 1.6 packaging tests of the integration-config deployable (ADR-005, Req 21.1, 21.4): both contexts start in
 * one JVM with only PostgreSQL running, each with its own datasource and login role, its own Flyway history in its
 * own schema, and its own health group; neither can read the other's tables.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class IntegrationConfigPackagingTest {

    static void register(DynamicPropertyRegistry registry, String schema) {
        BootstrappedPostgres pg = BootstrappedPostgres.shared();
        registry.add("autoreliance.db." + schema + ".url", pg::jdbcUrl);
        registry.add("autoreliance.db." + schema + ".password", () -> pg.credentialFor(schema));
    }

    @DynamicPropertySource
    static void databases(DynamicPropertyRegistry registry) {
        register(registry, IntegrationIntelligencePersistence.SCHEMA);
        register(registry, ConfigurationAssurancePersistence.SCHEMA);
    }

    @Value("${local.server.port}")
    int port;

    @Autowired
    JsonMapper jsonMapper;

    @Autowired
    @Qualifier(IntegrationIntelligencePersistence.DATA_SOURCE)
    DataSource integration;

    @Autowired
    @Qualifier(ConfigurationAssurancePersistence.DATA_SOURCE)
    DataSource configuration;

    @Autowired
    List<DataSource> allDataSources;

    HttpResponse<String> get(String path) throws Exception {
        try (HttpClient client = HttpClient.newHttpClient()) {
            return client.send(HttpRequest.newBuilder(URI.create("http://localhost:" + port + path)).GET().build(),
                    HttpResponse.BodyHandlers.ofString());
        }
    }

    @Test
    void bothContextsServeTheirContractedHealthRouteFromOneJvm() throws Exception {
        for (var entry : Map.of("/api/v1/integration-intelligence/health", "integration-intelligence",
                "/api/v1/configuration-assurance/health", "configuration-assurance").entrySet()) {
            HttpResponse<String> response = get(entry.getKey());
            assertThat(response.statusCode()).as(entry.getKey()).isEqualTo(200);
            JsonNode body = jsonMapper.readTree(response.body());
            assertThat(body.get("status").asString()).isEqualTo("up");
            assertThat(body.get("context").asString()).isEqualTo(entry.getValue());
        }
    }

    @Test
    void eachContextHasItsOwnHealthGroup() throws Exception {
        for (String group : List.of("integration-intelligence", "configuration-assurance")) {
            HttpResponse<String> response = get("/actuator/health/" + group);
            assertThat(response.statusCode()).as(group).isEqualTo(200);
            assertThat(jsonMapper.readTree(response.body()).get("status").asString()).isEqualTo("UP");
        }
    }

    @Test
    void theDeployableHasExactlyTwoDatasourcesEachAsItsOwnRole() {
        assertThat(allDataSources).hasSize(2);
        assertThat(new JdbcTemplate(integration).queryForObject("SELECT current_user", String.class)).isEqualTo("integration");
        assertThat(new JdbcTemplate(configuration).queryForObject("SELECT current_user", String.class)).isEqualTo("configuration");
    }

    @Test
    void eachContextMigratedOnlyItsOwnSchema() {
        for (var entry : Map.of("integration", integration, "configuration", configuration).entrySet()) {
            JdbcTemplate jdbc = new JdbcTemplate(entry.getValue());
            String schema = entry.getKey();
            assertThat(jdbc.queryForObject("SELECT count(*) FROM " + schema + ".flyway_schema_history WHERE success", Integer.class))
                    .as("%s Flyway history", schema).isPositive();
            assertThat(jdbc.queryForList("SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    + "WHERE n.nspname = ? AND c.relkind = 'r' ORDER BY 1", String.class, schema))
                    .containsExactly("flyway_schema_history", "inbox_event", "outbox");
            assertThat(jdbc.queryForObject("SELECT bool_and(c.relforcerowsecurity) FROM pg_class c JOIN pg_namespace n "
                    + "ON n.oid = c.relnamespace WHERE n.nspname = ? AND c.relname IN ('outbox', 'inbox_event')", Boolean.class, schema))
                    .isTrue();
        }
    }

    @Test
    void neitherContextCanReadTheOthersTables() {
        JdbcTemplate fromIntegration = new JdbcTemplate(integration);
        JdbcTemplate fromConfiguration = new JdbcTemplate(configuration);
        assertThatThrownBy(() -> fromIntegration.queryForObject("SELECT count(*) FROM configuration.outbox", Integer.class))
                .isInstanceOfSatisfying(BadSqlGrammarException.class, e -> assertThat(e.getSQLException().getSQLState()).isEqualTo("42501"));
        assertThatThrownBy(() -> fromConfiguration.queryForObject("SELECT count(*) FROM integration.outbox", Integer.class))
                .isInstanceOfSatisfying(BadSqlGrammarException.class, e -> assertThat(e.getSQLException().getSQLState()).isEqualTo("42501"));
        assertThatThrownBy(() -> fromIntegration.queryForObject("SELECT count(*) FROM configuration.flyway_schema_history", Integer.class))
                .isInstanceOfSatisfying(BadSqlGrammarException.class, e -> assertThat(e.getSQLException().getSQLState()).isEqualTo("42501"));
    }
}
