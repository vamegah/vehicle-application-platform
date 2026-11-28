package com.autoreliance.testsupport.postgres;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;
import org.testcontainers.utility.MountableFile;

/**
 * One PostgreSQL container per test JVM, bootstrapped exactly as compose bootstraps it (task 1.3): the image pinned
 * in {@code platform/docker-compose.yml} and the script {@code platform/postgres/bootstrap/bootstrap.sql}. Each
 * login role gets a random credential for this run only; nothing is stored.
 */
public final class BootstrappedPostgres {

    /** Every login role the bootstrap creates. */
    public static final List<String> LOGIN_ROLES = List.of("data_readiness", "legacy_integration", "integration",
            "configuration", "release", "audit", "audit_app");

    private static BootstrappedPostgres shared;

    private final PostgreSQLContainer container;
    private final Map<String, String> credentials = new LinkedHashMap<>();

    private BootstrappedPostgres() {
        Path platform = platformDir();
        LOGIN_ROLES.forEach(role -> credentials.put(role, UUID.randomUUID().toString()));
        container = new PostgreSQLContainer(
                        DockerImageName.parse(composePostgresImage(platform)).asCompatibleSubstituteFor("postgres"))
                .withDatabaseName("autoreliance")
                .withUsername("postgres")
                .withPassword(UUID.randomUUID().toString())
                .withCopyFileToContainer(MountableFile.forHostPath(platform.resolve("postgres/bootstrap/bootstrap.sql")),
                        "/bootstrap/bootstrap.sql");
        container.start();
        runBootstrap();
    }

    /** The shared, started, bootstrapped instance of this JVM. */
    public static synchronized BootstrappedPostgres shared() {
        if (shared == null) {
            shared = new BootstrappedPostgres();
        }
        return shared;
    }

    public String jdbcUrl() {
        return container.getJdbcUrl();
    }

    /** The credential of a login role for this test run. */
    public String credentialFor(String role) {
        String value = credentials.get(role);
        if (value == null) {
            throw new IllegalArgumentException("not a bootstrap login role: " + role);
        }
        return value;
    }

    public String superuser() {
        return container.getUsername();
    }

    public String superuserCredential() {
        return container.getPassword();
    }

    private void runBootstrap() {
        List<String> cmd = new ArrayList<>(List.of("psql", "-v", "ON_ERROR_STOP=1", "--no-psqlrc", "-q",
                "-U", "postgres", "-d", "autoreliance"));
        credentials.forEach((role, value) -> {
            cmd.add("-v");
            cmd.add(role + "_password=" + value);
        });
        cmd.addAll(List.of("-f", "/bootstrap/bootstrap.sql"));
        try {
            ExecResult result = container.execInContainer(cmd.toArray(String[]::new));
            if (result.getExitCode() != 0) {
                throw new IllegalStateException("bootstrap.sql failed: " + result.getStderr());
            }
        } catch (IOException e) {
            throw new IllegalStateException(e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }

    /** The repository's platform/ directory, found by walking up from the working directory. */
    static Path platformDir() {
        Path dir = Path.of("").toAbsolutePath();
        while (dir != null) {
            if (Files.isRegularFile(dir.resolve("platform/docker-compose.yml"))) {
                return dir.resolve("platform");
            }
            dir = dir.getParent();
        }
        throw new IllegalStateException("platform/docker-compose.yml not found above " + Path.of("").toAbsolutePath());
    }

    /** The PostgreSQL image of the compose file, which equals its ledger row. */
    static String composePostgresImage(Path platform) {
        try {
            String compose = Files.readString(platform.resolve("docker-compose.yml"));
            Matcher m = Pattern.compile("(?m)^  postgres:\\s*\\R\\s+image:\\s*(\\S+)").matcher(compose);
            if (!m.find()) {
                throw new IllegalStateException("no postgres image in platform/docker-compose.yml");
            }
            return m.group(1);
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
    }
}
