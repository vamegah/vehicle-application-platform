package com.autoreliance.platform.postgres;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;
import org.testcontainers.utility.MountableFile;

/**
 * Task 1.3 acceptance tests for platform/postgres/bootstrap/bootstrap.sql (Req 15.1, 15.2, 15.5, 16.4, 21.1).
 *
 * <p>Runs the bootstrap with psql inside the PostgreSQL image pinned in platform/docker-compose.yml, then connects
 * as each per-context login role. All data is fictional.
 */
@Testcontainers
class PostgresBootstrapTest {

    /** The six bounded-context roles; each owns the schema with the same name. */
    static final List<String> CONTEXT_ROLES =
            List.of("data_readiness", "legacy_integration", "integration", "configuration", "release", "audit");

    /** Contexts packaged in one deployable (ADR-005): they still must not see each other's schema. */
    static final List<List<String>> SAME_DEPLOYABLE =
            List.of(List.of("data_readiness", "legacy_integration"), List.of("integration", "configuration"));

    static final UUID TENANT_A = UUID.fromString("0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d");
    static final UUID TENANT_B = UUID.fromString("7f6e5d4c-3b2a-4190-8f7e-6d5c4b3a2910");

    /** Every login role the bootstrap creates: the six context roles and the audit application role. */
    static final List<String> LOGIN_ROLES = java.util.stream.Stream
            .concat(CONTEXT_ROLES.stream(), java.util.stream.Stream.of("audit_app")).toList();

    static final Path PLATFORM = Path.of("").toAbsolutePath().getParent().getParent();

    /** Credentials generated per test run for each login role; never stored. */
    static final Map<String, String> PASSWORDS = new LinkedHashMap<>();

    static {
        LOGIN_ROLES.forEach(role -> PASSWORDS.put(role, UUID.randomUUID().toString()));
    }

    @Container
    static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer(
                    DockerImageName.parse(composePostgresImage()).asCompatibleSubstituteFor("postgres"))
            .withDatabaseName("autoreliance")
            .withUsername("postgres")
            .withPassword(UUID.randomUUID().toString())
            .withCopyFileToContainer(
                    MountableFile.forHostPath(PLATFORM.resolve("postgres/bootstrap/bootstrap.sql")), "/bootstrap/bootstrap.sql");

