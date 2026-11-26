# Repository Structure

## Monorepo layout
- `apps/web/` — Next.js frontend (the ONLY frontend app)
- `services/<context-name>/` — one directory per bounded context
- `contracts/openapi/`, `contracts/asyncapi/`, `contracts/proto/` — ALL contracts
- `platform/docker-compose.yml`, `platform/k8s/`, `platform/terraform/`
- `.kiro/specs/<feature>/` — spec files (requirements, design, tasks)

## Service naming
- Bounded contexts use kebab-case: `release-assurance`, `integration-intelligence`
- Java services: `src/main/java/com/autoreliance/<context>/`
- Python services: `app/<context>/` with `main.py` as FastAPI entrypoint

## Contract-first rule
Every service must have its OpenAPI/AsyncAPI/proto contract committed
to `contracts/` BEFORE implementation code is written.