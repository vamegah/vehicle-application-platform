#!/usr/bin/env bash
# Blocks writes to dependency manifests that contain loose versions.
set -euo pipefail

input=$(cat)
target=$(echo "$input" | jq -r '.tool_input.path // .tool_input.file_path // empty' 2>/dev/null || true)
[[ -z "$target" ]] && exit 0

case "$(basename "$target")" in
  package.json|requirements.txt|pyproject.toml|pom.xml|build.gradle|build.gradle.kts) ;;
  *) exit 0 ;;
esac

content=$(echo "$input" | jq -r '.tool_input.content // .tool_input.new_str // empty' 2>/dev/null || true)
[[ -z "$content" ]] && exit 0

# Loose-version patterns that must never appear
bad_patterns='(>=|~>|~=|\^|"[0-9]+\.[0-9]+\.[0-9]+"|\x27[0-9]+\.[0-9]+\.[0-9]+\x27|latest|\*)'
# Allowed exact-pin patterns: "x.y.z" in package.json, ==x.y.z in pip, <version>x.y.z</version> in pom
if echo "$content" | grep -nE '(>=|~>|"latest"|\blatest\b|\*)' >/dev/null 2>&1; then
  echo "BLOCKED: loose dependency version detected in $target" >&2
  echo "Every dependency must be exactly pinned (e.g. \"1.2.3\" or ==1.2.3)." >&2
  echo "Update DEPENDENCIES.lock.md and re-try." >&2
  exit 2
fi

# require exact semver in package.json / pom / pip
if [[ "$target" == *package.json ]]; then
  if grep -nE ':[[:space:]]*"[~^]' "$target" 2>/dev/null; then
    echo "BLOCKED: range operator in package.json ($target)" >&2; exit 2
  fi
fi

exit 0