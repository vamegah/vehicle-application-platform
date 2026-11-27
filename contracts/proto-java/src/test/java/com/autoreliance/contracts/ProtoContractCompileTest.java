package com.autoreliance.contracts;

import static org.assertj.core.api.Assertions.assertThat;

import com.autoreliance.contracts.configuration.v1.ConfigValidationServiceGrpc;
import com.autoreliance.contracts.configuration.v1.RuleCategory;
import com.autoreliance.contracts.configuration.v1.RuleResult;
import com.autoreliance.contracts.configuration.v1.ValidateConfigurationRequest;
import com.autoreliance.contracts.configuration.v1.ValidateConfigurationResponse;
import com.autoreliance.contracts.configuration.v1.ValidationStatus;
import com.autoreliance.contracts.integration.v1.GetSnapshotGraphFactsRequest;
import com.autoreliance.contracts.integration.v1.GetSnapshotGraphFactsResponse;
import com.autoreliance.contracts.integration.v1.GraphFactsServiceGrpc;
import com.autoreliance.contracts.integration.v1.GraphNode;
import com.autoreliance.contracts.integration.v1.NodeType;
import com.google.protobuf.Descriptors.Descriptor;
import com.google.protobuf.Descriptors.FieldDescriptor;
import com.google.protobuf.Descriptors.ServiceDescriptor;
import io.grpc.MethodDescriptor.MethodType;
import org.junit.jupiter.api.Test;

/**
 * Task 2.3 compile test: the generated Java message and gRPC stub classes exist, compile, carry the
 * contracted packages, and round-trip. Every request message has a string tenant_id field 1.
 */
class ProtoContractCompileTest {

    private static final String TENANT = "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d";

    @Test
    void packagesAreVersionedPerContext() {
        assertThat(ValidateConfigurationRequest.getDescriptor().getFile().getPackage())
                .isEqualTo("autoreliance.configuration.v1");
        assertThat(GetSnapshotGraphFactsRequest.getDescriptor().getFile().getPackage())
                .isEqualTo("autoreliance.integration.v1");
    }

    @Test
    void everyRequestMessageHasTenantIdAsStringFieldOne() {
        for (ServiceDescriptor service : new ServiceDescriptor[] {
                ValidateConfigurationRequest.getDescriptor().getFile().findServiceByName("ConfigValidationService"),
                GetSnapshotGraphFactsRequest.getDescriptor().getFile().findServiceByName("GraphFactsService")}) {
            assertThat(service).isNotNull();
            service.getMethods().forEach(method -> {
                Descriptor input = method.getInputType();
                FieldDescriptor tenant = input.findFieldByName("tenant_id");
                assertThat(tenant).as("%s has tenant_id", input.getFullName()).isNotNull();
                assertThat(tenant.getNumber()).isEqualTo(1);
                assertThat(tenant.getJavaType()).isEqualTo(FieldDescriptor.JavaType.STRING);
            });
        }
    }

    @Test
    void grpcStubsAreGeneratedAsUnaryMethods() {
        assertThat(ConfigValidationServiceGrpc.getValidateConfigurationMethod().getFullMethodName())
                .isEqualTo("autoreliance.configuration.v1.ConfigValidationService/ValidateConfiguration");
        assertThat(ConfigValidationServiceGrpc.getValidateConfigurationMethod().getType()).isEqualTo(MethodType.UNARY);
        assertThat(GraphFactsServiceGrpc.getGetSnapshotGraphFactsMethod().getFullMethodName())
                .isEqualTo("autoreliance.integration.v1.GraphFactsService/GetSnapshotGraphFacts");
        assertThat(GraphFactsServiceGrpc.getGetSnapshotGraphFactsMethod().getType()).isEqualTo(MethodType.UNARY);
    }

    @Test
    void messagesRoundTrip() throws Exception {
        ValidateConfigurationResponse response = ValidateConfigurationResponse.newBuilder()
                .setSnapshotCanonicalId("3b4c5d6e-7f8a-4b9c-8d0e-1f2a3b4c5d6e")
                .setRuleSetVersion("rs-2026.11.1")
                .setOverallStatus(ValidationStatus.VALIDATION_STATUS_FAIL)
                .addFailedRuleIds("FIC-RULE-HW-001")
                .addRuleResults(RuleResult.newBuilder()
                        .setRuleId("FIC-RULE-HW-001")
                        .setRuleCategory(RuleCategory.RULE_CATEGORY_HARDWARE_REVISION_COMPATIBILITY)
                        .setStatus(ValidationStatus.VALIDATION_STATUS_FAIL)
                        .addOffendingEntityCanonicalIds("5d6e7f8a-9b0c-4d1e-8f2a-3b4c5d6e7f8a"))
                .build();
        assertThat(ValidateConfigurationResponse.parseFrom(response.toByteArray())).isEqualTo(response);

        GetSnapshotGraphFactsResponse facts = GetSnapshotGraphFactsResponse.newBuilder()
                .setSnapshotCanonicalId("3b4c5d6e-7f8a-4b9c-8d0e-1f2a3b4c5d6e")
                .addNodes(GraphNode.newBuilder()
                        .setCanonicalId("5d6e7f8a-9b0c-4d1e-8f2a-3b4c5d6e7f8a")
                        .setNodeType(NodeType.NODE_TYPE_ECU)
                        .putAttributes("hardwareRevision", "FIC-HW-B"))
                .build();
        assertThat(GetSnapshotGraphFactsResponse.parseFrom(facts.toByteArray())).isEqualTo(facts);

        ValidateConfigurationRequest request = ValidateConfigurationRequest.newBuilder()
                .setTenantId(TENANT).setSnapshotCanonicalId("3b4c5d6e-7f8a-4b9c-8d0e-1f2a3b4c5d6e").build();
        assertThat(ValidateConfigurationRequest.parseFrom(request.toByteArray()).getTenantId()).isEqualTo(TENANT);
    }
}
