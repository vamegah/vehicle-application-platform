#!/usr/bin/env bash
# Blocks writes outside Phase 1 service directories.
set -euo pipefail

input=$(cat)
target=$(echo "$input" | jq -r '.tool_input.path // .tool_input.file_path // empty' 2>/dev/null || true)
[[ -z "$target" ]] && exit 0

# Normalize: backslashes -> slashes; absolute paths -> repo-relative
target=${target//\\//}
[[ "$target" == */services/* ]] && target="services/${target#*/services/}"

PHASE1=(
  data-readiness
  legacy-integration
  integration-intelligence
  configuration-assurance
  release-assurance
  api-gateway
  audit-sink
)

PHASE_FUTURE=(
  quality-intelligence
  diagnostic
  connected-service
  test-lab
  security-compliance
  ota-risk
  knowledge-copilot
)

for svc in "${PHASE_FUTURE[@]}"; do
  if [[ "$target" == services/$svc/* ]]; then
    echo "BLOCKED: $target belongs to a Phase 2-4 bounded context." >&2
    echo "This session implements Phase 1 only: ${PHASE1[*]}" >&2
    exit 2
  fi
done
exit 0