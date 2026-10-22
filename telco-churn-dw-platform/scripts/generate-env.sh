#!/usr/bin/env bash
# Create .env from .env.example, replacing every CHANGE_ME value with a random
# secret and generating the Airflow Fernet key. Never overwrites an existing .env.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  echo ".env already exists" >&2
  exit 0
fi

rand() { head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c "${1:-32}"; }
fernet() { head -c 32 /dev/urandom | base64 | tr '+/' '-_'; }

while IFS= read -r line; do
  if [[ "$line" =~ ^([A-Z0-9_]+)=CHANGE_ME[^[:space:]]*(.*)$ ]]; then
    echo "${BASH_REMATCH[1]}=$(rand 32)"
  elif [[ "$line" =~ ^AIRFLOW_FERNET_KEY=$ ]]; then
    echo "AIRFLOW_FERNET_KEY=$(fernet)"
  else
    echo "$line"
  fi
done < .env.example > .env

# Avoid clashes with services already listening on this machine: walk upwards
# from the default until a free port is found.
port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }
taken=" "
for var in WEB_PORT APISIX_PORT KEYCLOAK_PORT AIRFLOW_PORT MLFLOW_PORT GRAFANA_PORT PROMETHEUS_PORT POSTGRES_PORT MYSQL_PORT KAFKA_PORT; do
  default=$(grep "^${var}=" .env | cut -d= -f2)
  port=$default
  while port_busy "$port" || [[ "$taken" == *" $port "* ]]; do
    port=$((port + 1))
  done
  taken+="$port "
  if [[ "$port" != "$default" ]]; then
    sed -i "s/^${var}=${default}$/${var}=${port}/" .env
    echo "port ${default} is busy - ${var} set to ${port}"
  fi
done

# Keep URLs in step with any port that moved.
set -a; source .env; set +a
sed -i "s#^PUBLIC_WEB_URL=.*#PUBLIC_WEB_URL=http://localhost:${WEB_PORT}#; \
        s#^PUBLIC_GATEWAY_URL=.*#PUBLIC_GATEWAY_URL=http://localhost:${APISIX_PORT}#; \
        s#^PUBLIC_KEYCLOAK_URL=.*#PUBLIC_KEYCLOAK_URL=http://localhost:${KEYCLOAK_PORT}#" .env

chmod 600 .env
echo "Created .env with random secrets. Demo user password: see DEMO_USER_PASSWORD in .env"
