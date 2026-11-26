package com.autoreliance.verification;

import static org.assertj.core.api.Assertions.assertThat;

import au.com.dius.pact.consumer.MockServer;
import au.com.dius.pact.consumer.dsl.PactDslWithProvider;
import au.com.dius.pact.consumer.junit5.PactConsumerTestExt;
import au.com.dius.pact.consumer.junit5.PactTestFor;
import au.com.dius.pact.core.model.PactSpecVersion;
import au.com.dius.pact.core.model.V4Pact;
import au.com.dius.pact.core.model.annotations.Pact;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

/** Task 1.4(d): Pact JVM 4.7.7 consumer test runs on the JUnit 6.0.3 platform. */
@ExtendWith(PactConsumerTestExt.class)
@PactTestFor(providerName = "smoke-provider", pactVersion = PactSpecVersion.V4)
class PactConsumerSmokeTest {

    @Pact(consumer = "smoke-consumer")
    V4Pact pact(PactDslWithProvider builder) {
        return builder.given("a resource exists")
                .uponReceiving("a health request")
                .path("/health")
                .method("GET")
                .willRespondWith()
                .status(200)
                .toPact(V4Pact.class);
    }

    @Test
    void consumerCallsMockProvider(MockServer mockServer) throws Exception {
        HttpResponse<String> response = HttpClient.newHttpClient().send(
                HttpRequest.newBuilder(URI.create(mockServer.getUrl() + "/health")).GET().build(),
                HttpResponse.BodyHandlers.ofString());
        assertThat(response.statusCode()).isEqualTo(200);
    }
}
