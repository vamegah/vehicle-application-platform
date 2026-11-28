# Deployable release-assurance, Java application container (task 1.6). Build context: the repository root (platform/docker-compose.yml sets it).
# Copies the runnable jar built by `python scripts/build` (or `mvn -DskipTests package`); no build runs in the image.
# Base image pinned by tag and digest in DEPENDENCIES.lock.md.
FROM eclipse-temurin:21.0.13_9-jre-noble@sha256:b4f9d2a0bc273417cf5219b7b832bbf0493ed500b7b57d5001d9f83374659060
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY services/release-assurance/target/release-assurance-0.1.0.jar /app/app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75", "-XX:+ExitOnOutOfMemoryError", "-jar", "/app/app.jar"]
