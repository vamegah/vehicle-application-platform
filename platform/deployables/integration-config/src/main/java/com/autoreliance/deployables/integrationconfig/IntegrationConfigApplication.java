package com.autoreliance.deployables.integrationconfig;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.ComponentScan.Filter;
import org.springframework.context.annotation.FilterType;
import org.springframework.context.annotation.FullyQualifiedAnnotationBeanNameGenerator;

/**
 * Deployable integration-config (ADR-005): the integration-intelligence and configuration-assurance contexts in one
 * JVM. It scans both context packages but not their standalone {@code @SpringBootApplication} classes, and names
 * scanned beans by their fully qualified class name, so the two contexts' same-named classes (for example their
 * health controllers) stay separate beans. Each context brings its own datasource, Flyway run, and health
 * indicator ({@code IntegrationIntelligencePersistence}, {@code ConfigurationAssurancePersistence}).
 */
@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan(
        basePackages = {"com.autoreliance.integrationintelligence", "com.autoreliance.configurationassurance"},
        nameGenerator = FullyQualifiedAnnotationBeanNameGenerator.class,
        excludeFilters = @Filter(type = FilterType.ANNOTATION, classes = SpringBootApplication.class))
public class IntegrationConfigApplication {

    public static void main(String[] args) {
        SpringApplication.run(IntegrationConfigApplication.class, args);
    }
}
