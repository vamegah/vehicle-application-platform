package com.autoreliance.auditsink;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/** Entry point of the audit-sink bounded context (task 1.1 skeleton). */
@SpringBootApplication
public class AuditSinkApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuditSinkApplication.class, args);
    }
}
