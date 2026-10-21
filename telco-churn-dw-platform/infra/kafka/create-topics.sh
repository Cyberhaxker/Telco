#!/usr/bin/env bash
# Idempotently create the platform topics (KRaft cluster, no ZooKeeper).
set -euo pipefail
BS="${BOOTSTRAP:-kafka:9092}"
RF="${REPLICATION_FACTOR:-1}"
MIN_ISR=$(( RF > 1 ? 2 : 1 ))
K=/opt/kafka/bin/kafka-topics.sh

create() { # name partitions retention_ms
  $K --bootstrap-server "$BS" --create --if-not-exists --topic "$1" \
     --partitions "$2" --replication-factor "$RF" \
     --config min.insync.replicas="$MIN_ISR" --config retention.ms="$3" \
     --config cleanup.policy=delete
}

create ingest.customers.v1     3 604800000    # 7 days
create ingest.subscriptions.v1 3 604800000
create ingest.dlq.v1           1 2592000000   # 30 days, for reprocessing
create dw.events.v1            1 604800000

$K --bootstrap-server "$BS" --list
