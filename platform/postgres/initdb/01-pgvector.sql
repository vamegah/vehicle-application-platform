-- Task 1.2: enable pgvector in the platform database (pgvector inside PostgreSQL; no separate vector database).
-- Schemas, per-context roles, and the RLS baseline are created by task 1.3.
CREATE EXTENSION IF NOT EXISTS vector;
