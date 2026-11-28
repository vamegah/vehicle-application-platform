package com.autoreliance.legacyintegration;

import java.net.URI;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.health.contributor.HealthIndicator;
import org.springframework.boot.health.contributor.Status;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Internal liveness probe /api/v1/legacy-integration/health contracted in contracts/openapi/legacy-integration.yaml (x-internal-only, not routed by the
 * gateway). It depends on no other context, broker, or Vault: it reports 200 when this context's own database
 * answers and 503 Problem Details when it does not, so a failing context in a shared deployable never hides or
 * drags down the healthy one (ADR-005 rule 5).
 */
@RestController
public class HealthController {

    static final String CONTEXT = "legacy-integration";

    /** Body of the contracted Health schema. */
    public record Health(String status, String context) {
    }

    private final HealthIndicator database;

    public HealthController(@Qualifier(LegacyIntegrationPersistence.HEALTH) HealthIndicator database) {
        this.database = database;
    }

    @GetMapping(path = "/api/v1/legacy-integration/health", produces = {MediaType.APPLICATION_JSON_VALUE, MediaType.APPLICATION_PROBLEM_JSON_VALUE})
    public ResponseEntity<?> health() {
        if (Status.UP.equals(database.health().getStatus())) {
            return ResponseEntity.ok().contentType(MediaType.APPLICATION_JSON).body(new Health("up", CONTEXT));
        }
        ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.SERVICE_UNAVAILABLE);
        problem.setType(URI.create("https://errors.autoreliance.example/unavailable"));
        problem.setTitle("Service Unavailable");
        problem.setDetail("The " + CONTEXT + " context cannot reach its database.");
        problem.setProperty("correlationId", UUID.randomUUID().toString());
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).contentType(MediaType.APPLICATION_PROBLEM_JSON).body(problem);
    }
}
