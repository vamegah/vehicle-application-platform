package com.autoreliance.releaseassurance;

import static org.assertj.core.api.Assertions.assertThat;

import com.autoreliance.testsupport.postgres.BootstrappedPostgres;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.List;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * Smoke and migration test (tasks 1.1 and 1.5). The context starts with only PostgreSQL running (no other context,
 * broker, or Vault), applies its Flyway migrations to an empty, bootstrapped database as its own login role, and its
 * contracted health route returns 200. The application JSON mapper is the Jackson 3 JsonMapper (ADR-006).
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HealthSmokeTest {

    static final String SCHEMA = "release";
    static final List<String> BASELINE_TABLES = List.of("outbox", "inbox_event");

    @DynamicPropertySource
    static void database(DynamicPropertyRegistry registry) {
        BootstrappedPostgres pg = BootstrappedPostgres.shared();
        registry.add("spring.datasource.url", pg::jdbcUrl);
        registry.add("spring.datasource.password", () -> pg.credentialFor(SCHEMA));
    }

    @Value("${local.server.port}")
    int port;

    @Autowired
    JsonMapper jsonMapper;

    @Autowired
    DataSource dataSource;

    @Test
    void contractedHealthRouteReturns200() throws Exception {
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

    @Test
    void flywayRanAsTheContextRoleInItsOwnSchema() {
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        assertThat(jdbc.queryForObject("SELECT current_user", String.class)).isEqualTo(SCHEMA);
        assertThat(jdbc.queryForObject("SELECT count(*) FROM " + SCHEMA + ".flyway_schema_history WHERE success", Integer.class))
                .isPositive();
        assertThat(jdbc.queryForObject("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                + "WHERE c.relname = 'flyway_schema_history' AND n.nspname <> ?", Integer.class, SCHEMA))
                .as("no Flyway history table outside the context schema").isZero();
    }

    @Test
    void baselineTablesAreTenantScopedWithForcedRlsAndOwnedByTheRole() {
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        List<String> tables = jdbc.queryForList("SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                + "WHERE n.nspname = ? AND c.relkind = 'r' AND c.relname <> 'flyway_schema_history' ORDER BY 1", String.class, SCHEMA);
        assertThat(tables).containsExactlyInAnyOrderElementsOf(BASELINE_TABLES);
        for (String table : BASELINE_TABLES) {
            var row = jdbc.queryForMap("SELECT c.relrowsecurity, c.relforcerowsecurity, pg_get_userbyid(c.relowner) AS owner, "
                    + "(SELECT count(*) FROM pg_policies p WHERE p.schemaname = n.nspname AND p.tablename = c.relname "
                    + "AND p.policyname = 'tenant_isolation') AS policies, "
                    + "(SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attname = 'tenant_id') AS tenant_type "
                    + "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = ? AND c.relname = ?", SCHEMA, table);
            assertThat(row.get("relrowsecurity")).as("%s RLS enabled", table).isEqualTo(true);
            assertThat(row.get("relforcerowsecurity")).as("%s RLS forced", table).isEqualTo(true);
            assertThat(row.get("owner")).as("%s owner", table).isEqualTo(SCHEMA);
            assertThat(((Number) row.get("policies")).intValue()).as("%s policy", table).isEqualTo(1);
            assertThat(row.get("tenant_type")).as("%s tenant_id type", table).isEqualTo("uuid");
            assertThat(jdbc.queryForObject("SELECT count(*) FROM " + SCHEMA + "." + table, Integer.class))
                    .as("%s without a tenant in context", table).isZero();
        }
    }
}
