#!/bin/sh
# Render /config.json (runtime settings for the PWA) from the environment.
set -eu
mkdir -p /tmp/config
cat > /tmp/config/config.json <<JSON
{"keycloakUrl":"${PUBLIC_KEYCLOAK_URL}","realm":"${KEYCLOAK_REALM:-telco}","clientId":"${KEYCLOAK_PWA_CLIENT_ID:-telco-pwa}","apiBase":"/api/v1","environment":"${ENVIRONMENT:-dev}"}
JSON
