package com.autoreliance.verification;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/** Verification-only application (task 1.4). Not a service. */
@SpringBootApplication
public class SmokeApplication {
    public static void main(String[] args) {
        SpringApplication.run(SmokeApplication.class, args);
    }
}
