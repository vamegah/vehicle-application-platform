package com.autoreliance.auditsink;

import com.zaxxer.hikari.HikariDataSource;
import java.sql.Connection;
import javax.sql.DataSource;
import org.flywaydb.core.Flyway;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.HealthIndicator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * The audit-sink context's own database wiring (tasks 1.5 and 1.6): one datasource that always connects as the
 * `audit` login role, one Flyway run in the `audit` schema at startup, and one health indicator. Every bean
 * is named after the schema, so this context can share a JVM with another context (deployable integration-config,
 * ADR-005) without sharing a datasource, a migration history, or a health status.
 *
 * <p>Configuration (environment; Vault from task 4.4): AUTORELIANCE_DB_AUDIT_URL and AUTORELIANCE_DB_AUDIT_PASSWORD
 * (properties autoreliance.db.audit.url and autoreliance.db.audit.password). Startup fails when either is missing.
 */
@Configuration(proxyBeanMethods = false)
public class AuditSinkPersistence {

    public static final String SCHEMA = "audit";
    public static final String DATA_SOURCE = "auditDataSource";
    public static final String FLYWAY = "auditFlyway";
    public static final String JDBC = "auditJdbcTemplate";
    /** Health contributor name; the deployable's health group for this context includes it. */
    public static final String HEALTH = "auditDatabase";

    @Bean(name = DATA_SOURCE, destroyMethod = "close")
    public HikariDataSource auditDataSource(Environment env) {
        HikariDataSource ds = new HikariDataSource();
        ds.setPoolName(SCHEMA);
        ds.setJdbcUrl(env.getRequiredProperty("autoreliance.db." + SCHEMA + ".url"));
        ds.setUsername(SCHEMA);
        ds.setPassword(env.getRequiredProperty("autoreliance.db." + SCHEMA + ".password"));
        ds.setSchema(SCHEMA);
        ds.setMaximumPoolSize(env.getProperty("autoreliance.db." + SCHEMA + ".pool-size", Integer.class, 5));
        return ds;
    }

    @Bean(name = FLYWAY, initMethod = "migrate")
    public Flyway auditFlyway(@Qualifier(DATA_SOURCE) DataSource dataSource) {
        return Flyway.configure()
                .dataSource(dataSource)
                .schemas(SCHEMA)
                .defaultSchema(SCHEMA)
                .createSchemas(false)
                .table("flyway_schema_history")
                .locations("classpath:db/migration/" + SCHEMA)
                .load();
    }

    @Bean(name = JDBC)
    public JdbcTemplate auditJdbcTemplate(@Qualifier(DATA_SOURCE) DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean(name = HEALTH)
    public HealthIndicator auditDatabase(@Qualifier(DATA_SOURCE) DataSource dataSource) {
        return () -> {
            try (Connection c = dataSource.getConnection()) {
                return c.isValid(2) ? Health.up().withDetail("schema", SCHEMA).build()
                        : Health.down().withDetail("schema", SCHEMA).build();
            } catch (Exception e) {
                return Health.down().withDetail("schema", SCHEMA).withDetail("error", e.getClass().getSimpleName()).build();
            }
        };
    }
}
