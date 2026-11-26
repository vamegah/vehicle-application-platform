package com.autoreliance.verification;

import static org.assertj.core.api.Assertions.assertThat;

import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import org.junit.jupiter.api.Test;

/**
 * Task 1.4(d): jqwik 1.10.2 runs on the JUnit 6.0.3 platform that Spring Boot 4.1.3 manages
 * (see PactConsumerSmokeTest for Pact JVM). Fails the build if either engine does not run.
 */
class TestFrameworkCompatibilityTest {

    @Property
    void jqwikPropertyRunsOnJUnit6(@ForAll int a, @ForAll int b) {
        assertThat(a + b).isEqualTo(b + a);
    }

    @Test
    void junitJupiterTestRuns() {
        assertThat(1 + 1).isEqualTo(2);
    }
}
