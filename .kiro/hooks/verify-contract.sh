#!/usr/bin/env bash
# Blocks task completion if the service's contract file is missing.
set -euo pipefail

# Drain stdin (hook framework writes context; this script reads git, not stdin)
cat >/dev/null

# Include untracked files so brand-new service dirs are caught
changed=$( { git diff --name-only HEAD; git ls-files --others --exclude-standard; } 2>/dev/null || true)
[[ -z "$changed" ]] && exit 0

services=(
  # Phase 1
  data-readiness
  legacy-integration
  integration-intelligence
  configuration-assurance
  release-assurance
  api-gateway
  audit-sink
  # Phase 2
  quality-intelligence
  diagnostic
  connected-service
  # Phase 3
  test-lab
  security-compliance
  ota-risk
  # Phase 4
  knowledge-copilot
)

for svc in "${services[@]}"; do
  if echo "$changed" | grep -q "^services/$svc/"; then
    found=0
    for ext in yaml yml json; do
      [[ -f "contracts/openapi/$svc.$ext" ]] && found=1
      [[ -f "contracts/asyncapi/$svc.$ext" ]] && found=1
    done
    compgen -G "contracts/proto/$svc/*.proto" >/dev/null && found=1

    if [[ $found -eq 0 ]]; then
      echo "BLOCKED: services/$svc changed but no contract in contracts/" >&2
      echo "Add OpenAPI/AsyncAPI/proto before marking this task complete." >&2
      exit 2
    fi
  fi
done
exit 0