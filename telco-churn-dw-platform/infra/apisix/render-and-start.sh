#!/usr/bin/env bash
# Render the declarative route file from the environment, then start APISIX.
set -euo pipefail
SRC=/usr/local/apisix/conf/telco
DST=/usr/local/apisix/conf

for v in KEYCLOAK_REALM PUBLIC_WEB_URL KEYCLOAK_GATEWAY_CLIENT_ID KEYCLOAK_GATEWAY_CLIENT_SECRET; do
  [[ -n "${!v:-}" ]] || { echo "render-and-start: $v is not set" >&2; exit 1; }
done

cp "$SRC/config.yaml" "$DST/config.yaml"
content="$(cat "$SRC/apisix.yaml.tmpl")"
for v in KEYCLOAK_REALM PUBLIC_WEB_URL KEYCLOAK_GATEWAY_CLIENT_ID KEYCLOAK_GATEWAY_CLIENT_SECRET; do
  content="${content//\$\{$v\}/${!v}}"
done
printf '%s\n' "$content" > "$DST/apisix.yaml"

if grep -q '\${' "$DST/apisix.yaml"; then
  echo "render-and-start: unresolved placeholder in apisix.yaml" >&2
  grep -n '\${' "$DST/apisix.yaml" >&2
  exit 1
fi

exec /docker-entrypoint.sh docker-start
