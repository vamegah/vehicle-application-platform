#!/usr/bin/env bash
set -euo pipefail

cat >/dev/null   # drain hook context

# Nothing to commit? Exit cleanly.
if [[ -z "$(git status --porcelain)" ]]; then
  exit 0
fi

# Do not commit if tests are red — the steering file says so, this enforces it.
# Replace with your actual test command or a Makefile target.
if ! make test >/dev/null 2>&1; then
  echo "Tests failing — skipping auto-commit." >&2
  exit 0   # not 2: we do not want to block the agent, just skip the commit
fi

branch=$(git branch --show-current)
[[ -z "$branch" ]] && exit 0
[[ "$branch" == "main" || "$branch" == "master" ]] && exit 0

# Derive a conventional-commit message from the changed paths.
changed=$(git diff --name-only HEAD)
type="chore"
scope=$(echo "$changed" | sed -nE 's|^services/([^/]+)/.*|\1|p' | head -n1)
[[ -z "$scope" ]] && scope=$(echo "$changed" | sed -nE 's|^\.kiro/([^/]+)/.*|\1|p' | head -n1)
[[ -z "$scope" ]] && scope="repo"

git add -A
git commit -m "${type}(${scope}): auto-commit on agent stop"

# Set upstream on first push, then push.
if ! git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
  git push -u origin "$branch"
else
  git push
fi