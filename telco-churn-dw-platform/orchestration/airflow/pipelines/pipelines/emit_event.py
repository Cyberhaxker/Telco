"""Publish a dw.events.v1 notification (e.g. dw.refreshed) with the standard envelope."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

from telco_common.kafka import TOPIC_DW_EVENTS, encode, envelope

log = logging.getLogger("pipelines.emit_event")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("event_type", choices=["dw.refreshed", "model.promoted"])
    ap.add_argument("--payload", default="{}", help="JSON object")
    args = ap.parse_args()
    from confluent_kafka import Producer

    payload = json.loads(args.payload)
    payload.setdefault("dag_run_id", os.environ.get("AIRFLOW_CTX_DAG_RUN_ID"))
    msg = envelope(args.event_type, payload, source="airflow")
    producer = Producer(
        {"bootstrap.servers": os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"), "acks": "all", "enable.idempotence": True}
    )
    producer.produce(TOPIC_DW_EVENTS, key=args.event_type.encode(), value=encode(msg))
    remaining = producer.flush(30)
    if remaining:
        log.error("event %s was not delivered", msg["event_id"])
        return 1
    log.info("published %s (%s)", args.event_type, msg["event_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
