package com.autoreliance.verification;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.security.SecureRandom;
import java.util.HexFormat;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.images.builder.Transferable;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.NoSuchKeyException;

/**
 * ADR-013: put, get, head, and delete against the digest-pinned Garage image with the when-required
 * client (path-style, region "garage"). The object-store test uses a GenericContainer, not an
 * object-store-specific Testcontainers module. The container's RPC secret and the S3 key are generated
 * at run time inside a throwaway container; nothing is committed.
 */
@Testcontainers(disabledWithoutDocker = true)
class GarageS3SmokeTest {

    private static final String BUCKET = "autoreliance-text-dev";
    private static GenericContainer<?> garage;
    private static URI endpoint;
    private static String accessKey;
    private static String secretKey;

    @BeforeAll
    static void startGarage() throws Exception {
        byte[] rpc = new byte[32];
        new SecureRandom().nextBytes(rpc);
        String config = """
                metadata_dir = "/tmp/meta"
                data_dir = "/tmp/data"
                db_engine = "sqlite"
                replication_factor = 1
                rpc_bind_addr = "[::]:3901"
                rpc_public_addr = "127.0.0.1:3901"
                rpc_secret = "%s"

                [s3_api]
                s3_region = "garage"
                api_bind_addr = "[::]:3900"
                root_domain = ".s3.garage.localhost"
                """.formatted(HexFormat.of().formatHex(rpc));
        garage = new GenericContainer<>(DockerImageName.parse(System.getProperty("garage.image")))
                .withCopyToContainer(Transferable.of(config), "/etc/garage.toml")
                .withExposedPorts(3900)
                .waitingFor(Wait.forListeningPort());
        garage.start();

        exec("/garage", "layout", "assign", "-z", "dc1", "-c", "1G", awaitNodeId());
        exec("/garage", "layout", "apply", "--version", "1");
        exec("/garage", "bucket", "create", BUCKET);
        String key = exec("/garage", "key", "create", "smoke").getStdout();
        accessKey = group(key, "Key ID:\\s*(\\S+)");
        secretKey = group(key, "Secret key:\\s*(\\S+)");
        exec("/garage", "bucket", "allow", "--read", "--write", "--owner", BUCKET, "--key", "smoke");
        endpoint = URI.create("http://" + garage.getHost() + ":" + garage.getMappedPort(3900));
        Thread.sleep(2000); // layout propagation
    }

    @AfterAll
    static void stopGarage() {
        if (garage != null) {
            garage.stop();
        }
    }

    /**
     * The S3 port opens before Garage has written its node key to the metadata directory, so an early
     * `garage status` fails with "Unable to read node key" (seen on a slow CI runner). Retry until the
     * node reports its ID, for at most 60 seconds, then fail with the last output.
     */
    private static String awaitNodeId() throws Exception {
        Pattern nodeId = Pattern.compile("([0-9a-f]{16})\\s");
        long deadline = System.nanoTime() + java.util.concurrent.TimeUnit.SECONDS.toNanos(60);
        ExecResult last;
        do {
            last = garage.execInContainer("/garage", "status");
            if (last.getExitCode() == 0) {
                Matcher m = nodeId.matcher(last.getStdout());
                if (m.find()) {
                    return m.group(1);
                }
            }
            Thread.sleep(500);
        } while (System.nanoTime() < deadline);
        throw new AssertionError("Garage node did not report its ID within 60 s: " + last.getStdout() + " " + last.getStderr());
    }

    private static ExecResult exec(String... cmd) throws Exception {
        ExecResult r = garage.execInContainer(cmd);
        assertThat(r.getExitCode()).as("%s -> %s %s", String.join(" ", cmd), r.getStdout(), r.getStderr()).isZero();
        return r;
    }

    private static String group(String text, String regex) {
        Matcher m = Pattern.compile(regex).matcher(text);
        assertThat(m.find()).as("%s in: %s", regex, text.replaceAll("(?i)(secret key:\\s*)\\S+", "$1***")).isTrue();
        return m.group(1);
    }

    @Test
    void putGetHeadDeleteWithWhenRequiredChecksums() {
        String key = "tenant-smoke/text/smoke.txt";
        try (S3Client s3 = S3ClientFactory.whenRequired(endpoint, "garage", accessKey, secretKey)) {
            s3.putObject(b -> b.bucket(BUCKET).key(key), RequestBody.fromString("hello"));
            assertThat(s3.getObjectAsBytes(b -> b.bucket(BUCKET).key(key)).asUtf8String()).isEqualTo("hello");
            assertThat(s3.headObject(b -> b.bucket(BUCKET).key(key)).contentLength()).isEqualTo(5L);
            s3.deleteObject(b -> b.bucket(BUCKET).key(key));
            try {
                s3.getObjectAsBytes(b -> b.bucket(BUCKET).key(key));
                throw new AssertionError("object still readable after delete");
            } catch (NoSuchKeyException expected) {
                // deleted
            }
        }
    }

    /** Records, without failing, whether Garage also accepts the SDK default checksums. */
    @Test
    void recordWhetherGarageAcceptsSdkDefaultChecksums() {
        String key = "tenant-smoke/text/default-checksum.txt";
        boolean accepted;
        try (S3Client s3 = S3ClientFactory.sdkDefault(endpoint, "garage", accessKey, secretKey)) {
            s3.putObject(b -> b.bucket(BUCKET).key(key), RequestBody.fromString("hello"));
            s3.deleteObject(b -> b.bucket(BUCKET).key(key));
            accepted = true;
        } catch (RuntimeException e) {
            accepted = false;
            System.out.println("GARAGE_DEFAULT_CHECKSUM_ERROR=" + e.getClass().getSimpleName());
        }
        System.out.println("GARAGE_ACCEPTS_SDK_DEFAULT_CHECKSUMS=" + accepted + " (java)");
    }
}
