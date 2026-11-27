#!/bin/sh
# Vault init job (task 1.2). Runs in the pinned hashicorp/vault image against the dev server.
# Idempotent: every step checks first and creates only what is missing, so `docker compose up` can run it again.
# It never prints a secret value (no `set -x`, `vault kv put` output shows metadata only).
#
# Seeds, for local development only:
#   - a transit key per seed tenant (transit/keys/tenant-<tenantId>)
#   - the KV version 2 mount `kv` (the layout read-back of task 7.15 needs KV v2 metadata)
#   - the gateway's Internal_Principal signing key (transit/keys/internal-principal, ed25519)
#   - kv/platform/redis/broker and kv/platform/redis/cache (one local Redis, logical DB 0 and 1)
#   - kv/platform/storage/settings (endpoint, region garage, path-style)
#   - kv/tenants/<tenantId>/storage/legacy-integration and .../data-readiness (the two Garage keys, identical
#     for every seed tenant because Garage cannot scope keys by prefix: the named dev limitation, ADR-020)
#   - kv/tenants/<tenantId>/storage/layout = shared (no dedicated bucket in compose)
set -eu

: "${VAULT_ADDR:?}" "${VAULT_TOKEN:?}" "${SEED_TENANT_IDS:?}" "${REDIS_PASSWORD:?}"
: "${LEGACY_INTEGRATION_ACCESS_KEY_ID:?}" "${LEGACY_INTEGRATION_SECRET_ACCESS_KEY:?}"
: "${DATA_READINESS_ACCESS_KEY_ID:?}" "${DATA_READINESS_SECRET_ACCESS_KEY:?}"

log() { echo "vault-init: $*"; }

i=0
until vault status >/dev/null 2>&1; do
  i=$((i + 1))
  [ "$i" -le 60 ] || { log "Vault did not become ready"; exit 1; }
  sleep 1
done

mounts=$(vault secrets list -format=json)
if ! printf '%s' "$mounts" | grep -q '"kv/"'; then
  vault secrets enable -path=kv -version=2 kv >/dev/null
  log "enabled KV version 2 at kv/"
fi
if ! vault read -format=json sys/mounts/kv | grep -Eq '"version": *"2"'; then
  log "the kv/ mount is not KV version 2"; exit 1
fi
if ! printf '%s' "$mounts" | grep -q '"transit/"'; then
  vault secrets enable transit >/dev/null
  log "enabled transit"
fi

ensure_transit_key() { # name type
  if vault read "transit/keys/$1" >/dev/null 2>&1; then return 0; fi
  vault write -f "transit/keys/$1" type="$2" >/dev/null
  log "created transit key $1 ($2)"
}

ensure_kv() { # path key=value...
  path=$1; shift
  if vault kv get -mount=kv "$path" >/dev/null 2>&1; then return 0; fi
  vault kv put -mount=kv "$path" "$@" >/dev/null
  log "wrote kv/$path"
}

ensure_transit_key internal-principal ed25519
ensure_kv platform/redis/broker url="redis://default:${REDIS_PASSWORD}@redis:6379/0"
ensure_kv platform/redis/cache url="redis://default:${REDIS_PASSWORD}@redis:6379/1"
ensure_kv platform/storage/settings endpoint="http://garage:3900" region="garage" pathStyle="true"

for tenant in $SEED_TENANT_IDS; do
  ensure_transit_key "tenant-$tenant" aes256-gcm96
  ensure_kv "tenants/$tenant/storage/legacy-integration" \
    accessKeyId="$LEGACY_INTEGRATION_ACCESS_KEY_ID" secretAccessKey="$LEGACY_INTEGRATION_SECRET_ACCESS_KEY"
  ensure_kv "tenants/$tenant/storage/data-readiness" \
    accessKeyId="$DATA_READINESS_ACCESS_KEY_ID" secretAccessKey="$DATA_READINESS_SECRET_ACCESS_KEY"
  ensure_kv "tenants/$tenant/storage/layout" storage.layout="shared"
done

log "done"
