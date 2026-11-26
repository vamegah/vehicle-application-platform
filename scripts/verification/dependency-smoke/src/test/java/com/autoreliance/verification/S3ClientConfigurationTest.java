package com.autoreliance.verification;

import static org.assertj.core.api.Assertions.assertThat;

import com.sun.net.httpserver.HttpServer;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.util.Map;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.stream.Collectors;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;

/**
 * ADR-013: the S3 client is built with when-required checksums. Verified on the wire against a local
 * HTTP server: a PutObject from the configured client carries no checksum header, while a client
 * built with SDK defaults does (so the test can tell the two apart). Test credentials are fake.
 */
class S3ClientConfigurationTest {

    private HttpServer server;
    private final ConcurrentLinkedQueue<Map<String, String>> puts = new ConcurrentLinkedQueue<>();
    private URI endpoint;

    @BeforeEach
    void start() throws Exception {
        server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        server.createContext("/", exchange -> {
            if ("PUT".equals(exchange.getRequestMethod())) {
                puts.add(exchange.getRequestHeaders().entrySet().stream()
                        .collect(Collectors.toMap(e -> e.getKey().toLowerCase(), e -> String.join(",", e.getValue()))));
            }
            exchange.getRequestBody().readAllBytes();
            exchange.getResponseHeaders().add("ETag", "\"d41d8cd98f00b204e9800998ecf8427e\"");
            exchange.sendResponseHeaders(200, -1);
            exchange.close();
        });
        server.start();
        endpoint = URI.create("http://127.0.0.1:" + server.getAddress().getPort());
    }

    @AfterEach
    void stop() {
        server.stop(0);
    }

    private static boolean hasChecksumHeader(Map<String, String> headers) {
        return headers.keySet().stream()
                .anyMatch(k -> k.startsWith("x-amz-checksum-") || k.equals("x-amz-sdk-checksum-algorithm"));
    }

    @Test
    void whenRequiredClientSendsNoChecksumHeaders() {
        try (S3Client s3 = S3ClientFactory.whenRequired(endpoint, "garage", "TESTKEYID", "testsecret")) {
            s3.putObject(b -> b.bucket("b").key("k"), RequestBody.fromString("hello"));
        }
        assertThat(puts).hasSize(1);
        assertThat(hasChecksumHeader(puts.peek())).as("headers: %s", puts.peek()).isFalse();
    }

    @Test
    void sdkDefaultClientSendsChecksumHeaders() {
        try (S3Client s3 = S3ClientFactory.sdkDefault(endpoint, "garage", "TESTKEYID", "testsecret")) {
            s3.putObject(b -> b.bucket("b").key("k"), RequestBody.fromString("hello"));
        }
        assertThat(puts).hasSize(1);
        assertThat(hasChecksumHeader(puts.peek())).as("headers: %s", puts.peek()).isTrue();
    }
}
