#!/usr/bin/env bash
# Runs tests for every runtime touched by a saved file.
set -euo pipefail

input=$(cat)
target=$(echo "$input" | jq -r '.tool_input.path // .tool_input.file_path // empty' 2>/dev/null || true)
[[ -z "$target" ]] && exit 0

# Normalize: backslashes -> slashes; absolute paths -> repo-relative
target=${target//\\//}
[[ "$target" == */services/* ]] && target="services/${target#*/services/}"
[[ "$target" == */apps/web/* ]] && target="apps/web/${target#*/apps/web/}"

case "$target" in
  *.java|*.py|*.ts|*.tsx) ;;
  *) exit 0 ;;
esac

roots=()

# --- Pass 1: nearest runnable project root via upward walk (services/) ---
dir=$(dirname "$target")
while [[ "$dir" == services/* || "$dir" == services ]]; do
  if [[ -f "$dir/pom.xml" || -f "$dir/pyproject.toml" || -f "$dir/requirements.txt" || -f "$dir/setup.py" ]]; then
    roots+=("$dir")
    break
  fi
  [[ "$dir" == "services" ]] && break
  dir=$(dirname "$dir")
done

# --- Pass 2: cross-runtime coverage for mixed-runtime services ---

# Release Assurance: Java service + Python inference-sidecar.
if [[ "$target" == services/release-assurance/* ]]; then
  sc="services/release-assurance/inference-sidecar"
  if [[ -d "$sc" ]] && { [[ -f "$sc/pyproject.toml" || -f "$sc/requirements.txt" || -f "$sc/setup.py" ]]; }; then
    roots+=("$sc")
  fi
fi

# NOTE: connector-runtime branch removed. Java connector code now lives at
# services/legacy-integration/ with its own pom.xml, found by the upward walk.

# Dedupe (guard empty under set -u)
if (( ${#roots[@]} > 0 )); then
  mapfile -t roots < <(printf '%s\n' "${roots[@]}" | sort -u)
fi

failed=0
for root in "${roots[@]}"; do
  if [[ -f "$root/pom.xml" ]]; then
    (cd "$root" && mvn -q -DskipITs test) || failed=1
  elif [[ -f "$root/pyproject.toml" || -f "$root/requirements.txt" || -f "$root/setup.py" ]]; then
    # pytest exits 5 when no tests are collected. Treat 0 or 5 as pass.
    # The `&& rc=0 || rc=$?` form protects pytest from set -e so we can read its code.
    (cd "$root" && { pytest -q --maxfail=1 && rc=0 || rc=$?; [[ $rc -eq 0 || $rc -eq 5 ]]; }) || failed=1
  fi
done

# --- Web app branch: .ts/.tsx under apps/web/ ---
if [[ "$target" == apps/web/* && -f "apps/web/package.json" ]]; then
  if jq -e '.scripts.test' apps/web/package.json >/dev/null 2>&1; then
    (cd apps/web && npm test --silent) || failed=1
  fi
fi

[[ $failed -eq 0 ]] || exit 2
exit 0