# services/release-assurance/AGENTS.md

## Domain assumptions
- A "release" is a tuple of (ECU set, firmware versions, calibration IDs, test evidence)
- Evidence sufficiency is scored 0–100; below threshold blocks release
- Every score MUST cite the test results and coverage gaps that produced it

## Testing conventions
- Rule-engine tests: JUnit 5 + AssertJ, one test per validation rule
- Inference-sidecar tests: pytest, model outputs must be deterministic
  (seed all randomness; no live model calls in unit tests)

## Forbidden in this service
- Do NOT call other services synchronously to compute a score —
  consume Kafka events and maintain a local projection