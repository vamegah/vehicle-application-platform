package com.autoreliance.verification;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.junit.jupiter.api.Test;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.neo4j.Neo4jContainer;
import org.testcontainers.utility.DockerImageName;

/**
 * Task 1.4(e) and (i). These tests need a Docker daemon. They are disabled without Docker so a laptop
 * without Docker does not fail; CI has Docker, and the CI workflow fails if these tests are skipped.
 * The images come from the surefire system properties, which equal the ledger rows.
 */
@Testcontainers(disabledWithoutDocker = true)
class DockerBackedCompatibilityTest {

    @Test
    void kafkaClients422ProduceAndConsumeAgainstKafka3Broker() {
        String image = System.getProperty("kafka.image");
        try (KafkaContainer kafka = new KafkaContainer(DockerImageName.parse(image).asCompatibleSubstituteFor("apache/kafka"))) {
            kafka.start();
            Properties p = new Properties();
            p.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, kafka.getBootstrapServers());
            p.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
            p.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
            try (KafkaProducer<String, String> producer = new KafkaProducer<>(p)) {
                producer.send(new ProducerRecord<>("smoke.topic.recorded", "t1:k", "v")).get();
            } catch (Exception e) {
                throw new AssertionError(e);
            }
            Properties c = new Properties();
            c.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, kafka.getBootstrapServers());
            c.put(ConsumerConfig.GROUP_ID_CONFIG, "smoke");
            c.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
            c.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class.getName());
            c.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class.getName());
            try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(c)) {
                consumer.subscribe(List.of("smoke.topic.recorded"));
                int seen = 0;
                for (int i = 0; i < 20 && seen == 0; i++) {
                    seen += consumer.poll(Duration.ofMillis(500)).count();
                }
                assertThat(seen).isEqualTo(1);
            }
        }
    }

    @Test
    void neo4jDriver610RunsQueryAgainstNeo4j5Server() {
        String image = System.getProperty("neo4j.image");
        try (Neo4jContainer neo4j = new Neo4jContainer(DockerImageName.parse(image).asCompatibleSubstituteFor("neo4j")).withoutAuthentication()) {
            neo4j.start();
            try (Driver driver = GraphDatabase.driver(neo4j.getBoltUrl(), AuthTokens.none())) {
                driver.verifyConnectivity();
                var record = driver.executableQuery("RETURN 1 AS n").execute().records().get(0);
                assertThat(record.get("n").asInt()).isEqualTo(1);
                var versions = driver.executableQuery("CALL dbms.components() YIELD versions RETURN versions[0] AS v")
                        .execute().records().get(0).get("v").asString();
                assertThat(versions).startsWith("5.");
            }
        }
    }
}
