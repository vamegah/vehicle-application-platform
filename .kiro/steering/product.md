# Product: AutoReliance AI

## Purpose
AI-powered automotive engineering, quality, and release assurance platform.

## Central question
"Has this automotive software or hardware change been adequately validated,
what risks remain, and what evidence supports releasing it?"

## Scope boundaries (Phase 1 ONLY — do not build beyond this)
- Data Readiness, Legacy Integration, Integration Intelligence,
  Configuration Assurance, Release Assurance
- NO Quality Intelligence, Diagnostic, Security, OTA, Copilot in Phase 1

## Anti-scope (explicitly out of bounds)
- No shared database across bounded contexts
- No separate vector DB (pgvector only)
- No AI conclusion without evidence citations
- No real automaker data — all seed data fictional and labeled