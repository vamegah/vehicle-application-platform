package com.autoreliance.verification;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.gateway.route.RouteLocator;
import tools.jackson.databind.json.JsonMapper;

/**
 * ADR-006: the gateway starts on Spring Boot 4.1.3 with Spring Cloud BOM 2025.1.5, and the
 * application JsonMapper is the Jackson 3 mapper. Also asserts Jackson 2 databind is absent.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GatewayAndJacksonSmokeTest {

    @Autowired
    JsonMapper jsonMapper;

    @Autowired
    RouteLocator routeLocator;

    @Test
    void applicationJsonMapperBeanIsJackson3() {
        assertThat(jsonMapper).isInstanceOf(tools.jackson.databind.json.JsonMapper.class);
        assertThat(jsonMapper.getClass().getName()).isEqualTo("tools.jackson.databind.json.JsonMapper");
    }

    @Test
    void jackson2ObjectMapperIsNotOnTheClasspath() {
        assertThatThrownBy(() -> Class.forName("com.fasterxml.jackson.databind.ObjectMapper"))
                .isInstanceOf(ClassNotFoundException.class);
    }

    @Test
    void gatewayContextStartsAndLoadsConfiguredRoute() {
        var routes = routeLocator.getRoutes().collectList().block();
        assertThat(routes).extracting(r -> r.getId()).contains("smoke");
    }
}