    /** The PostgreSQL image of the compose file, which equals its ledger row (platform/tests/test_compose_static.py). */
    static String composePostgresImage() {
        try {
            String compose = Files.readString(PLATFORM.resolve("docker-compose.yml"));
            Matcher m = Pattern.compile("(?m)^  postgres:\\s*\\R\\s+image:\\s*(\\S+)").matcher(compose);
            if (!m.find()) {
                throw new IllegalStateException("no postgres image in platform/docker-compose.yml");
            }
            return m.group(1);
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
    }

    static ExecResult runBootstrap() throws Exception {
        List<String> cmd = new ArrayList<>(List.of("psql", "-v", "ON_ERROR_STOP=1", "--no-psqlrc", "-q",
                "-U", "postgres", "-d", "autoreliance"));
        PASSWORDS.forEach((role, pw) -> {
            cmd.add("-v");
            cmd.add(role + "_password=" + pw);
        });
        cmd.addAll(List.of("-f", "/bootstrap/bootstrap.sql"));
        return POSTGRES.execInContainer(cmd.toArray(String[]::new));
    }

    static Connection connect(String role) throws SQLException {
        return DriverManager.getConnection(POSTGRES.getJdbcUrl(), role, PASSWORDS.get(role));
    }

    static Connection superuser() throws SQLException {
        return DriverManager.getConnection(POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword());
    }

    @BeforeAll
    static void bootstrapAndCreateProbeTables() throws Exception {
        ExecResult result = runBootstrap();
        assertThat(result.getExitCode()).as(result.getStderr()).isZero();
        // Each context creates a tenant-scoped table in its own schema, as its migrations will (task 1.5).
        for (String role : CONTEXT_ROLES) {
            try (Connection c = connect(role); Statement s = c.createStatement()) {
                s.execute("CREATE TABLE " + role + ".probe (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, "
                        + "tenant_id uuid NOT NULL, note text NOT NULL)");
                s.execute("SELECT platform.enable_tenant_rls('" + role + ".probe')");
            }
        }
        try (Connection c = connect("audit"); Statement s = c.createStatement()) {
            s.execute("CREATE TABLE audit.audit_record (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, "
                    + "tenant_id uuid NOT NULL, event_id uuid NOT NULL UNIQUE, action text NOT NULL, "
                    + "occurred_at timestamptz NOT NULL, record_hash text NOT NULL, prev_record_hash text)");
            s.execute("SELECT platform.enable_tenant_rls('audit.audit_record')");
        }
    }

    static String sqlState(ThrowingRunnable action) {
        try {
            action.run();
            return "no error";
        } catch (SQLException e) {
            return e.getSQLState();
        }
    }

    interface ThrowingRunnable {
        void run() throws SQLException;
    }

    static void inTenant(Connection c, UUID tenant, String sql) throws SQLException {
        c.setAutoCommit(false);
        try (Statement s = c.createStatement()) {
            s.execute("SET LOCAL app.tenant_id = '" + tenant + "'");
            s.execute(sql);
            c.commit();
        } catch (SQLException e) {
            c.rollback();
            throw e;
        } finally {
            c.setAutoCommit(true);
        }
    }

    static long count(Connection c, String sql) throws SQLException {
        try (Statement s = c.createStatement(); ResultSet rs = s.executeQuery(sql)) {
            rs.next();
            return rs.getLong(1);
        }
    }

    // ------------------------------------------------------------------------------------- cross-schema denial

    @Test
    void everyContextRoleIsDeniedEveryOtherContextsSchema() throws Exception {
        List<String> roles = new ArrayList<>(CONTEXT_ROLES);
        roles.add("audit_app");
        int pairs = 0;
        for (String caller : roles) {
            for (String owner : CONTEXT_ROLES) {
                if (caller.equals(owner) || (caller.equals("audit_app") && owner.equals("audit"))) {
                    continue;
                }
                pairs++;
                try (Connection c = connect(caller); Statement s = c.createStatement()) {
                    String table = owner + ".probe";
                    assertThat(sqlState(() -> s.executeQuery("SELECT count(*) FROM " + table)))
                            .as("%s reads %s", caller, table).isEqualTo("42501");
                    assertThat(sqlState(() -> s.executeUpdate("INSERT INTO " + table + " (tenant_id, note) VALUES ('"
                            + TENANT_A + "', 'x')"))).as("%s writes %s", caller, table).isEqualTo("42501");
                    assertThat(sqlState(() -> s.execute("CREATE TABLE " + owner + ".intruder (id int)")))
                            .as("%s creates in %s", caller, owner).isEqualTo("42501");
                }
            }
        }
        assertThat(pairs).isEqualTo(6 * 5 + 5);
    }

    @Test
    void contextsInTheSameDeployableCannotReadEachOther() throws Exception {
        for (List<String> pair : SAME_DEPLOYABLE) {
            for (int i = 0; i < 2; i++) {
                String caller = pair.get(i);
                String other = pair.get(1 - i);
                try (Connection c = connect(caller); Statement s = c.createStatement()) {
                    assertThat(sqlState(() -> s.executeQuery("SELECT * FROM " + other + ".probe")))
                            .as("%s reads %s in the same deployable", caller, other).isEqualTo("42501");
                }
            }
        }
    }

    @Test
    void noRoleHoldsAnyPrivilegeOnAnotherSchema() throws Exception {
        List<String> roles = new ArrayList<>(CONTEXT_ROLES);
        roles.add("audit_app");
        try (Connection c = superuser(); Statement s = c.createStatement()) {
            for (String role : roles) {
                for (String schema : CONTEXT_ROLES) {
                    boolean own = role.equals(schema) || (role.equals("audit_app") && schema.equals("audit"));
                    try (ResultSet rs = s.executeQuery("SELECT has_schema_privilege('" + role + "', '" + schema
                            + "', 'USAGE'), has_schema_privilege('" + role + "', '" + schema + "', 'CREATE')")) {
                        rs.next();
                        assertThat(rs.getBoolean(1)).as("%s USAGE on %s", role, schema).isEqualTo(own);
                        assertThat(rs.getBoolean(2)).as("%s CREATE on %s", role, schema)
                                .isEqualTo(role.equals(schema));
                    }
                }
            }
        }
    }

    // ------------------------------------------------------------------------------------- row-level security

    @Test
    void queryWithoutTenantInContextReturnsZeroRows() throws Exception {
        try (Connection c = connect("data_readiness")) {
            inTenant(c, TENANT_A, "INSERT INTO probe (tenant_id, note) VALUES ('" + TENANT_A + "', 'fictional a')");
            inTenant(c, TENANT_B, "INSERT INTO probe (tenant_id, note) VALUES ('" + TENANT_B + "', 'fictional b')");
        }
        // A fresh session that never set the tenant: the owning role itself sees nothing (FORCE ROW LEVEL SECURITY).
        try (Connection c = connect("data_readiness")) {
            assertThat(count(c, "SELECT count(*) FROM probe")).isZero();
        }
        // A pooled session after a SET LOCAL transaction ended: the setting is now '' and must still give zero rows.
        try (Connection c = connect("data_readiness")) {
            c.setAutoCommit(false);
            try (Statement s = c.createStatement()) {
                s.execute("SET LOCAL app.tenant_id = '" + TENANT_A + "'");
                assertThat(count(c, "SELECT count(*) FROM probe")).isEqualTo(1);
            }
            c.commit();
            c.setAutoCommit(true);
            assertThat(count(c, "SELECT count(*) WHERE current_setting('app.tenant_id', true) = ''"))
                    .as("PostgreSQL leaves '' in the session after SET LOCAL").isEqualTo(1);
            assertThat(count(c, "SELECT count(*) FROM probe")).isZero();
        }
    }

    @Test
    void aTenantSeesOnlyItsOwnRowsAndCannotWriteAnotherTenantsRow() throws Exception {
        try (Connection c = connect("release")) {
            inTenant(c, TENANT_A, "INSERT INTO probe (tenant_id, note) VALUES ('" + TENANT_A + "', 'fictional a')");
            inTenant(c, TENANT_B, "INSERT INTO probe (tenant_id, note) VALUES ('" + TENANT_B + "', 'fictional b')");
            c.setAutoCommit(false);
            try (Statement s = c.createStatement()) {
                s.execute("SET LOCAL app.tenant_id = '" + TENANT_A + "'");
                assertThat(count(c, "SELECT count(*) FROM probe WHERE tenant_id = '" + TENANT_A + "'")).isPositive();
                assertThat(count(c, "SELECT count(*) FROM probe WHERE tenant_id <> '" + TENANT_A + "'")).isZero();
            }
            c.commit();
            c.setAutoCommit(true);
            assertThat(sqlState(() -> inTenant(c, TENANT_A,
                    "INSERT INTO probe (tenant_id, note) VALUES ('" + TENANT_B + "', 'cross-tenant')")))
                    .as("WITH CHECK rejects a row for another tenant").isEqualTo("42501");
        }
    }

    @Test
    void everyProbeTableHasForcedRlsAndTheTenantPolicy() throws Exception {
        try (Connection c = superuser(); Statement s = c.createStatement();
                ResultSet rs = s.executeQuery("SELECT n.nspname, c.relrowsecurity, c.relforcerowsecurity, p.qual, p.with_check "
                        + "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                        + "LEFT JOIN pg_policies p ON p.schemaname = n.nspname AND p.tablename = c.relname "
                        + "AND p.policyname = 'tenant_isolation' WHERE c.relkind = 'r' AND c.relname IN ('probe', 'audit_record')")) {
            int rows = 0;
            while (rs.next()) {
                rows++;
                assertThat(rs.getBoolean(2)).as("RLS enabled on %s", rs.getString(1)).isTrue();
                assertThat(rs.getBoolean(3)).as("RLS forced on %s", rs.getString(1)).isTrue();
                assertThat(rs.getString(4)).contains("current_setting('app.tenant_id'::text, true)").contains("NULLIF");
                assertThat(rs.getString(5)).contains("current_setting('app.tenant_id'::text, true)");
            }
            assertThat(rows).isEqualTo(CONTEXT_ROLES.size() + 1);
        }
    }

    @Test
    void enableTenantRlsRejectsATableWithoutAUuidTenantId() throws Exception {
        try (Connection c = connect("configuration"); Statement s = c.createStatement()) {
            s.execute("CREATE TABLE no_tenant (id int)");
            assertThat(sqlState(() -> s.execute("SELECT platform.enable_tenant_rls('configuration.no_tenant')")))
                    .isEqualTo("42P16");
            s.execute("CREATE TABLE text_tenant (id int, tenant_id text)");
            assertThat(sqlState(() -> s.execute("SELECT platform.enable_tenant_rls('configuration.text_tenant')")))
                    .isEqualTo("42P16");
            s.execute("DROP TABLE no_tenant, text_tenant");
        }
    }

    @Test
    void enableTenantRlsIsRepeatableAndNotCallableByTheAuditAppRole() throws Exception {
        try (Connection c = connect("integration"); Statement s = c.createStatement()) {
            s.execute("SELECT platform.enable_tenant_rls('integration.probe')");
            s.execute("SELECT platform.enable_tenant_rls('integration.probe')");
            assertThat(count(c, "SELECT count(*) FROM pg_policies WHERE schemaname = 'integration' AND tablename = 'probe'"))
                    .isEqualTo(1);
        }
        try (Connection c = connect("audit_app"); Statement s = c.createStatement()) {
            assertThat(sqlState(() -> s.execute("SELECT platform.enable_tenant_rls('audit.audit_record')")))
                    .isEqualTo("42501");
        }
    }

    // ------------------------------------------------------------------------------------- audit role

    @Test
    void auditAppRoleCanInsertAndSelectButNotUpdateDeleteOrTruncate() throws Exception {
        try (Connection c = connect("audit_app")) {
            inTenant(c, TENANT_A, "INSERT INTO audit_record (tenant_id, event_id, action, occurred_at, record_hash) VALUES ('"
                    + TENANT_A + "', '" + UUID.randomUUID() + "', 'fictional.action', now(), 'h1')");
            c.setAutoCommit(false);
            try (Statement s = c.createStatement()) {
                s.execute("SET LOCAL app.tenant_id = '" + TENANT_A + "'");
                assertThat(count(c, "SELECT count(*) FROM audit_record")).isPositive();
            }
            c.commit();
            c.setAutoCommit(true);
            assertThat(sqlState(() -> inTenant(c, TENANT_A, "UPDATE audit_record SET action = 'tampered'")))
                    .as("UPDATE").isEqualTo("42501");
            assertThat(sqlState(() -> inTenant(c, TENANT_A, "DELETE FROM audit_record"))).as("DELETE").isEqualTo("42501");
            assertThat(sqlState(() -> inTenant(c, TENANT_A, "TRUNCATE audit_record"))).as("TRUNCATE").isEqualTo("42501");
            assertThat(sqlState(() -> inTenant(c, TENANT_A, "CREATE TABLE audit.extra (id int)"))).as("CREATE").isEqualTo("42501");
        }
        try (Connection c = superuser(); Statement s = c.createStatement();
                ResultSet rs = s.executeQuery("SELECT string_agg(privilege_type, ',' ORDER BY privilege_type) "
                        + "FROM information_schema.role_table_grants WHERE grantee = 'audit_app' "
                        + "AND table_schema = 'audit' AND table_name = 'audit_record'")) {
            rs.next();
            assertThat(rs.getString(1)).isEqualTo("INSERT,SELECT");
        }
    }

    // ------------------------------------------------------------------------------------- no shared database

    @Test
    void noSharedTablesAndEachSchemaIsOwnedByItsContextRole() throws Exception {
        try (Connection c = superuser(); Statement s = c.createStatement()) {
            assertThat(count(c, "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    + "WHERE n.nspname IN ('public', 'platform') AND c.relkind IN ('r', 'p', 'v', 'm', 'f')"))
                    .as("the public and platform schemas hold no tables").isZero();
            for (String role : CONTEXT_ROLES) {
                try (ResultSet rs = s.executeQuery("SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = '" + role + "'")) {
                    assertThat(rs.next()).isTrue();
                    assertThat(rs.getString(1)).isEqualTo(role);
                }
            }
            try (ResultSet rs = s.executeQuery("SELECT rolname, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb, rolinherit "
                    + "FROM pg_roles WHERE rolname IN ('data_readiness', 'legacy_integration', 'integration', "
                    + "'configuration', 'release', 'audit', 'audit_app')")) {
                int n = 0;
                while (rs.next()) {
                    n++;
                    for (int col = 2; col <= 6; col++) {
                        assertThat(rs.getBoolean(col)).as("%s attribute %d", rs.getString(1), col).isFalse();
                    }
                }
                assertThat(n).isEqualTo(7);
            }
        }
    }

    @Test
    void bootstrapIsIdempotent() throws Exception {
        ExecResult again = runBootstrap();
        assertThat(again.getExitCode()).as(again.getStderr()).isZero();
        try (Connection c = connect("legacy_integration"); Statement s = c.createStatement()) {
            assertThat(sqlState(() -> s.executeQuery("SELECT * FROM data_readiness.probe"))).isEqualTo("42501");
        }
        try (Connection c = connect("audit_app")) {
            assertThat(sqlState(() -> inTenant(c, TENANT_A, "DELETE FROM audit_record"))).isEqualTo("42501");
        }
    }

    @Test
    void bootstrapPrintsNoPassword() throws Exception {
        ExecResult again = runBootstrap();
        String output = again.getStdout() + again.getStderr();
        for (String pw : PASSWORDS.values()) {
            assertThat(output).doesNotContain(pw);
        }
    }
}
