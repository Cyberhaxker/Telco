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

# Avoid clashes with services already listening on this machine.
port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }
for pair in POSTGRES_PORT:5432:5434 MYSQL_PORT:3306:3307 KAFKA_PORT:9092:9093; do
  IFS=: read -r var default alt <<<"$pair"
  if port_busy "$default"; then
    sed -i "s/^${var}=${default}$/${var}=${alt}/" .env
    echo "port ${default} is busy - ${var} set to ${alt}"
  fi
done

chmod 600 .env
echo "Created .env with random secrets (demo user password: $(grep ^DEMO_USER_PASSWORD .env | cut -d= -f2))"
