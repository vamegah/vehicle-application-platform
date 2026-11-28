#!/bin/sh
# Garage bootstrap job (task 1.2, ADR-013, ADR-018, ADR-020). Runs in the pinned hashicorp/vault image, which
# already runs in compose (BusyBox sh and wget), so it adds no image. The Garage image has no shell, and
# `garage key import` fails with 409 on a second run, so the job drives Garage's admin API v2 over HTTP
# instead and checks before every create. Idempotent; never prints a secret.
#
# Result, and nothing else:
#   - exactly two buckets for the dev environment: autoreliance-raw-dev and autoreliance-text-dev
#     (seed tenants are key prefixes, never buckets)
#   - the legacy-integration key: read and write on both buckets
#   - the data-readiness key: read on the text bucket only (no write, no owner, nothing on raw)
set -eu

: "${GARAGE_ADMIN_TOKEN:?}"
: "${LEGACY_INTEGRATION_ACCESS_KEY_ID:?}" "${LEGACY_INTEGRATION_SECRET_ACCESS_KEY:?}"
: "${DATA_READINESS_ACCESS_KEY_ID:?}" "${DATA_READINESS_SECRET_ACCESS_KEY:?}"

API="${GARAGE_ADMIN_URL:-http://garage:3903}/v2"
RAW_BUCKET="autoreliance-raw-dev"
TEXT_BUCKET="autoreliance-text-dev"
ERR=/tmp/garage-bootstrap.err

log() { echo "garage-bootstrap: $*"; }

# GET <endpoint?query>: prints the body; returns 1 on 404, exits on any other error.
get() {
  if wget -q -O - --header "Authorization: Bearer $GARAGE_ADMIN_TOKEN" "$API/$1" 2>"$ERR"; then return 0; fi
  if grep -q ' 404' "$ERR"; then return 1; fi
  log "GET $1 failed: $(cat "$ERR")"; exit 1
}

# POST <endpoint> <json>: prints the body; exits on any error.
post() {
  if wget -q -O - --header "Authorization: Bearer $GARAGE_ADMIN_TOKEN" --header "Content-Type: application/json" \
      --post-data "$2" "$API/$1" 2>"$ERR"; then return 0; fi
  log "POST $1 failed: $(cat "$ERR")"; exit 1
}

i=0
until wget -q -O /dev/null "${GARAGE_ADMIN_URL:-http://garage:3903}/health" 2>/dev/null; do
  i=$((i + 1))
  [ "$i" -le 60 ] || { log "Garage admin API did not become ready"; exit 1; }
  sleep 1
done

ensure_bucket() { # alias -> prints bucket id
  body=$(get "GetBucketInfo?globalAlias=$1") || body=$(post CreateBucket "{\"globalAlias\":\"$1\"}")
  id=$(printf '%s' "$body" | sed -n 's/^[^"]*"id" *: *"\([0-9a-f]*\)".*/\1/p' | head -n 1)
  [ -n "$id" ] || { log "no bucket id for $1"; exit 1; }
  printf '%s' "$id"
}

ensure_key() { # id secret name
  if get "GetKeyInfo?id=$1" >/dev/null; then return 0; fi
  post ImportKey "{\"accessKeyId\":\"$1\",\"secretAccessKey\":\"$2\",\"name\":\"$3\"}" >/dev/null
  log "imported key $3"
}

perm() { # Allow|Deny bucketId keyId read write owner
  post "${1}BucketKey" "{\"bucketId\":\"$2\",\"accessKeyId\":\"$3\",\"permissions\":{\"read\":$4,\"write\":$5,\"owner\":$6}}" >/dev/null
}

raw=$(ensure_bucket "$RAW_BUCKET")
text=$(ensure_bucket "$TEXT_BUCKET")
log "buckets $RAW_BUCKET and $TEXT_BUCKET present"

ensure_key "$LEGACY_INTEGRATION_ACCESS_KEY_ID" "$LEGACY_INTEGRATION_SECRET_ACCESS_KEY" legacy-integration
ensure_key "$DATA_READINESS_ACCESS_KEY_ID" "$DATA_READINESS_SECRET_ACCESS_KEY" data-readiness

li="$LEGACY_INTEGRATION_ACCESS_KEY_ID"
dr="$DATA_READINESS_ACCESS_KEY_ID"
# Allow sets the flags that are true; Deny removes the flags that are true. Both are idempotent.
perm Allow "$raw" "$li" true true false
perm Allow "$text" "$li" true true false
perm Deny "$raw" "$li" false false true
perm Deny "$text" "$li" false false true
perm Allow "$text" "$dr" true false false
perm Deny "$text" "$dr" false true true
perm Deny "$raw" "$dr" true true true
log "grants: legacy-integration read+write on both buckets; data-readiness read on $TEXT_BUCKET only"
log "done"
