package com.autoreliance.legacyintegration;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Internal liveness probe /api/v1/legacy-integration/health contracted in contracts/openapi/legacy-integration.yaml (x-internal-only, not routed by the
 * gateway). It depends on no other context, database, broker, or Vault, so it reports healthy when the context
 * runs alone.
 */
@RestController
public class HealthController {

    static final String CONTEXT = "legacy-integration";

    /** Body of the contracted Health schema: status is always "up" when the process answers. */
    public record Health(String status, String context) {
    }

    @GetMapping(path = "/api/v1/legacy-integration/health", produces = "application/json")
    public Health health() {
        return new Health("up", CONTEXT);
    }
}
