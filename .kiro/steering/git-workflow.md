# Git Workflow — Commit and Push Frequently

## Standing instruction
Commit and push after every meaningful unit of work, not at the end of a
session. A "meaningful unit" is one of:
- a task from tasks.md is complete and its tests pass
- a bounded context's contract is written or updated
- a hook script or steering file is edited
- a design.md or validation.md decision is recorded

## Commit message format
Use Conventional Commits:
  <type>(<scope>): <short imperative summary>

Types: feat, fix, refactor, test, docs, chore, build, ci
Scope = bounded context name (e.g. release-assurance, data-readiness)

Examples:
  feat(release-assurance): add evidence-sufficiency scorer
  chore(hooks): pin dev S3 image digest
  docs(validation): record Redis isolation checkbox

## Push behavior
- Push to the current branch after every commit.
- If the branch has no upstream, set it on first push.
- Never force-push. Never push to main directly.
- If tests fail, do not commit. Fix the failure first.

## What not to commit
- No .env, no secrets, no real automaker data.
- Seed data must be clearly labeled as fictional.
- Generated clients under contracts/ are committed; build artifacts are not.