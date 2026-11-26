package com.autoreliance.verification;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.vault.core.VaultTemplate;

/** ADR-010: the runtime jar for spring-vault-core is 4.1.2, not the Cloud BOM's managed 4.0.x. */
class VaultVersionSmokeTest {

    @Test
    void springVaultCoreRuntimeVersionIs412() {
        assertThat(VaultTemplate.class.getPackage().getImplementationVersion()).isEqualTo("4.1.2");
    }
}
