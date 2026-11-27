package com.autoreliance.apigateway;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Internal liveness probe /api/v1/api-gateway/health contracted in contracts/openapi/api-gateway.yaml (x-internal-only, not routed by the
 * gateway). It depends on no other context, database, broker, or Vault, so it reports healthy when the context
 * runs alone.
 */
@RestController
public class HealthController {

    static final String CONTEXT = "api-gateway";

    /** Body of the contracted Health schema: status is always "up" when the process answers. */
    public record Health(String status, String context) {
    }

    @GetMapping(path = "/api/v1/api-gateway/health", produces = "application/json")
    public Health health() {
        return new Health("up", CONTEXT);
    }
}
